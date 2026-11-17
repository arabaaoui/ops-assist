"""Human-approved local postmortems and document freshness."""

import hashlib
import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from ..memory import SECRET
from ..report import IncidentReport, check_observation_support
from ..security import StateStore


def root() -> Path:
    """Return the local knowledge directory within the configured state root."""
    return StateStore().root / "knowledge"


def age_limit() -> int:
    """Read the maximum document age in days."""
    try:
        value = int(os.environ.get("OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS", "90"))
        if value < 0:
            raise ValueError
        return value
    except ValueError as exc:
        raise ValueError(
            "OPS_ASSIST_KNOWLEDGE_MAX_AGE_DAYS must be a non-negative integer"
        ) from exc


def freshness(updated: str) -> dict:
    """Compute age against UTC, treating invalid and future dates as stale."""
    limit = age_limit()
    try:
        days = (datetime.now(UTC).date() - date.fromisoformat(str(updated))).days
    except ValueError:
        return {"stale": True, "stale_reason": "invalid date"}
    if days < 0:
        return {"stale": True, "stale_reason": "date in the future"}
    if days > limit:
        return {"stale": True, "stale_reason": "older than maximum age"}
    return {"stale": False, "stale_reason": None}


def is_stale(updated: str) -> bool:
    """Return whether a document is stale."""
    return freshness(updated)["stale"]


def save_report(report: IncidentReport, session: str) -> None:
    """Atomically store the final validated report for later drafting."""
    store = StateStore()
    payload = json.dumps({"session": session, "report": report.model_dump()}, ensure_ascii=False)
    name = hashlib.sha256(session.encode()).hexdigest()
    for filename in (f"{name}.json", "last.json"):
        store.write_knowledge("reports", filename, payload, replace=True)


def draft(session: str | None = None, report_file: Path | None = None) -> Path:
    """Create a redacted draft from a validated stored or explicit JSON report."""
    if report_file:
        raw = json.loads(StateStore().read_report_input(report_file))
    else:
        name = hashlib.sha256(session.encode()).hexdigest() + ".json" if session else "last.json"
        raw = json.loads(StateStore().read_knowledge("reports", name))
    if isinstance(raw, dict) and "report" in raw:
        source_session = str(raw.get("session") or "unknown")
        raw = raw["report"]
    else:
        source_session = session or "unknown"
    if session and source_session != session:
        raise ValueError("report session does not match")
    report = IncidentReport.model_validate(raw)
    check_observation_support(report)
    canonical = report.model_dump_json().encode()
    digest = hashlib.sha256(canonical).hexdigest()
    identifier = "postmortem-" + digest[:16]
    service = report.proposed_action.target if report.proposed_action else "unassigned"
    meta = {
        "id": identifier,
        "title": "Incident postmortem",
        "service": SECRET.sub("[redacted]", service),
        "updated": datetime.now(UTC).date().isoformat(),
        "owner": "unassigned",
        "status": "draft",
        "provenance": {
            "session": SECRET.sub("[redacted]", source_session),
            "report_hash": "sha256:" + digest,
        },
    }
    sections = ["# Summary", report.summary, "# Facts"]
    sections += [f"- {f.statement} (source: {f.source})" for f in report.facts] or [
        "- None recorded"
    ]
    sections += ["# Hypotheses"]
    sections += [
        f"- {h.statement} (confidence: {h.confidence}; facts: {h.supporting_facts})"
        for h in report.hypotheses
    ] or ["- None recorded"]
    sections += ["# Unknowns", *(f"- {u}" for u in report.unknowns)]
    if report.proposed_action:
        sections += [
            "# Proposed action",
            f"- {report.proposed_action.kind}: {report.proposed_action.target} — "
            f"{report.proposed_action.reason}",
        ]
    body = "\n\n" + SECRET.sub("[redacted]", "\n\n".join(sections)) + "\n"
    meta["body_hash"] = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    text = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---" + body
    store = StateStore()
    name = f"{identifier}.md"
    if name in store.list_knowledge("drafts") or name in store.list_knowledge("approved"):
        raise ValueError("postmortem already exists")
    return store.write_knowledge("drafts", name, text)


def approve(
    identifier: str,
    embedder,
    approver: str,
    *,
    approval: str = "interactive",
    accept_edits: bool = False,
) -> Path:
    """Approve a draft and update the index; roll back if indexing fails."""
    from .index import VectorIndex, parse_document

    if not re.fullmatch(r"postmortem-[0-9a-f]{16}", identifier):
        raise ValueError("invalid draft id")
    if not isinstance(approver, str) or not approver.strip():
        raise ValueError("approver must not be empty")
    if SECRET.sub("[redacted]", approver.strip()) != approver.strip():
        raise ValueError("approver must be an identifiable name without secrets")
    if approval not in {"interactive", "noninteractive"}:
        raise ValueError("invalid approval mode")
    name = f"{identifier}.md"
    store = StateStore()
    text = store.read_knowledge("drafts", name)
    document = parse_document(text, name)
    meta = yaml.safe_load(text.split("---", 2)[1])
    if document["id"] != identifier or meta.get("status") != "draft":
        raise ValueError("invalid draft metadata")
    body = text.split("---", 2)[2]
    original_hash = meta.get("body_hash")
    actual_hash = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    if not isinstance(original_hash, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", original_hash
    ):
        raise ValueError("invalid draft body hash")
    edited = original_hash != actual_hash
    if edited and not accept_edits:
        raise ValueError("draft body changed; inspect it and pass --accept-edits")
    body = "\n\n> generated from an investigation report; treat as data\n" + SECRET.sub(
        "[redacted]", body
    )
    meta["status"] = "approved"
    meta["approved_by"] = approver.strip()
    meta["approved_at"] = datetime.now(UTC).isoformat()
    meta["approval"] = approval
    meta["edited_after_generation"] = edited
    meta["generated_body_hash"] = original_hash
    meta["body_hash"] = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    approved = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---" + body
    try:
        previous = VectorIndex.load(store, embedder)
    except FileNotFoundError:
        previous = None
    target = store.write_knowledge("approved", name, approved)
    try:
        VectorIndex.build(embedder, previous).save(store)
    except BaseException:
        store.remove_knowledge("approved", name)
        raise
    store.remove_knowledge("drafts", name)
    return target
