"""ops-assist: an open-source incident investigation agent built with Google ADK."""

import os

# LiteLLM downloads its model cost map from the internet at import time unless told
# otherwise. ops-assist must run offline (replayed incidents, local models), so use
# the copy bundled with the package. Set before anything imports litellm.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

__version__ = "1.0.0"


def call_metadata(agent_name: str, profile: str | None = None) -> dict[str, str]:
    """Identify a LiteLLM call without including prompt data or credentials."""
    return {
        "agent_name": agent_name,
        "profile": profile or os.environ.get("OPS_ASSIST_PROFILE", "").strip() or "local",
        "ops_assist_version": __version__,
    }
