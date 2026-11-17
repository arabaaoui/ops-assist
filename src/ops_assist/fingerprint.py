"""Stable identifier for the versioned inputs to investigation behaviour."""

import hashlib
import json
from pathlib import Path

from .config import Settings
from .evaluation_dataset import load_dataset
from .report import IncidentReport

PACKAGE = Path(__file__).resolve().parent
# Bump whenever the evaluation scoring logic changes.
SCORER_VERSION = "1"


def fingerprint(settings: Settings) -> str:
    """Hash canonical behaviour inputs, excluding credentials and endpoint values."""
    files = sorted((PACKAGE / "prompts").rglob("*.md")) + sorted(
        (PACKAGE / "skills").rglob("SKILL.md")
    )
    inputs = {
        "files": {str(p.relative_to(PACKAGE)): p.read_text(encoding="utf-8") for p in files},
        "profile": settings.profile,
        "models": settings.models,
        "fast_models": settings.fast_models or settings.models,
        "deterministic": settings.deterministic,
        "report_schema": IncidentReport.model_json_schema(),
        "scorer_version": SCORER_VERSION,
        "dataset_version": load_dataset()["version"],
    }
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
