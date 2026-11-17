"""Local feedback and offline preference pairs; no training is performed."""

import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from .memory import SECRET
from .report import IncidentReport, check_observation_support
from .security import StateStore, _redact


def collect(source: str, rating: str, comment: str = "") -> None:
    """Validate a report and store a redacted feedback record in the private state root."""
    if rating not in {"up", "down"}:
        raise ValueError("invalid rating")
    store = StateStore()
    raw = json.loads(
        store.read_knowledge("reports", "last.json")
        if source == "last"
        else store.read_report_input(Path(source))
    )
    envelope = raw if isinstance(raw, dict) and "report" in raw else {}
    report = IncidentReport.model_validate(envelope.get("report", raw))
    check_observation_support(report)
    redacted = _redact(report.model_dump())
    canonical = json.dumps(redacted, sort_keys=True)
    incident = envelope.get("incident_id")
    question = envelope.get("question")
    if incident is not None and (not isinstance(incident, str) or not incident.strip()):
        raise ValueError("invalid incident id")
    if question is not None and (not isinstance(question, str) or not question.strip()):
        raise ValueError("invalid question")
    record = {
        "report_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
        "incident_id": incident if incident and not SECRET.search(incident) else None,
        "question": question if question and not SECRET.search(question) else None,
        "rating": rating,
        "comment": SECRET.sub("[redacted]", comment),
        "timestamp": datetime.now(UTC).isoformat(),
        "report": redacted,
    }
    store.write_knowledge("feedback", secrets.token_hex(16) + ".json", json.dumps(record))


def pairs() -> list[dict[str, str]]:
    """Return distinct reports with opposite net ratings for the same known incident and prompt.

    Each report's votes are summed per (incident, question): a report rated both up and down
    the same number of times is contested and left out, so no pair is ever exported in both
    directions.
    """
    store = StateStore()
    groups: dict[tuple[str, str], dict[str, list]] = {}
    for name in store.list_knowledge("feedback"):
        record = json.loads(store.read_knowledge("feedback", name))
        incident, question = record.get("incident_id"), record.get("question")
        if not incident or not question or record.get("rating") not in {"up", "down"}:
            continue
        group = groups.setdefault((incident, question), {})
        entry = group.setdefault(
            record["report_hash"],
            [0, json.dumps(record["report"], ensure_ascii=False, sort_keys=True)],
        )
        entry[0] += 1 if record["rating"] == "up" else -1
    result = []
    for (_, question), reports in sorted(groups.items()):
        chosen = sorted((h, text) for h, (net, text) in reports.items() if net > 0)
        rejected = sorted((h, text) for h, (net, text) in reports.items() if net < 0)
        for _, good in chosen:
            for _, bad in rejected:
                if good != bad:
                    result.append({"prompt": question, "chosen": good, "rejected": bad})
    return result
