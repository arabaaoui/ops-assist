"""Generate a deterministic fictional alert classification dataset offline."""

import json
from pathlib import Path

ALERTS = Path(__file__).resolve().parent / "alerts.json"
LABELS = {
    "HttpErrorsHigh": "http_errors",
    "ErrorRateElevated": "http_errors",
    "MemoryLookupMissHigh": "cache_misses",
    "TLSHandshakeFailuresHigh": "tls_failures",
    "DiskUsageHigh": "disk_usage",
    "HighLatencyP95": "latency",
}
TRAIN_TEMPLATES = (
    "Alert {name} on {service}: {summary}",
    "Service {service} reports {name}. Details: {summary}",
    "Observation for {service}: {name}; {summary}",
)
TEST_TEMPLATE = "For {service}, {name} was observed. {summary}"


def make_dataset() -> dict[str, list[dict[str, str]]]:
    """Build train and test examples from dedicated fictional alerts and distinct templates."""
    dataset: dict[str, list[dict[str, str]]] = {"train": [], "test": []}
    for alert in json.loads(ALERTS.read_text(encoding="utf-8")):
        label = LABELS[alert["name"]]
        for template in TRAIN_TEMPLATES:
            dataset["train"].append({"text": template.format(**alert), "label": label})
        dataset["test"].append({"text": TEST_TEMPLATE.format(**alert), "label": label})
    return dataset


if __name__ == "__main__":
    print(json.dumps(make_dataset(), ensure_ascii=False, indent=2))
