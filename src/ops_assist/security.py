"""Tool policy, per-invocation budgets, and an append-only local audit."""

import json
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool

from .memory import SECRET
from .observability import ReplaySource

# Unknown names are writes. Expert tools are delegations as well as reads.
TOOL_ACCESS = {
    "get_alerts": "read",
    "get_metric": "read",
    "get_logs": "read",
    "get_changes": "read",
    "recall_past_incidents": "read",
    "list_skills": "read",
    "load_skill": "read",
    "unload_skill": "read",
    "load_skill_resource": "read",
    "metrics_expert": "read",
    "logs_expert": "read",
    "transfer_to_agent": "read",
    "rollback_deployment": "write",
}
DELEGATIONS = frozenset({"metrics_expert", "logs_expert", "transfer_to_agent"})


def _positive(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    if not raw.isdecimal() or int(raw) < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(raw)


def _redact(value: Any, key: str = "") -> Any:
    if re.search(r"(?i)token|password|passwd|secret|api[_-]?key|authorization", key):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return SECRET.sub("[redacted]", value)
    return value


PACKAGE_DIR = Path(__file__).resolve().parent


def _root_path() -> Path:
    root = Path(
        os.path.abspath(
            os.environ.get("OPS_ASSIST_STATE_DIR") or Path.home() / ".local/state/ops-assist"
        )
    )
    if root.is_relative_to(PACKAGE_DIR) or PACKAGE_DIR.is_relative_to(root):
        raise ValueError("state directory overlaps installed package")
    return root


def _open_root() -> tuple[Path, int]:
    """Walk directories through descriptors so components cannot be swapped for symlinks."""
    root = _root_path()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in root.parts[1:]:
            try:
                os.mkdir(component, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
            try:
                child = os.open(component, flags, dir_fd=fd)
            except OSError as exc:
                raise ValueError(
                    "state directory must not contain symlinks or non-directories"
                ) from exc
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid():
            raise ValueError("state directory must be owned by the current user")
        if info.st_mode & 0o022:
            raise ValueError("state directory must not be group or world writable")
        return root, fd
    except BaseException:
        os.close(fd)
        raise


def state_root() -> Path:
    """Validate the state root and return its path."""
    root, fd = _open_root()
    os.close(fd)
    return root


def _plain_name(name: str) -> str:
    if not name or name in (".", "..", "incident-state.json") or "/" in name or "\\" in name:
        raise ValueError("audit file must be a plain name inside the state root")
    return name


def _checked_file(fd: int) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("file must be a regular file owned by the current user")
    if info.st_nlink != 1:
        raise ValueError("file must not have hard links")


class StateStore:
    """Hold one validated directory descriptor for audit and simulation operations."""

    def __init__(self):
        """Resolve names without touching the filesystem until first use."""
        self.root = _root_path()
        self.audit_name = _plain_name(os.environ.get("OPS_ASSIST_AUDIT_FILE") or "audit.jsonl")
        self.fd = None

    def directory(self):
        """Return the single anchored descriptor, opening it lazily."""
        if self.fd is None:
            root, self.fd = _open_root()
            if root != self.root:
                os.close(self.fd)
                self.fd = None
                raise ValueError("state directory changed")
        return self.fd

    def __del__(self):
        """Close the anchored descriptor when its owner is released."""
        fd = getattr(self, "fd", None)
        if fd is not None:
            os.close(fd)

    def open_audit(self):
        """Open a private single-link audit file relative to the anchored root."""
        fd = os.open(
            self.audit_name,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory(),
        )
        try:
            _checked_file(fd)
            os.fchmod(fd, 0o600)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def index_name(self):
        """Resolve an index name without allowing collisions with other state files."""
        name = os.environ.get("OPS_ASSIST_INDEX_FILE") or "knowledge-index.json"
        if name == self.audit_name or name.startswith(".incident-state-"):
            raise ValueError("index file conflicts with another state file")
        try:
            return _plain_name(name)
        except ValueError as exc:
            raise ValueError("index file must be a plain name inside the state root") from exc

    def open_index(self):
        """Open an existing single-link index without following symbolic links."""
        fd = os.open(
            self.index_name(),
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=self.directory(),
        )
        try:
            _checked_file(fd)
        except BaseException:
            os.close(fd)
            raise
        return os.fdopen(fd, "r", encoding="utf-8")

    def write_index(self, data):
        """Replace a validated index atomically inside the anchored state directory."""
        name = self.index_name()
        directory = self.directory()
        try:
            with self.open_index():
                pass
        except FileNotFoundError:
            pass
        temporary = ".knowledge-index-" + secrets.token_hex(16)
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        return self.root / name

    def update_state(self, source, service, deployment_id, version):
        """Replace the simulated state atomically within the same anchored directory."""
        directory = self.directory()
        name = "incident-state.json"
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            state = {}
        else:
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                _checked_file(stream.fileno())
                state = json.load(stream)
        state.setdefault(source.name, {})[service] = {
            "deployment_id": deployment_id,
            "version": version,
        }
        temporary = ".incident-state-" + secrets.token_hex(16)
        fd = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
        return str(self.root / name)


class SecurityBoundary:
    """Shared ADK callbacks for the coordinator and all experts."""

    def __init__(self, *, allow_writes: bool | None = None):
        """Load explicit local policy and budgets."""
        self.max_calls = _positive("OPS_ASSIST_MAX_TOOL_CALLS", 100)
        self.max_delegations = _positive("OPS_ASSIST_MAX_DELEGATIONS", 10)
        self.allow_writes = (
            os.environ.get("OPS_ASSIST_ALLOW_WRITES") == "1"
            if allow_writes is None
            else allow_writes
        )
        self.store = StateStore()
        self.audit_path = self.store.root / self.store.audit_name
        self.runs = {}
        self.starts = {}
        self.audit_failures = set()

    def _open_audit(self):
        return self.store.open_audit()

    def audit(self, tool, args, outcome, started):
        """Write an audit record; failure to audit stops execution."""
        entry = {
            "tool": tool,
            "args": _redact(args),
            "outcome": outcome,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
        fd = self._open_audit()
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            stream.flush()
            if outcome == "pending":
                os.fsync(stream.fileno())

    def before(self, tool, args, tool_context):
        """Deny over-budget calls and unknown or disabled writes before execution."""
        started = time.monotonic()
        # Fail before a tool runs if its audit log cannot be opened.
        fd = self._open_audit()
        os.close(fd)
        run = self.runs.setdefault(tool_context.invocation_id, [0, 0])
        run[0] += 1
        if tool.name in DELEGATIONS:
            run[1] += 1
        reason = None
        if run[0] > self.max_calls:
            reason = "tool_call_limit"
        elif run[1] > self.max_delegations:
            reason = "delegation_limit"
        elif TOOL_ACCESS.get(tool.name, "write") == "write":
            if tool.name != "rollback_deployment" or not self.allow_writes:
                reason = "read_only"
        if reason:
            self.starts[id(tool_context)] = started
            return {"status": "denied", "reason": reason}
        self.starts[id(tool_context)] = started
        confirmation = getattr(tool_context, "tool_confirmation", None)
        if (
            TOOL_ACCESS.get(tool.name, "write") == "write"
            and confirmation
            and confirmation.confirmed
        ):
            try:
                self.audit(tool.name, args, "pending", started)
            except (OSError, ValueError):
                self.starts.pop(id(tool_context), None)
                self.audit_failures.add(id(tool_context))
                return {"status": "denied", "reason": "audit_unavailable"}
        return None

    def after(self, tool, args, tool_context, tool_response):
        """Record normal, refused and failed results, including confirmation requests."""
        if id(tool_context) in self.audit_failures:
            self.audit_failures.remove(id(tool_context))
            return None
        started = self.starts.pop(id(tool_context), time.monotonic())
        error = tool_response.get("error") if isinstance(tool_response, dict) else None
        status = tool_response.get("status") if isinstance(tool_response, dict) else None
        outcome = (
            "denied"
            if status == "denied"
            or (
                error
                and tool.name == "rollback_deployment"
                and ("confirm" in str(error) or "rejected" in str(error))
            )
            else "failed"
            if error or status in ("error", "failed")
            else "ok"
        )
        self.audit(tool.name, args, outcome, started)
        return None

    def error(self, tool, args, tool_context, error):
        """Audit exceptions from ADK tools."""
        self.audit(tool.name, args, "failed", self.starts.pop(id(tool_context), time.monotonic()))
        return None


def make_rollback_tool(source, *, demo_client=None, boundary=None):
    """Build the confirmation-gated rollback; demo clients are explicitly injected."""
    store = boundary.store if boundary else StateStore()

    def rollback_deployment(service: str, deployment_id: str) -> dict:
        """Roll back one recorded deployment after human confirmation."""
        if isinstance(source, ReplaySource):
            matches = [
                c
                for c in source.changes(service)
                if c.get("id") == deployment_id and c.get("kind") == "deployment"
            ]
            if not matches:
                return {"status": "error", "error": "deployment not found for service"}
            try:
                state_file = store.update_state(
                    source, service, deployment_id, matches[0].get("previous_version")
                )
            except (OSError, ValueError) as exc:
                return {"status": "denied", "reason": str(exc)}
            return {
                "status": "ok",
                "state_file": state_file,
                "version": matches[0].get("previous_version"),
            }
        if getattr(source, "name", None) == "demo":
            if demo_client is None:
                return {"status": "error", "error": "demo rollback is not available offline"}
            return demo_client.rollback_deployment(service, deployment_id)
        return {"status": "denied", "reason": "live rollback is forbidden even when confirmed"}

    return FunctionTool(rollback_deployment, require_confirmation=True)
