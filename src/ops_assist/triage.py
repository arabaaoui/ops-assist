"""Deterministic preliminary incident classification."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from .observability import ObservationSource
from .tools import _bounded


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
    alerts = source.alerts()
    truncated = len(alerts) > 50
    for alert in alerts[:50]:
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
                cleaned, cut = _bounded(change)
                truncated |= cut
                changes.append(cleaned)
    bounded_services, services_cut = _bounded(services)
    bounded_ids, ids_cut = _bounded(sorted(ids))
    bounded_warnings, warnings_cut = _bounded(warnings)
    truncated |= services_cut or ids_cut or warnings_cut
    return Triage(
        affected_services=bounded_services,
        firing_alert_ids=bounded_ids,
        earliest_since=min(first.values(), default=None),
        suspect_changes=changes,
        warnings=bounded_warnings,
        truncated=truncated,
    )
