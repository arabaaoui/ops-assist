"""Settings: which model profile, which models, which incident to replay.

Everything is read from environment variables over the bundled ``profiles.yaml``,
so the same code runs from a clone, from an installed wheel, in CI and in a
container without edits. A malformed profile or override is refused with a
message that names the file, never silently repaired.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
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
    fast_models: list[str] = field(default_factory=list)
    api_base: str | None = None
    incident: str = "payment-latency"
    session_db: str | None = None
    requires_env: list[str] = field(default_factory=list)
    models_overridden: bool = False
    deterministic: bool = False

    def describe(self) -> str:
        """One line for the startup log: what will actually be called."""
        where = ""
        if self.api_base:
            url = urlsplit(self.api_base)
            host = url.netloc.rsplit("@", 1)[-1]
            safe_base = urlunsplit((url.scheme, host, url.path, "", ""))
            where = f" via {safe_base}"
        return (
            f"profile={self.profile} models={self.models} "
            f"fast_models={self.fast_models or self.models}{where} incident={self.incident}"
        )


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
        fast = p.get("fast_models", models)
        if (
            not isinstance(fast, list)
            or ("fast_models" in p and not fast)
            or not all(isinstance(m, str) and m.strip() for m in fast)
        ):
            raise ValueError(
                f"{path}: profile {name!r}: fast_models must be a non-empty list of model ids"
            )
        required = p.get("requires_env")
        if (
            not isinstance(required, list)
            or not all(
                isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                for key in required
            )
            or len(set(required)) != len(required)
        ):
            raise ValueError(
                f"{path}: profile {name!r}: requires_env must be a list of "
                "unique environment variable names"
            )
        if not isinstance(p.get("description"), str) or not p["description"].strip():
            raise ValueError(f"{path}: profile {name!r}: description must be a non-empty string")
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
    if "OPS_ASSIST_FAST_MODELS" in env:
        fast_models = [m.strip() for m in env["OPS_ASSIST_FAST_MODELS"].split(",") if m.strip()]
        if not fast_models:
            raise ValueError("OPS_ASSIST_FAST_MODELS is set but lists no model id")
    elif "OPS_ASSIST_MODELS" in env:
        fast_models = list(models)
    else:
        fast_models = list(profile.get("fast_models", models))
    return Settings(
        profile=name,
        models=models,
        fast_models=fast_models,
        api_base=api_base,
        incident=env.get("OPS_ASSIST_INCIDENT", "").strip() or "payment-latency",
        session_db=env.get("OPS_ASSIST_SESSION_DB") or None,
        requires_env=list(profile["requires_env"]),
        models_overridden="OPS_ASSIST_MODELS" in env,
    )


PROVIDER_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def missing_fast_keys(settings: Settings, env: dict[str, str]) -> list[str]:
    """Find missing credentials for known providers in the expert chain."""
    required = {
        PROVIDER_KEYS[provider]
        for model in settings.fast_models or settings.models
        if (provider := model.partition("/")[0].lower()) in PROVIDER_KEYS
    }
    return sorted(key for key in required if not env.get(key, "").strip())
