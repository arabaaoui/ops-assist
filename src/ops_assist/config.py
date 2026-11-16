"""Settings: which model profile, which models, which incident to replay.

Everything is read from environment variables over the bundled ``profiles.yaml``,
so the same code runs from a clone, from an installed wheel, in CI and in a
container without edits. A malformed profile or override is refused with a
message that names the file, never silently repaired.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml

DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILES_FILE = DATA_DIR / "profiles.yaml"


@dataclass(frozen=True)
class Settings:
    """Resolved settings for one process."""

    profile: str
    models: list[str]
    api_base: str | None = None
    incident: str = "payment-latency"
    session_db: str | None = None

    def describe(self) -> str:
        """One line for the startup log: what will actually be called."""
        where = ""
        if self.api_base:
            url = urlsplit(self.api_base)
            host = url.netloc.rsplit("@", 1)[-1]
            safe_base = urlunsplit((url.scheme, host, url.path, "", ""))
            where = f" via {safe_base}"
        return f"profile={self.profile} models={self.models}{where} incident={self.incident}"


def _load_profiles(path: Path) -> dict[str, dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"{path}: expected a non-empty 'profiles' mapping")
    for name, p in profiles.items():
        if not isinstance(p, dict):
            raise ValueError(f"{path}: profile {name!r} must be a mapping")
        models = p.get("models", [])
        if not isinstance(models, list) or not all(isinstance(m, str) and m for m in models):
            raise ValueError(f"{path}: profile {name!r}: 'models' must be a list of model ids")
    return profiles


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build the settings from the environment and the profiles file; refuse anything unclear."""
    env = dict(os.environ if env is None else env)
    path = Path(env.get("OPS_ASSIST_PROFILES_FILE") or PROFILES_FILE)
    profiles = _load_profiles(path)
    name = env.get("OPS_ASSIST_PROFILE", "").strip() or "local"
    if name not in profiles:
        raise ValueError(f"unknown profile {name!r}; known profiles: {sorted(profiles)}")
    profile = profiles[name]

    if "OPS_ASSIST_MODELS" in env:
        models = [m.strip() for m in env["OPS_ASSIST_MODELS"].split(",") if m.strip()]
        if not models:
            raise ValueError("OPS_ASSIST_MODELS is set but lists no model id")
        # Overridden models do not inherit the profile's endpoint: an Ollama address
        # sent to a hosted model would fail in a confusing way.
        api_base = env.get("OPS_ASSIST_API_BASE") or None
    else:
        models = list(profile.get("models", []))
        if not models:
            raise ValueError(f"profile {name!r} defines no model and OPS_ASSIST_MODELS is not set")
        api_base = (
            env["OPS_ASSIST_API_BASE"] or None
            if "OPS_ASSIST_API_BASE" in env
            else profile.get("api_base")
        )
    return Settings(
        profile=name,
        models=models,
        api_base=api_base,
        incident=env.get("OPS_ASSIST_INCIDENT", "").strip() or "payment-latency",
        session_db=env.get("OPS_ASSIST_SESSION_DB") or None,
    )
