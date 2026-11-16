"""Compose independent observation sources."""

from .base import ObservationSource


class CompositeSource:
    """Delegate metrics and alerts, logs, and changes to their respective sources."""

    name = "composite"
    capabilities = frozenset({"alerts", "metric", "logs", "changes"})

    def __init__(
        self, metrics: ObservationSource, logs: ObservationSource, changes: ObservationSource
    ):
        """Bind the three sources."""
        self.metrics, self.log_source, self.change_source = metrics, logs, changes

    def alerts(self):
        """Return metric-source alerts."""
        return self.metrics.alerts()

    def metric(self, name, service):
        """Return a metric-source series."""
        return self.metrics.metric(name, service)

    def logs(self, service, level=None, limit=50):
        """Return log-source lines."""
        return self.log_source.logs(service, level, limit)

    def changes(self, service):
        """Return changes from the configured source."""
        return self.change_source.changes(service)
