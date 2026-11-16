"""Model routing: one LiteLLM-backed model per id, chained with ADK's FallbackModel.

The provider is a configuration choice. With a single id the model is used as-is;
with several, ADK's ``FallbackModel`` (experimental in ADK 2.14) tries the next one
when a call fails with HTTP 429, 500, 502, 503 or 504 before any output was produced.
It does not switch on a malformed request (4xx), on an error without a status (for
instance a connection error or a stopped Ollama), on a renamed model (404), nor once
the first chunk of an answer has been sent.
"""

from __future__ import annotations

from google.adk.models import FallbackModel
from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm

from .config import Settings


def build_model(settings: Settings) -> BaseLlm:
    """Return the model the agent will call, with its fallback chain if more than one id."""
    kwargs = {"api_base": settings.api_base} if settings.api_base else {}
    models = [LiteLlm(model=m, **kwargs) for m in settings.models]
    if len(models) == 1:
        return models[0]
    return FallbackModel(models=models)
