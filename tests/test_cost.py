import asyncio
import json
import socket
from dataclasses import replace

import litellm
import pytest
from google.adk.models.lite_llm import _get_completion_inputs
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm.integrations.anthropic_cache_control_hook import AnthropicCacheControlHook
from test_agent_loop import ScriptedModel

from ops_assist import cli
from ops_assist.agent import INSTRUCTION
from ops_assist.config import load_settings
from ops_assist.cost import call_cost, price_for, scripted_costs
from ops_assist.models import build_model
from ops_assist.run import investigate


class PrefixModel(ScriptedModel):
    prefixes: list = []

    async def generate_content_async(self, llm_request, stream=False):
        messages, tools, *_ = await _get_completion_inputs(llm_request, "openai/gpt-4o-mini")
        self.prefixes.append(
            (
                json.dumps(messages[0]).encode(),
                json.dumps(tools).encode(),
            )
        )
        assert messages[0]["role"] == "system"
        assert INSTRUCTION.strip() in messages[0]["content"]
        assert tools and all(tool["type"] == "function" for tool in tools)
        async for response in super().generate_content_async(llm_request, stream):
            yield response


def test_instruction_and_tools_stable_across_investigation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))
    model = PrefixModel(seen=[], prefixes=[])
    investigate("Why?", model=model, save_memory=False)
    assert len(model.prefixes) >= 2
    assert all(prefix == model.prefixes[0] for prefix in model.prefixes[1:])


def test_trace_marks_missing_usage_and_omitted_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))
    monkeypatch.setattr("ops_assist.run.MAX_TRACE_CALLS", 1)
    _, trace = investigate("Why?", model=ScriptedModel(seen=[]), save_memory=False)
    assert len(trace.usage) == 1 and trace.omitted_usage == 1
    assert trace.usage[0]["input_tokens"] is None
    assert trace.usage[0]["cached_input_tokens"] is None
    assert trace.usage[0]["output_tokens"] is None


@pytest.mark.parametrize("setting,enabled", [("on", True), ("off", False)])
def test_anthropic_cache_injection_reaches_litellm(setting, enabled):
    settings = load_settings(
        {"OPS_ASSIST_MODELS": "anthropic/claude-haiku-4-5", "OPS_ASSIST_PROMPT_CACHE": setting}
    )
    model = build_model(settings)
    calls = []

    class Client:
        async def acompletion(self, **kwargs):
            calls.append(kwargs)
            return litellm.ModelResponse(
                choices=[
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ]
            )

    model.llm_client = Client()
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        config=types.GenerateContentConfig(system_instruction="stable"),
    )

    async def run():
        return [response async for response in model.generate_content_async(request)]

    asyncio.run(run())
    assert calls[0]["metadata"]["agent_name"] == "ops_assist"
    points = calls[0].get("cache_control_injection_points")
    assert points == (
        [{"location": "message", "role": "system", "control": {"type": "ephemeral"}}]
        if enabled
        else None
    )
    if enabled:
        _, marked, _ = AnthropicCacheControlHook().get_chat_completion_prompt(
            model="anthropic/claude-haiku-4-5",
            messages=calls[0]["messages"],
            non_default_params={"cache_control_injection_points": points},
            prompt_id=None,
            prompt_variables=None,
            dynamic_callback_params={},
        )
        assert marked[0]["cache_control"] == {"type": "ephemeral"}


def test_prompt_cache_setting_validation():
    assert load_settings({}).prompt_cache
    assert not load_settings({"OPS_ASSIST_PROMPT_CACHE": "off"}).prompt_cache
    with pytest.raises(ValueError, match="OPS_ASSIST_PROMPT_CACHE"):
        load_settings({"OPS_ASSIST_PROMPT_CACHE": "maybe"})
    model = build_model(load_settings({"OPS_ASSIST_MODELS": "openai/gpt-4o-mini"}))
    assert "cache_control_injection_points" not in model._additional_args
    unknown = build_model(load_settings({"OPS_ASSIST_MODELS": "anthropic/unknown-model"}))
    assert "cache_control_injection_points" not in unknown._additional_args


PRICE = {
    "input_cost_per_token": 2.0,
    "output_cost_per_token": 4.0,
    "cache_read_input_token_cost": 0.5,
    "cache_creation_input_token_cost": 3.0,
    "supports_prompt_caching": True,
}


def test_cost_arithmetic_and_unknowns():
    assert call_cost({"input": 100, "output": 10, "cached": 30, "write": 20}, PRICE) == 215
    assert (
        call_cost(
            {"input": 100, "output": 10, "cached": 30, "write": 20}, {"input_cost_per_token": 2}
        )
        is None
    )
    assert call_cost({"input": 10, "output": 0, "cached": 11, "write": 0}, PRICE) is None
    assert price_for("anthropic/model", {"model": {"litellm_provider": "openai"}}) is None


def test_scenarios_compare_cache_and_fast_and_unknown():
    settings = replace(load_settings({}), models=["anthropic/main"], fast_models=["anthropic/fast"])
    dataset = {"incidents": [{"id": "fiction"}]}
    prices = {"anthropic/main": PRICE, "anthropic/fast": {**PRICE, "input_cost_per_token": 1.0}}
    row = scripted_costs(settings, prices=prices, dataset=dataset)[0]
    assert row["cache_on_fast_off"] < row["cache_off_fast_off"]
    assert row["cache_off_fast_on"] < row["cache_off_fast_off"]
    assert row["cache_on_fast_on"] < row["cache_off_fast_on"]
    assert scripted_costs(settings, prices={}, dataset=dataset)[0]["cache_off_fast_off"] is None
    incomplete = dict(PRICE)
    incomplete.pop("cache_creation_input_token_cost")
    assert (
        scripted_costs(settings, prices={"anthropic/main": incomplete}, dataset=dataset)[0][
            "cache_on_fast_off"
        ]
        is None
    )


def test_no_fast_tier_and_provider_cache(capsys, monkeypatch):
    settings = replace(
        load_settings({}), models=["bedrock/example"], fast_models=["bedrock/example"]
    )
    row = scripted_costs(
        settings, prices={"bedrock/example": PRICE}, dataset={"incidents": [{"id": "x"}]}
    )[0]
    assert row["cache_off_fast_on"] is None
    assert row["reasons"]["cache_off_fast_on"] == "no distinct fast tier"
    assert row["cache_on_fast_off"] == row["cache_off_fast_off"]
    assert "bedrock/example" in row["notes"][0]
    monkeypatch.setenv("OPS_ASSIST_MODELS", "bedrock/example")
    assert cli.main(["eval", "cost"]) == 0
    assert "n/a (no distinct fast tier)" in capsys.readouterr().out
    assert cli.main(["eval", "cost", "--json"]) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert row["cache_off_fast_on"] is None and row["reasons"]["cache_off_fast_on"]


def test_zero_rates_and_vertex_lookup(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("network called"))
    usage = {"input": 10, "output": 1, "cached": 0, "write": 0}
    assert call_cost(usage, {"input_cost_per_token": 0, "output_cost_per_token": 1}) is None
    assert call_cost(usage, price_for("ollama/example", {})) == 0
    model = load_settings({"OPS_ASSIST_PROFILE": "vertex"}).models[0]
    assert price_for(model, litellm.model_cost)["input_cost_per_token"] > 0
    assert price_for("vertex_ai/nonexistent-xyz", litellm.model_cost) is None


def test_cost_cli_is_offline(monkeypatch, capsys):
    monkeypatch.setenv("OPS_ASSIST_MODELS", "unknown/model")
    monkeypatch.setattr(litellm, "completion", lambda **kwargs: pytest.fail("model called"))
    monkeypatch.setattr(litellm, "embedding", lambda **kwargs: pytest.fail("embedding called"))
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("network called"))
    assert cli.main(["eval", "cost"]) == 0
    out = capsys.readouterr().out
    assert "unknown" in out and "payment-latency" in out
    assert cli.main(["eval", "cost", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert all(row["cache_off_fast_off"] is None for row in rows)
