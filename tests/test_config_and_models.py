import asyncio

import litellm
import pytest
from google.adk.models import FallbackModel
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from ops_assist.config import load_settings
from ops_assist.models import build_model


def test_local_is_the_default_profile():
    s = load_settings(env={})
    assert s.profile == "local" and s.api_base and s.models


def test_models_can_be_overridden_without_editing_code():
    s = load_settings(env={"OPS_ASSIST_PROFILE": "api", "OPS_ASSIST_MODELS": "a/one, b/two"})
    assert s.models == ["a/one", "b/two"] and s.api_base is None


def test_an_unknown_profile_is_refused():
    with pytest.raises(ValueError, match="unknown profile"):
        load_settings(env={"OPS_ASSIST_PROFILE": "nope"})


def test_one_model_is_used_as_is():
    m = build_model(load_settings(env={"OPS_ASSIST_MODELS": "ollama_chat/x"}))
    assert isinstance(m, LiteLlm) and m.model == "ollama_chat/x"


def test_several_models_build_a_fallback_chain_in_order():
    m = build_model(
        load_settings(env={"OPS_ASSIST_PROFILE": "api", "OPS_ASSIST_MODELS": "p/a,p/b"})
    )
    assert isinstance(m, FallbackModel)
    assert [x.model for x in m.models] == ["p/a", "p/b"]


def test_the_profiles_ship_inside_the_package():
    from ops_assist.config import PROFILES_FILE

    assert PROFILES_FILE.is_file() and "ops_assist" in PROFILES_FILE.parts


def test_a_profile_without_models_is_refused(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("profiles:\n  empty:\n    models: []\n")
    with pytest.raises(ValueError, match="defines no model"):
        load_settings(env={"OPS_ASSIST_PROFILES_FILE": str(f), "OPS_ASSIST_PROFILE": "empty"})


def test_the_local_profile_sends_requests_to_its_endpoint():
    m = build_model(load_settings(env={}))
    assert m._additional_args["api_base"] == "http://localhost:11434"


def test_overridden_models_do_not_inherit_the_profile_endpoint():
    s = load_settings(env={"OPS_ASSIST_MODELS": "gemini/x"})
    assert s.api_base is None
    assert "api_base" not in build_model(s)._additional_args


def test_an_empty_override_is_refused_not_ignored():
    with pytest.raises(ValueError, match="lists no model"):
        load_settings(env={"OPS_ASSIST_MODELS": " , "})


def test_a_scalar_models_entry_is_refused(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("profiles:\n  bad:\n    models: ollama_chat/qwen3:8b\n")
    with pytest.raises(ValueError, match="must be a list"):
        load_settings(env={"OPS_ASSIST_PROFILES_FILE": str(f), "OPS_ASSIST_PROFILE": "bad"})


# -- the fallback chain, exercised without network ------------------------------


class _Client:
    """Stands in for the HTTP client of one LiteLlm: fails with `error`, or answers `text`."""

    def __init__(self, error=None, text=""):
        self.error, self.text, self.calls = error, text, 0

    async def acompletion(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return litellm.ModelResponse(
            choices=[
                {"message": {"role": "assistant", "content": self.text}, "finish_reason": "stop"}
            ]
        )


def _ask(model) -> str:
    request = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="hi")])])

    async def go():
        return [r async for r in model.generate_content_async(request)]

    responses = asyncio.run(go())
    return "".join(p.text or "" for r in responses for p in (r.content.parts or []))


def _chain(first_error):
    model = build_model(load_settings(env={"OPS_ASSIST_MODELS": "p/a,p/b"}))
    a, b = _Client(error=first_error), _Client(text="answer from b")
    model.models[0].llm_client, model.models[1].llm_client = a, b
    return model, a, b


def test_a_rate_limited_primary_falls_back_to_the_next_model():
    model, a, b = _chain(litellm.RateLimitError("slow down", llm_provider="p", model="p/a"))
    assert _ask(model) == "answer from b" and (a.calls, b.calls) == (1, 1)


def test_a_malformed_request_does_not_fall_back():
    model, a, b = _chain(litellm.BadRequestError("bad request", model="p/a", llm_provider="p"))
    with pytest.raises(litellm.BadRequestError):
        _ask(model)
    assert b.calls == 0


def test_empty_variables_fall_back_to_the_defaults():
    s = load_settings(env={"OPS_ASSIST_PROFILE": " ", "OPS_ASSIST_INCIDENT": ""})
    assert s.profile == "local" and s.incident == "payment-latency"
