import logging
from pathlib import Path
from types import SimpleNamespace

import litellm
import yaml
from test_agent_loop import ScriptedModel
from test_config_and_models import _ask, _chain

from ops_assist import cli
from ops_assist.config import load_settings
from ops_assist.models import build_model
from ops_assist.run import investigate


def test_gateway_config_and_profile_are_consistent():
    config = yaml.safe_load(Path("deploy/litellm/config.yaml").read_text())
    models = {m["model_name"]: m["litellm_params"]["model"] for m in config["model_list"]}
    assert models == {
        "ops-primary": "gemini/gemini-2.5-flash-lite",
        "ops-backup": "openai/gpt-4o-mini",
    }
    assert config["router_settings"]["fallbacks"] == [{"ops-primary": ["ops-backup"]}]
    assert config["litellm_settings"]["turn_off_message_logging"] is True
    assert config["general_settings"]["disable_spend_logs"] is False
    assert config["general_settings"]["store_prompts_in_spend_logs"] is False
    assert config["general_settings"]["database_url"] == "os.environ/DATABASE_URL"
    settings = load_settings(env={"OPS_ASSIST_PROFILE": "gateway"})
    assert settings.models == ["openai/ops-primary"]
    assert settings.requires_env == ["OPENAI_API_KEY"]
    assert build_model(settings)._additional_args["api_base"] == "http://127.0.0.1:4000/v1"


def test_503_fallback_names_both_models_in_warning(caplog):
    error = litellm.ServiceUnavailableError("unavailable", model="p/a", llm_provider="p")
    model, primary, backup = _chain(error)
    with caplog.at_level(logging.WARNING, logger="ops_assist.models"):
        assert _ask(model) == "answer from b"
    assert (primary.calls, backup.calls) == (1, 1)
    assert "Model fallback: p/a -> p/b" in caplog.text


def test_non_retriable_error_does_not_log_transition(caplog):
    import pytest

    model, _, _ = _chain(litellm.BadRequestError("bad", model="p/a", llm_provider="p"))
    with (
        caplog.at_level(logging.WARNING, logger="ops_assist.models"),
        pytest.raises(litellm.BadRequestError),
    ):
        _ask(model)
    assert "Model fallback:" not in caplog.text


def test_cli_shows_provider_reported_model(monkeypatch, capsys):
    monkeypatch.setenv("OPS_ASSIST_MODELS", "openai/example")
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kw: SimpleNamespace(
            model="actual-backup",
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
        ),
    )
    assert cli.main(["ask", "hi"]) == 0
    output = capsys.readouterr()
    assert output.out.strip() == "answer" and "Model: actual-backup" in output.err


def test_investigation_cli_reports_model_versions(monkeypatch, capsys):
    class NamedModel(ScriptedModel):
        async def generate_content_async(self, llm_request, stream=False):
            async for response in super().generate_content_async(llm_request, stream):
                response.model_version = "actual-backup"
                yield response

    monkeypatch.setattr(
        cli,
        "investigate",
        lambda question, settings: investigate(question, model=NamedModel(seen=[])),
    )
    assert cli.main(["investigate", "why?"]) == 0
    assert "Models: actual-backup" in capsys.readouterr().out
