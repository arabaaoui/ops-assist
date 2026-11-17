"""Offline coverage of tier routing and comparison."""

import json
from dataclasses import replace

import pytest
from google.genai import types
from test_roles import RolesModel

from ops_assist import cli
from ops_assist.agent import build_agent
from ops_assist.config import load_settings
from ops_assist.evaluation import evaluate
from ops_assist.run import investigate


def test_fast_resolution_and_validation(tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        'profiles:\n  local:\n    models: ["main"]\n'
        '    fast_models: ["fast", "backup"]\n    description: Test\n    requires_env: []\n'
    )
    env = {"OPS_ASSIST_PROFILES_FILE": str(path)}
    settings = load_settings(env)
    assert settings.fast_models == ["fast", "backup"]
    assert load_settings({**env, "OPS_ASSIST_FAST_MODELS": " a, b "}).fast_models == ["a", "b"]
    assert load_settings({**env, "OPS_ASSIST_MODELS": "override"}).fast_models == ["override"]
    with pytest.raises(ValueError, match="OPS_ASSIST_FAST_MODELS"):
        load_settings({**env, "OPS_ASSIST_FAST_MODELS": " , "})
    path.write_text(path.read_text().replace('["fast", "backup"]', "[]"))
    with pytest.raises(ValueError, match="fast_models"):
        load_settings(env)
    assert load_settings({}).fast_models == load_settings({}).models


def test_tiers_construct_distinct_models(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    settings = replace(load_settings({}), models=["main"], fast_models=["fast", "backup"])
    agent = build_agent(settings)
    assert agent.model.model == "main"
    assert agent.model._additional_args["metadata"]["agent_name"] == "ops_assist"
    assert all(
        model._additional_args["metadata"]["agent_name"] == expert.name
        for expert in agent.sub_agents
        for model in expert.model.models
    )
    assert all([m.model for m in e.model.models] == ["fast", "backup"] for e in agent.sub_agents)


def test_scripted_usage_with_and_without_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))

    class UsageModel(RolesModel):
        async def generate_content_async(self, llm_request, stream=False):
            async for response in super().generate_content_async(llm_request, stream):
                response.usage_metadata = types.GenerateContentResponseUsageMetadata(
                    total_token_count=17,
                    prompt_token_count=10,
                    cached_content_token_count=4,
                    candidates_token_count=7,
                )
                yield response

    _, trace = investigate(
        "Why?", model=UsageModel(seen=[]), topology="experts", measure_usage=True, save_memory=False
    )
    assert trace.total_tokens == 17 * len(trace.context_tokens)
    assert trace.approximate_calls == 0
    assert trace.usage and all(
        row["input_tokens"] == 10 and row["cached_input_tokens"] == 4 and row["output_tokens"] == 7
        for row in trace.usage
    )
    _, estimated = investigate(
        "Why?", model=RolesModel(seen=[]), topology="experts", measure_usage=True, save_memory=False
    )
    assert estimated.total_tokens > sum(estimated.context_tokens)
    assert estimated.approximate_calls == len(estimated.context_tokens) > 0


def test_evaluate_and_cli_comparison(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))
    settings = replace(load_settings({}), fast_models=["fast"])
    result, path = evaluate(settings, model=RolesModel(seen=[]), compare_tier=True)
    assert len(result["results"]) > 1
    assert result["total_tokens"] > 0 and result["approximate_calls"] > 0
    assert result["duration_seconds"] >= 0
    assert json.loads(path.read_text())["fast_models"] == ["fast"]

    def fake_tiers(settings, repeat):
        assert settings.fast_models == ["fast"] and repeat == 2
        result = {
            "pass_rate": 0.5,
            "incident_pass_rates": {"fictional": 0.5},
            "total_tokens": 23,
            "approximate_calls": 1,
            "unknown_calls": 2,
            "duration_seconds": 2.0,
            "results": [],
        }
        return {"main": (result, tmp_path), "fast": (result, tmp_path)}

    monkeypatch.setattr("ops_assist.evaluation.evaluate_tiers", fake_tiers)
    monkeypatch.setenv("OPS_ASSIST_FAST_MODELS", "fast")
    assert cli.main(["eval", "run", "--repeat", "2", "--compare-tiers"]) == 0
    out = capsys.readouterr().out
    assert "main: pass rate=50.0% total tokens=23" in out
    assert "fast: pass rate=50.0% total tokens=23" in out and "duration=2.00s" in out
    assert "unknown calls=2" in out and "Sampling variance remains" in out
    assert cli.main(["profile"]) == 0
    assert "fast_models=['fast']" in capsys.readouterr().out


def test_mcp_refused_before_evaluation(monkeypatch, capsys):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")

    def forbidden(*args, **kwargs):
        pytest.fail("evaluation must not start")

    monkeypatch.setattr("ops_assist.evaluation.load_dataset", forbidden)
    for args in (["eval", "run"], ["eval", "run", "--compare-tiers"]):
        assert cli.main(args) == 1
        assert "Evaluation does not support OPS_ASSIST_TOOLS=mcp" in capsys.readouterr().err
    with pytest.raises(ValueError, match="OPS_ASSIST_TOOLS=mcp"):
        evaluate(load_settings({}))


@pytest.mark.parametrize(
    "models,key",
    [
        ("gemini/example", "GEMINI_API_KEY"),
        ("openai/example", "OPENAI_API_KEY"),
        ("anthropic/example", "ANTHROPIC_API_KEY"),
        ("mistral/example", "MISTRAL_API_KEY"),
        ("openrouter/example", "OPENROUTER_API_KEY"),
    ],
)
def test_fast_keys_checked_before_evaluation(monkeypatch, capsys, models, key):
    monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPS_ASSIST_FAST_MODELS", models)
    monkeypatch.setattr(
        "ops_assist.evaluation.evaluate_tiers", lambda *a, **k: pytest.fail("called")
    )
    assert cli.main(["eval", "run", "--compare-tiers"]) == 1
    assert key in capsys.readouterr().err


def test_profile_fast_keys_and_local_models(monkeypatch, capsys, tmp_path):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        "profiles:\n  local:\n    models: [ollama_chat/main]\n"
        "    fast_models: [anthropic/fast, ollama_chat/local]\n"
        "    description: Test\n    requires_env: []\n"
    )
    monkeypatch.setenv("OPS_ASSIST_PROFILES_FILE", str(path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        "ops_assist.evaluation.evaluate_tiers", lambda *a, **k: pytest.fail("called")
    )
    assert cli.main(["eval", "run", "--compare-tiers"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fictional")
    from ops_assist.config import missing_fast_keys

    assert missing_fast_keys(load_settings(), dict(__import__("os").environ)) == []


def test_tiers_interleave_and_fix_generation(monkeypatch, tmp_path):
    from test_evaluation import report_for

    from ops_assist import evaluation

    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(tmp_path))
    calls = []

    def scripted(question, *, settings, **kwargs):
        calls.append(
            (
                settings.incident,
                settings.fast_models,
                settings.deterministic,
                kwargs["topology"],
                kwargs["measure_usage"],
            )
        )
        trace = type("Trace", (), {"total_tokens": 7, "approximate_calls": 0, "unknown_calls": 0})()
        return report_for(settings.incident), trace

    monkeypatch.setattr(evaluation, "investigate", scripted)
    settings = replace(load_settings({}), fast_models=["fast"])
    results = evaluation.evaluate_tiers(settings, repeat=2)
    assert len(calls) > 4
    for main, fast in zip(calls[::2], calls[1::2], strict=True):
        assert main[0] == fast[0] and main[1] == settings.models and fast[1] == ["fast"]
        assert main[2:] == fast[2:] == (True, "experts", True)
    assert results["main"][0]["total_tokens"] == len(calls) // 2 * 7
    assert results["fast"][0]["total_tokens"] == len(calls) // 2 * 7


def test_sampling_settings_reach_scripted_requests(monkeypatch):
    class WatchModel(RolesModel):
        async def generate_content_async(self, llm_request, stream=False):
            assert llm_request.config.temperature == 0 and llm_request.config.seed == 42
            async for response in super().generate_content_async(llm_request, stream):
                yield response

    settings = replace(load_settings({}), deterministic=True)
    _, trace = investigate(
        "Why?",
        settings=settings,
        model=WatchModel(seen=[]),
        topology="experts",
        measure_usage=True,
        save_memory=False,
    )
    assert len(trace.context_agents) > 2
    from ops_assist.models import build_model

    assert build_model(settings)._additional_args["drop_params"] is True


def test_unmeasured_request_is_unknown_not_previous_count(monkeypatch):
    import ops_assist.run as run

    real_counter = run.litellm.token_counter
    calls = 0

    def counter(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("measurement unavailable")
        return real_counter(*args, **kwargs)

    monkeypatch.setattr(run.litellm, "token_counter", counter)
    _, trace = investigate(
        "Why?", model=RolesModel(seen=[]), topology="experts", measure_usage=True, save_memory=False
    )
    assert trace.unknown_calls == 1
    assert trace.approximate_calls == len(trace.context_tokens) > 1


def test_fast_override_endpoint_routing():
    for env, expected in [
        ({}, "http://localhost:11434"),
        ({"OPS_ASSIST_FAST_MODELS": "hosted/fast"}, None),
        (
            {"OPS_ASSIST_FAST_MODELS": "hosted/fast", "OPS_ASSIST_FAST_API_BASE": "http://fast"},
            "http://fast",
        ),
        ({"OPS_ASSIST_FAST_MODELS": "ollama_chat/qwen3:8b"}, None),
    ]:
        settings = load_settings(env)
        agent = build_agent(settings, topology="experts")
        for expert in agent.sub_agents:
            models = getattr(expert.model, "models", [expert.model])
            assert all(m._additional_args.get("api_base") == expected for m in models)


def test_zero_usage_is_estimated():
    class ZeroUsage(RolesModel):
        async def generate_content_async(self, llm_request, stream=False):
            async for response in super().generate_content_async(llm_request, stream):
                response.usage_metadata = types.GenerateContentResponseUsageMetadata(
                    total_token_count=0
                )
                yield response

    _, trace = investigate(
        "Why?", model=ZeroUsage(seen=[]), topology="experts", measure_usage=True, save_memory=False
    )
    assert trace.total_tokens > 0
    assert trace.approximate_calls == len(trace.context_tokens) > 0
