"""Agent tools. Plain functions with typed parameters and compact, cited results.

A tool never raises into the agent loop: any failure of the source comes back as
``{"status": "error", "error": ...}`` so the model can read it and adapt, and is
logged with its traceback so a human can see it too.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from .memory import MAX_RECALL, list_memories
from .observability import MAX_LOG_LINES, ObservationError, ObservationSource

logger = logging.getLogger(__name__)


def _failure(tool: str, error: Exception) -> dict[str, Any]:
    if isinstance(error, ObservationError):
        logger.warning("%s: %s", tool, error)
        return {"status": "error", "error": str(error)}
    # An unexpected failure (timeout, bug, unreadable data): keep the traceback in the
    # logs, give the model only the kind of failure, not internals.
    logger.exception("%s failed unexpectedly", tool)
    return {"status": "error", "error": f"{tool} failed: {type(error).__name__}"}


def _bounded(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        return value[:300], len(value) > 300
    if isinstance(value, dict):
        items = {key: _bounded(item) for key, item in value.items()}
        return {key: item[0] for key, item in items.items()}, any(
            item[1] for item in items.values()
        )
    if isinstance(value, list):
        items = [_bounded(item) for item in value]
        return [item[0] for item in items], any(item[1] for item in items)
    return value, False


def _records(records: list, cap: int) -> tuple[list, bool]:
    items, cut = _bounded(records[:cap])
    return items, cut or len(records) > cap


def make_tools(source: ObservationSource) -> list[Callable[..., dict[str, Any]]]:
    """Bind the read-only tools to one observation source."""

    def get_alerts() -> dict[str, Any]:
        """List the alerts currently firing, with their service, severity and start time.

        Start every investigation here: the alerts tell which service to look at.
        """
        try:
            alerts, truncated = _records(source.alerts(), 50)
            return {"status": "ok", "alerts": alerts, "truncated": truncated}
        except Exception as e:  # noqa: BLE001 - a tool must never break the agent loop
            return _failure("get_alerts", e)

    def get_metric(name: str, service: str) -> dict[str, Any]:
        """Read a metric series for a service, summarising long series."""
        try:
            metric = dict(source.metric(name, service))
            raw = metric.get("points", [])
            if not isinstance(raw, list):
                raw = []
            points = [
                p
                for p in raw
                if isinstance(p, (list, tuple))
                and len(p) == 2
                and isinstance(p[1], (int, float))
                and not isinstance(p[1], bool)
                and math.isfinite(p[1])
            ]
            metric["points"] = points
            metric["dropped_points"] = len(raw) - len(points)
            if len(points) > 60:
                values = [p[1] for p in points]
                jump = max(range(1, len(points)), key=lambda i: abs(values[i] - values[i - 1]))
                start = max(0, min(jump - 5, len(points) - 10))
                metric.update(
                    points=points[start : start + 10],
                    summarised=True,
                    min=min(values),
                    max=max(values),
                    mean=sum(values) / len(values),
                    first=points[0],
                    last=points[-1],
                )
            else:
                metric["summarised"] = False
            metric, _ = _bounded(metric)
            return {"status": "ok", "metric": metric}
        except Exception as e:  # noqa: BLE001
            return _failure("get_metric", e)

    def get_logs(service: str, level: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Read recent bounded log lines for a service."""
        try:
            if limit < 1:
                raise ObservationError("limit must be at least 1")
            cap = min(limit, MAX_LOG_LINES)
            lines = source.logs(service, level, cap)
            normalised = [{**line, "message": str(line.get("message") or "")} for line in lines]
            bounded, truncated = _records(normalised, cap)
            return {"status": "ok", "logs": bounded, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("get_logs", e)

    def get_changes(service: str) -> dict[str, Any]:
        """Read changes for a service."""
        try:
            changes, truncated = _records(source.changes(service), 50)
            return {"status": "ok", "changes": changes, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("get_changes", e)

    def recall_past_incidents(service: str) -> dict[str, Any]:
        """Read the most recent saved summaries for a service."""
        try:
            incidents, truncated = _records(list_memories(service)[-MAX_RECALL:], MAX_RECALL)
            return {"status": "ok", "incidents": incidents, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("recall_past_incidents", e)

    return [get_alerts, get_metric, get_logs, get_changes, recall_past_incidents]
