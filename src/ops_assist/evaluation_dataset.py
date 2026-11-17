"""Offline, versioned incident evaluation manifest."""

import hashlib
import json
import re
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent / "data"
MANIFEST = DATA / "eval" / "dataset.yaml"
PUBLISHED = DATA / "eval" / "published.yaml"
RECORDING_FILES = (
    "incident.json",
    "alerts.json",
    "metrics.json",
    "logs.jsonl",
    "changes.json",
    "expected.json",
)


def checksum(dataset: dict, root: Path = DATA) -> str:
    """Hash manifest cases and all six files of each recording, including answer keys."""
    recordings = {}
    for case in dataset["incidents"]:
        directory = root / "incidents" / case["id"]
        recordings[case["id"]] = {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in sorted(RECORDING_FILES)
        }
    payload = {key: dataset[key] for key in ("version", "created", "changelog", "incidents")}
    payload["recordings"] = recordings
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def load_dataset(path: Path = MANIFEST, root: Path = DATA, registry: Path = PUBLISHED) -> dict:
    """Load and validate the manifest before exposing its list of cases."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {
        "version",
        "created",
        "changelog",
        "incidents",
        "checksum",
    }:
        raise ValueError("invalid dataset fields")
    if not isinstance(data["version"], str) or not re.fullmatch(r"\d+\.\d+\.\d+", data["version"]):
        raise ValueError("invalid dataset version")
    from datetime import date

    try:
        date.fromisoformat(str(data["created"]))
    except ValueError as exc:
        raise ValueError("invalid dataset creation date") from exc
    changes = data["changelog"]
    if (
        not isinstance(changes, list)
        or not changes
        or any(
            not isinstance(c, dict)
            or set(c) != {"version", "description"}
            or not all(isinstance(v, str) and v.strip() for v in c.values())
            for c in changes
        )
        or changes[-1]["version"] != data["version"]
    ):
        raise ValueError("invalid dataset changelog")
    cases = data["incidents"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("empty dataset")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"id", "question", "expected"}:
            raise ValueError("invalid case")
        ident = case["id"]
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ident):
            raise ValueError("invalid incident id")
        if ident in ids or not isinstance(case["question"], str) or not case["question"].strip():
            raise ValueError("duplicate incident or empty question")
        if case["expected"] != f"../incidents/{ident}/expected.json":
            raise ValueError("invalid expected file")
        ids.add(ident)
    if not isinstance(data["checksum"], str) or data["checksum"] != checksum(data, root):
        raise ValueError("dataset checksum mismatch: update version and checksum")
    published = yaml.safe_load(registry.read_text(encoding="utf-8"))
    if not isinstance(published, dict) or any(
        not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for version, digest in published.items()
    ):
        raise ValueError("invalid published dataset registry")
    published_checksum = published.get(data["version"])
    if published_checksum is not None and published_checksum != data["checksum"]:
        raise ValueError("published dataset version has changed: bump the version")
    return data
