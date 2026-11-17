"""Deterministic evaluation of investigations against the bundled answer keys."""

import json
import os
import re
import secrets
import time
from dataclasses import replace

from .evaluation_dataset import DATA, load_dataset
from .observability import ReplaySource
from .report import IncidentReport, check_observation_support
from .run import investigate
from .security import StateStore, _redact


def _contains(text: str, value: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", text.casefold()))


# Conservative sentence-level lexical checks; these do not parse scope or meaning.
NEGATION = re.compile(
    r"\b(?:not|no|never|neither|nor|without|unlikely|ruled?\s+out|"
    r"exclud(?:e|es|ed|ing)|rather\s+than|instead\s+of|cannot|can't|isn't|wasn't|"
    r"doesn't|didn't|hasn't|haven't|weren't)\b",
    re.IGNORECASE,
)
SENTENCES = re.compile(r"(?<=[.!?])\s+|[\n;]+")
MAX_ABSTENTION_CONFIDENCE = 0.5
MAX_ERROR_LENGTH = 500


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCES.split(text) if part.strip()]


def _affirmative_tokens(text: str, tokens: list[str]) -> bool:
    return any(
        not NEGATION.search(sentence) and all(_contains(sentence, token) for token in tokens)
        for sentence in _sentences(text)
    )


def _word_forms(text: str) -> list[str]:
    # A small, explicit English inflection normalizer, not a stemmer or semantic model.
    irregular = {
        "ran": "run",
        "running": "run",
        "caused": "cause",
        "causes": "cause",
        "failed": "fail",
        "failure": "fail",
        "failures": "fail",
    }
    result = []
    for word in re.findall(r"[a-z0-9]+", text.casefold()):
        if word in irregular:
            word = irregular[word]
        elif len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 4 and word.endswith("ed"):
            word = word[:-2]
        elif len(word) > 4 and word.endswith("ing"):
            word = word[:-3]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        result.append(word)
    return result


def _forbidden_affirmed(text: str, phrase: str) -> bool:
    target = _word_forms(phrase)
    if not target:
        return False
    for sentence in _sentences(text):
        if NEGATION.search(sentence):
            continue
        words = _word_forms(sentence)
        if any(words[i : i + len(target)] == target for i in range(len(words))):
            return True
    return False


def score_report(report, expected: dict) -> dict[str, bool]:
    """Score structured hypotheses and conservative lexical sentence checks."""
    try:
        report = IncidentReport.model_validate(report)
        check_observation_support(report)
    except (ValueError, TypeError):
        return dict.fromkeys(("valid", "status", "root_cause", "sources", "forbidden"), False)

    status = expected["status"]
    if status == "root_cause_identified":
        retained = max(
            report.hypotheses, key=lambda hypothesis: hypothesis.confidence, default=None
        )
        matching = bool(retained) and _affirmative_tokens(
            retained.statement, [expected["root_cause_service"], expected["root_cause_change"]]
        )
    elif status == "hypotheses_only":
        matching = any(
            _affirmative_tokens(hypothesis.statement, [entry["service"], entry["change"]])
            for hypothesis in report.hypotheses
            for entry in expected.get("accepted_hypotheses", [])
        )
    else:
        matching = bool(any(unknown.strip() for unknown in report.unknowns)) and all(
            hypothesis.confidence <= MAX_ABSTENTION_CONFIDENCE for hypothesis in report.hypotheses
        )
    conclusions = [report.summary, *(h.statement for h in report.hypotheses)]
    return {
        "valid": True,
        "status": report.status == status,
        "root_cause": matching,
        "sources": all(
            any(
                re.search(r"(?:^|[/:])" + re.escape(source) + r"(?:$|[/:])", f.source.casefold())
                or re.search(
                    r"^get_" + ("metric" if source == "metrics" else source) + r"(?:\b|:)",
                    f.source.casefold(),
                )
                for f in report.facts
            )
            for source in expected["required_facts_sources"]
        ),
        "forbidden": not any(
            _forbidden_affirmed(text, phrase)
            for text in conclusions
            for phrase in expected["forbidden_conclusions"]
        ),
    }


def _check_tools_mode() -> None:
    if os.environ.get("OPS_ASSIST_TOOLS", "inprocess") == "mcp":
        raise ValueError("Evaluation does not support OPS_ASSIST_TOOLS=mcp; use inprocess")


def _save_result(result: dict) -> object:
    store = StateStore()
    name = "eval-" + secrets.token_hex(16) + ".json"
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=store.directory()
    )
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return store.root / name


def _evaluate(settings, repeat, *, model=None, compare=False):
    _check_tools_mode()
    if not 1 <= repeat <= 100:
        raise ValueError("repeat must be between 1 and 100")
    dataset = load_dataset()
    tiers = (
        {
            "main": replace(settings, fast_models=settings.models, deterministic=True),
            "fast": replace(settings, deterministic=True),
        }
        if compare
        else {"single": settings}
    )
    if compare == "fast":
        tiers.pop("main")
    totals = {
        name: {"rows": [], "tokens": 0, "approximate": 0, "unknown": 0, "duration": 0.0}
        for name in tiers
    }
    for case in dataset["incidents"]:
        expected = json.loads((DATA / "incidents" / case["id"] / "expected.json").read_text())
        for iteration in range(1, repeat + 1):
            for name, tier_settings in tiers.items():
                total = totals[name]
                started = time.monotonic()
                try:
                    report, trace = investigate(
                        case["question"],
                        settings=replace(tier_settings, incident=case["id"], session_db=None),
                        source=ReplaySource(case["id"], root=DATA / "incidents"),
                        model=model,
                        allow_writes=False,
                        save_memory=False,
                        **({"topology": "experts", "measure_usage": True} if compare else {}),
                    )
                    if compare:
                        total["tokens"] += trace.total_tokens
                        total["approximate"] += trace.approximate_calls
                        total["unknown"] += trace.unknown_calls
                    report = IncidentReport.model_validate(report)
                    check_observation_support(report)
                    checks = score_report(report, expected)
                    saved_report = _redact(report.model_dump(mode="json"))
                    error = None
                except Exception as exc:  # Failures count against the pass rate.
                    checks = dict.fromkeys(
                        ("valid", "status", "root_cause", "sources", "forbidden"), False
                    )
                    saved_report = None
                    error = _redact(f"{type(exc).__name__}: {exc}")[:MAX_ERROR_LENGTH]
                finally:
                    total["duration"] += time.monotonic() - started
                total["rows"].append(
                    {
                        "incident": case["id"],
                        "iteration": iteration,
                        "checks": checks,
                        "passed": all(checks.values()),
                        "error": error,
                        "report": saved_report,
                    }
                )
    results = {}
    for name, tier_settings in tiers.items():
        total = totals[name]
        rows = total["rows"]
        result = {
            "dataset_version": dataset["version"],
            "dataset_checksum": dataset["checksum"],
            "profile": settings.profile,
            "models": settings.models,
            "repeat": repeat,
            "pass_rate": sum(row["passed"] for row in rows) / len(rows),
            "results": rows,
        }
        if compare:
            result.update(
                total_tokens=total["tokens"],
                approximate_calls=total["approximate"],
                unknown_calls=total["unknown"],
                duration_seconds=total["duration"],
                fast_models=tier_settings.fast_models or tier_settings.models,
            )
        results[name] = (result, _save_result(result))
    return results


def evaluate(settings, repeat: int = 1, *, model=None, compare_tier: bool = False):
    """Run each replay in a fresh session, retaining failures in the denominator."""
    if compare_tier:
        # Preserve the original programmatic entry point for a single measured tier.
        return _evaluate(settings, repeat, model=model, compare="fast")["fast"]
    return _evaluate(settings, repeat, model=model)["single"]


def evaluate_tiers(settings, repeat: int = 1, *, model=None):
    """Compare main and fast experts in alternating incident/repetition order."""
    return _evaluate(settings, repeat, model=model, compare=True)
