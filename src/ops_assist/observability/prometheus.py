"""Read alerts and time series from the Prometheus HTTP API."""

import json
import math
import re
import time
from datetime import UTC, datetime

from .base import ObservationError
from .http import HttpSource


class PrometheusSource(HttpSource):
    """Prometheus observations over the last hour."""

    name = "prometheus"
    capabilities = frozenset({"alerts", "metric"})

    def alerts(self):
        """Return firing alerts with their labels and provenance."""
        try:
            alerts = self._get("/api/v1/alerts")["alerts"]
            return [
                {
                    "id": a["labels"].get("alertname", "") + ":" + a["labels"].get("service", ""),
                    "name": a["labels"].get("alertname", ""),
                    "service": a["labels"].get("service", ""),
                    "severity": a["labels"].get("severity", "unknown"),
                    "since": a["activeAt"],
                    "source": "prometheus/alerts",
                }
                for a in alerts
                if a.get("state") == "firing"
            ]
        except (KeyError, TypeError) as exc:
            raise ObservationError("invalid Prometheus alerts response") from exc

    def metric(self, name, service):
        """Return one series; reject ambiguous or absent series."""
        if not re.fullmatch(r"[a-zA-Z_:][a-zA-Z0-9_:]*", name):
            raise ObservationError("invalid metric name")
        end = time.time()
        query = f"{name}{{service={json.dumps(service)}}}"
        try:
            result = self._get(
                "/api/v1/query_range", {"query": query, "start": end - 3600, "end": end, "step": 60}
            )["result"]
            matching = [s for s in result if s["metric"].get("service") == service]
            if len(matching) != 1:
                raise ObservationError(
                    f"expected one series for {name!r} and {service!r}; got {len(matching)}"
                )
            points = []
            for ts, value in matching[0]["values"]:
                value = float(value)
                if math.isfinite(value):
                    points.append([datetime.fromtimestamp(float(ts), UTC).isoformat(), value])
            return {
                "name": name,
                "service": service,
                "unit": "unknown",
                "points": points,
                "source": f"prometheus/metrics/{name}",
            }
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ObservationError("invalid Prometheus metric response") from exc
