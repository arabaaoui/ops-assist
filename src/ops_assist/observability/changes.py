"""Optional explicit change records for live investigations."""

import json
from pathlib import Path

from .base import ObservationError


class LiveChanges:
    """Read user-provided changes, or explain that they are unavailable."""

    def __init__(self, path: str | None):
        """Select an explicit file without reading bundled incident data."""
        self.path = Path(path) if path else None

    def changes(self, service: str) -> list[dict]:
        """Read and cite changes for a known service, newest first."""
        if self.path is None:
            raise ObservationError(
                "changes are not available in live mode; set OPS_ASSIST_CHANGES_FILE "
                "to a JSON changes file"
            )
        try:
            items = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(items, list) or not all(
                isinstance(item, dict)
                and all(
                    isinstance(item.get(key), str) and item[key] for key in ("id", "ts", "service")
                )
                for item in items
            ):
                raise ValueError("expected a list of changes with id, ts and service")
        except (OSError, ValueError) as exc:
            raise ObservationError(f"cannot read changes file {self.path}: {exc}") from exc
        known = {item["service"] for item in items}
        if service not in known:
            raise ObservationError(f"unknown service {service!r}; known services: {sorted(known)}")
        changes = sorted(
            (item for item in items if item["service"] == service),
            key=lambda item: item["ts"],
            reverse=True,
        )
        return [{**item, "source": f"file:{self.path}/changes/{item['id']}"} for item in changes]
