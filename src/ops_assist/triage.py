"""Deterministic preliminary incident classification."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from .observability import ObservationSource


class Triage(BaseModel):
    """Preliminary observations, not a diagnosis."""

    affected_services: list[str]
    firing_alert_ids: list[str]
    earliest_since: datetime | None
    suspect_changes: list[dict[str, Any]]
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def pretriage(source: ObservationSource) -> Triage:
    """Order services and select changes within an hour of each service's first alert."""
    rank = {"critical": 4, "high": 3, "warning": 2, "info": 1}
    severity: dict[str, int] = {}
    first: dict[str, datetime] = {}
    ids: list[str] = []
    warnings: list[str] = []
    for alert in source.alerts():
        try:
            service, identifier = alert["service"], alert["id"]
            level = alert["severity"]
            if not isinstance(service, str) or not isinstance(identifier, str):
                raise ValueError("invalid service or id")
            if not isinstance(level, str) or not level.strip():
                raise ValueError("invalid severity")
            when = _time(alert["since"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            warnings.append(f"Skipped alert {alert.get('id', '?')}: {type(exc).__name__}")
            continue
        level = level.lower()
        if level not in rank:
            warnings.append(f"Unknown severity for alert {identifier}: {level[:100]}")
        severity[service] = max(severity.get(service, 0), rank.get(level, 0))
        first[service] = min(first.get(service, when), when)
        ids.append(identifier)
    services = sorted(severity, key=lambda s: (-severity[s], s))
    changes = []
    truncated = False
    for service in services:
        for change in source.changes(service):
            try:
                when = _time(change["ts"])
            except (KeyError, TypeError, ValueError, AttributeError):
                warnings.append(f"Skipped change with invalid timestamp for {service}")
                continue
            if first[service] - timedelta(minutes=60) <= when <= first[service]:
                if len(changes) >= 10:
                    truncated = True
                    continue
                cleaned = {}
                for key, value in change.items():
                    if isinstance(value, str) and len(value) > 300:
                        value = value[:300]
                        truncated = True
                    cleaned[key] = value
                changes.append(cleaned)
    return Triage(
        affected_services=services,
        firing_alert_ids=sorted(ids),
        earliest_since=min(first.values(), default=None),
        suspect_changes=changes,
        warnings=warnings,
        truncated=truncated,
    )
