"""Local memory of validated summaries; redaction is heuristic."""

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from .report import IncidentReport

MAX_RECALL = 10
logger = logging.getLogger(__name__)
SECRET = re.compile(
    r"""(?ix)
    \bhttps?://[^\s/@:]+(?::[^\s/@]*)?@ |
    \bauthorization\s*:\s*(?:bearer|basic)\s+[^\s,;]+ |
    \b(?:bearer|basic)\s+[^\s,;]+ |
    \b\w*(?:token|password|passwd|secret|api[_-]?key|apikey)\w*\s*[:=]\s*
    (?:"[^"]*"|'[^']*'|[^\s,;]+) |
    \b(?:sk-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|ghp_[A-Za-z0-9_]+)\b |
    \b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b
    """
)


def _path() -> Path:
    return (
        Path(os.environ.get("OPS_ASSIST_MEMORY_DIR") or Path.home() / ".local/state/ops-assist")
        / "reports.jsonl"
    )


def list_memories(service: str | None = None) -> list[dict[str, str]]:
    """Read valid summaries, skipping corrupt entries with a warning."""
    path = _path()
    if not path.exists():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("service"), str)
                or not isinstance(entry.get("summary"), str)
            ):
                raise ValueError("invalid entry")
        except (ValueError, TypeError):
            logger.warning("Skipping invalid memory line %d", number)
            continue
        if service is None or entry["service"] == service:
            entries.append(entry)
    return entries


def remember(report: IncidentReport, services: list[str]) -> None:
    """Append only a heuristically redacted validated summary for each service."""
    if not services:
        return
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = SECRET.sub("[redacted]", report.summary)
    with path.open("a", encoding="utf-8") as file:
        for service in services:
            file.write(
                json.dumps(
                    {"service": SECRET.sub("[redacted]", service), "summary": summary},
                    ensure_ascii=False,
                )
                + "\n"
            )


def forget(service: str) -> int:
    """Atomically remove summaries for a service and return the count."""
    path = _path()
    if not path.exists():
        return 0
    entries = list_memories()
    kept = [e for e in entries if e["service"] != service]
    removed = len(entries) - len(kept)
    if not removed:
        return 0
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            name = file.name
            for entry in kept:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return removed
