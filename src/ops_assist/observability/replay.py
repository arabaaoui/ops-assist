"""Replay source: answers from a recorded incident on disk, no network, no cost.

An incident is a folder with ``incident.json`` (description), ``alerts.json``,
``metrics.json``, ``logs.jsonl`` and ``changes.json``. An optional
``expected.json`` holds the answer key for evaluations; this source never reads it,
so no tool can hand the answer to the model. All data is fictional.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import LOG_LEVELS, MAX_LOG_LINES, ObservationError

OBSERVATION_FILES = frozenset(
    {"incident.json", "alerts.json", "metrics.json", "logs.jsonl", "changes.json"}
)

BUNDLED_INCIDENTS = Path(__file__).resolve().parents[1] / "data" / "incidents"


def incidents_dir() -> Path:
    """Return where recorded incidents live: OPS_ASSIST_INCIDENTS_DIR, or the bundled ones."""
    return Path(os.environ.get("OPS_ASSIST_INCIDENTS_DIR") or BUNDLED_INCIDENTS)


def list_incidents(root: Path | None = None) -> list[str]:
    """Return the ids of the recorded incidents."""
    root = root or incidents_dir()
    if not root.is_dir():
        raise FileNotFoundError(f"incidents directory {root} does not exist")
    return sorted(p.name for p in root.iterdir() if (p / "incident.json").is_file())


class ReplaySource:
    """An ``ObservationSource`` backed by one recorded incident."""

    capabilities = frozenset({"alerts", "metric", "logs", "changes"})

    def __init__(self, incident: str, root: Path | None = None) -> None:
        """Load the incident folder ``root/incident``; fail loudly if it is missing."""
        root = root or incidents_dir()
        self.dir = root / incident
        if not (self.dir / "incident.json").is_file():
            raise FileNotFoundError(f"no recorded incident {incident!r} under {root}")
        self.name = f"replay:{incident}"
        self.incident = self._json("incident.json")

    # -- reading the recording: every failure becomes an ObservationError --------

    def _read(self, file: str) -> str:
        if file not in OBSERVATION_FILES:
            raise ObservationError("recorded file is not an observation")
        try:
            path = self.dir / file
            if path.is_symlink() or path.resolve().parent != self.dir.resolve():
                raise ObservationError("recorded observation must be a local file")
            return path.read_text(encoding="utf-8")
        except OSError as e:
            raise ObservationError(f"recorded incident has no readable {file}: {e}") from e

    def _json(self, file: str) -> Any:
        try:
            return json.loads(self._read(file))
        except json.JSONDecodeError as e:
            raise ObservationError(f"recorded {file} is not valid JSON: {e}") from e

    def _records(self, file: str) -> list[dict[str, Any]]:
        if file.endswith(".jsonl"):
            try:
                items = [json.loads(x) for x in self._read(file).splitlines() if x.strip()]
            except json.JSONDecodeError as e:
                raise ObservationError(f"recorded {file} is not valid JSON lines: {e}") from e
        else:
            items = self._json(file)
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ObservationError(f"recorded {file} must be a list of objects")
        missing = [i for i, x in enumerate(items) if "service" not in x]
        if missing:
            raise ObservationError(f"recorded {file}: entries {missing} have no 'service'")
        return items

    def _known_services(self) -> set[str]:
        files = ("alerts.json", "metrics.json", "logs.jsonl", "changes.json")
        return {x["service"] for f in files for x in self._records(f)}

    def _check_service(self, service: str) -> None:
        known = self._known_services()
        if service not in known:
            raise ObservationError(f"unknown service {service!r}; known services: {sorted(known)}")

    # -- the ObservationSource interface -----------------------------------------

    def alerts(self) -> list[dict[str, Any]]:
        """Return the alerts firing in the recorded incident."""
        return [{**a, "source": f"{self.name}/alerts"} for a in self._records("alerts.json")]

    def metric(self, name: str, service: str) -> dict[str, Any]:
        """Return a recorded series, or explain which ones exist."""
        series = self._records("metrics.json")
        for s in series:
            if s.get("name") == name and s["service"] == service:
                return {**s, "source": f"{self.name}/metrics/{name}"}
        known = sorted({f"{s.get('name')} ({s['service']})" for s in series})
        raise ObservationError(f"no series {name!r} for service {service!r}; known series: {known}")

    def logs(self, service: str, level: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent log lines of a service, newest first, optionally by level."""
        if level is not None and level not in LOG_LEVELS:
            raise ObservationError(f"unknown level {level!r}; use one of {list(LOG_LEVELS)}")
        if limit < 1:
            raise ObservationError(f"limit must be at least 1, got {limit}")
        self._check_service(service)
        lines = [
            x
            for x in self._records("logs.jsonl")
            if x["service"] == service and (level is None or x.get("level") == level)
        ]
        lines.sort(key=lambda x: x["ts"], reverse=True)  # sort first, then keep the newest
        return [{**x, "source": f"{self.name}/logs"} for x in lines[: min(limit, MAX_LOG_LINES)]]

    def changes(self, service: str) -> list[dict[str, Any]]:
        """Return recorded changes of a service, newest first."""
        self._check_service(service)
        items = [c for c in self._records("changes.json") if c["service"] == service]
        items.sort(key=lambda c: c["ts"], reverse=True)
        return [{**c, "source": f"{self.name}/changes/{c['id']}"} for c in items]
