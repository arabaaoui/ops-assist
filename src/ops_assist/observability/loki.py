"""Read bounded log streams from the Loki HTTP API."""

import json
import time
from datetime import UTC, datetime

from .base import LOG_LEVELS, MAX_LOG_LINES, ObservationError
from .http import HttpSource


class LokiSource(HttpSource):
    """Loki observations over the last hour, using service and level labels."""

    name = "loki"
    capabilities = frozenset({"logs"})

    def logs(self, service, level=None, limit=50):
        """Return newest log lines; distinguish an unknown service from an empty filter."""
        if level is not None and level not in LOG_LEVELS:
            raise ObservationError(f"unknown level {level!r}; use one of {list(LOG_LEVELS)}")
        if limit < 1:
            raise ObservationError("limit must be at least 1")
        end = time.time_ns()
        selector = "{service=" + json.dumps(service)
        if level is not None:
            selector += ",level=" + json.dumps(level)
        params = {
            "query": selector + "}",
            "start": end - 3600 * 10**9,
            "end": end,
            "limit": MAX_LOG_LINES,
            "direction": "backward",
        }
        try:
            streams = self._get("/loki/api/v1/query_range", params)["result"]
            streams = [s for s in streams if s["stream"].get("service") == service]
            if not streams:
                known = self._get("/loki/api/v1/label/service/values")
                if not isinstance(known, list) or not all(isinstance(x, str) for x in known):
                    raise ValueError("invalid service label response")
                if service not in known:
                    raise ObservationError(
                        f"unknown service {service!r}; known services: {sorted(known)}"
                    )
                return []
            lines = [
                {
                    "ts": datetime.fromtimestamp(int(ts) / 10**9, UTC).isoformat(),
                    "service": service,
                    "level": stream["stream"].get("level", "info"),
                    "message": message,
                    "source": "loki/logs",
                }
                for stream in streams
                for ts, message in stream["values"]
            ]
            lines.sort(key=lambda x: x["ts"], reverse=True)
            return [x for x in lines if level is None or x["level"] == level][
                : min(limit, MAX_LOG_LINES)
            ]
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ObservationError("invalid Loki logs response") from exc
