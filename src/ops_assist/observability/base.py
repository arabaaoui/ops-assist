"""The single observation interface every data source implements.

The agent's tools only ever talk to an ``ObservationSource``. The replay source
reads recorded incidents from disk; Prometheus and Loki implement declared subsets
of the same contract, and a composite combines those subsets. Results are plain dicts so they can be
returned to the model as-is, and every one carries the ``source`` it came from so
the report can cite it.
"""

from __future__ import annotations

from typing import Any, Protocol

LOG_LEVELS = ("debug", "info", "warn", "error")
MAX_LOG_LINES = 200
"""No source returns more log lines than this, whatever the caller asks: a tool result
lands in the model's context, and an unbounded one would crowd out everything else."""


class ObservationError(Exception):
    """A source could not answer; the message is safe to show to the model."""


class ObservationSource(Protocol):
    """Read-only access to alerts, metrics, logs and changes for one environment."""

    name: str
    capabilities: frozenset[str]

    def alerts(self) -> list[dict[str, Any]]:
        """Return the alerts currently firing: ``id, name, service, severity, since, source``."""
        ...

    def metric(self, name: str, service: str) -> dict[str, Any]:
        """Return one metric series for one service: ``{"name", "service", "unit", "points"}``."""
        ...

    def logs(self, service: str, level: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent log lines of a service, newest first, at most MAX_LOG_LINES.

        An unknown service or level raises ObservationError naming the known ones: an
        empty list must mean "nothing logged", never "you asked for the wrong thing".
        """
        ...

    def changes(self, service: str) -> list[dict[str, Any]]:
        """Return the recent deployments and configuration changes of a service, newest first.

        An unknown service raises ObservationError; a known one without changes returns [].
        """
        ...
