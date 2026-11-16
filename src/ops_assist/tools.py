"""Agent tools. Plain functions with typed parameters and compact, cited results.

A tool never raises into the agent loop: any failure of the source comes back as
``{"status": "error", "error": ...}`` so the model can read it and adapt, and is
logged with its traceback so a human can see it too.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .observability import ObservationError, ObservationSource

logger = logging.getLogger(__name__)


def _failure(tool: str, error: Exception) -> dict[str, Any]:
    if isinstance(error, ObservationError):
        logger.warning("%s: %s", tool, error)
        return {"status": "error", "error": str(error)}
    # An unexpected failure (timeout, bug, unreadable data): keep the traceback in the
    # logs, give the model only the kind of failure, not internals.
    logger.exception("%s failed unexpectedly", tool)
    return {"status": "error", "error": f"{tool} failed: {type(error).__name__}"}


def make_tools(source: ObservationSource) -> list[Callable[..., dict[str, Any]]]:
    """Bind the read-only tools to one observation source."""

    def get_alerts() -> dict[str, Any]:
        """List the alerts currently firing, with their service, severity and start time.

        Start every investigation here: the alerts tell which service to look at.
        """
        try:
            return {"status": "ok", "alerts": source.alerts()}
        except Exception as e:  # noqa: BLE001 - a tool must never break the agent loop
            return _failure("get_alerts", e)

    return [get_alerts]
