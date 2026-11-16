"""Shared HTTP handling for read-only observation APIs."""

import httpx

from .base import ObservationError


class HttpSource:
    """A synchronous HTTP source with a bounded request time."""

    def __init__(self, url: str, timeout: float = 5, client: httpx.Client | None = None):
        """Configure a base URL and optionally inject a client for offline tests."""
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.client = client or httpx.Client()

    def _get(self, path, params=None):
        try:
            response = self.client.get(self.url + path, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get("status") != "success":
                raise ValueError("API returned an unsuccessful status")
            return data["data"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ObservationError(f"observation API request failed: {type(exc).__name__}") from exc

    def alerts(self):
        """Alerts are unavailable from this source."""
        raise ObservationError("alerts are not supported by this source")

    def metric(self, name, service):
        """Metrics are unavailable from this source."""
        raise ObservationError("metrics are not supported by this source")

    def logs(self, service, level=None, limit=50):
        """Report that logs are unavailable."""
        raise ObservationError("logs are not supported by this source")

    def changes(self, service):
        """Report that changes are unavailable."""
        raise ObservationError(
            "changes are not supported by this source; configure an explicit changes file"
        )
