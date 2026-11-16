"""ops-assist: an open-source incident investigation agent built with Google ADK."""

import os

# LiteLLM downloads its model cost map from the internet at import time unless told
# otherwise. ops-assist must run offline (replayed incidents, local models), so use
# the copy bundled with the package. Set before anything imports litellm.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

__version__ = "0.1.0"
