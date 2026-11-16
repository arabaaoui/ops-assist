"""Observation sources: replay, live connectors, and composition."""

from .base import LOG_LEVELS, MAX_LOG_LINES, ObservationError, ObservationSource
from .replay import ReplaySource, list_incidents

__all__ = [
    "LOG_LEVELS",
    "MAX_LOG_LINES",
    "ObservationError",
    "ObservationSource",
    "ReplaySource",
    "list_incidents",
]

from .changes import LiveChanges
from .composite import CompositeSource
from .loki import LokiSource
from .prometheus import PrometheusSource


def source_from_env(incident: str) -> ObservationSource:
    """Select replay or compose live observations with explicit file changes."""
    import math
    import os

    mode = os.environ.get("OPS_ASSIST_SOURCE", "replay")
    if mode == "replay":
        return ReplaySource(incident)
    if mode != "live":
        raise ValueError("OPS_ASSIST_SOURCE must be replay or live")
    try:
        timeout = float(os.environ.get("OPS_ASSIST_HTTP_TIMEOUT", "5"))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError("OPS_ASSIST_HTTP_TIMEOUT must be a positive finite number") from exc
    prometheus = os.environ.get("OPS_ASSIST_PROMETHEUS_URL")
    loki = os.environ.get("OPS_ASSIST_LOKI_URL")
    if not prometheus or not loki:
        raise ValueError("live source requires OPS_ASSIST_PROMETHEUS_URL and OPS_ASSIST_LOKI_URL")
    return CompositeSource(
        PrometheusSource(prometheus, timeout),
        LokiSource(loki, timeout),
        LiveChanges(os.environ.get("OPS_ASSIST_CHANGES_FILE")),
    )
