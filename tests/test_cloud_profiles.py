"""Cloud profile contracts, exercised without credentials or model calls."""

import asyncio

import pytest

from ops_assist import cli
from ops_assist.config import load_settings

PROFILES = {
    "vertex": ("vertex_ai/gemini-3.1-flash-lite", ["VERTEXAI_PROJECT", "VERTEXAI_LOCATION"]),
    "bedrock": (
        "bedrock/us.anthropic.claude-3-5-haiku-20241022-v1:0",
        ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION_NAME"],
    ),
    "azure": ("azure/gpt-4o", ["AZURE_API_KEY", "AZURE_API_BASE", "AZURE_API_VERSION"]),
}


@pytest.mark.parametrize("profile", PROFILES)
def test_resolution_and_each_required_variable(profile):
    model, keys = PROFILES[profile]
    settings = load_settings({"OPS_ASSIST_PROFILE": profile})
    assert settings.models == [model]
    assert settings.requires_env == keys
    cli.check_profile_env(settings, dict.fromkeys(keys, "value"))
    for key in keys:
        env = dict.fromkeys(keys, "value")
        env[key] = "  "
        with pytest.raises(ValueError, match=key):
            cli.check_profile_env(settings, env)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("command", ["ask", "investigate", "eval", "bench"])
def test_missing_variables_stop_before_call(monkeypatch, capsys, tmp_path, profile, command):
    monkeypatch.setenv("OPS_ASSIST_PROFILE", profile)
    monkeypatch.delenv("OPS_ASSIST_MODELS", raising=False)
    for key in PROFILES[profile][1]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cli.litellm, "completion", lambda **kw: pytest.fail("model called"))
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: pytest.fail("agent called"))
    (tmp_path / "prompt").write_text("fictional")
    args = {
        "ask": ["ask", "question"],
        "investigate": ["investigate", "question"],
        "eval": ["eval", "run"],
        "bench": ["bench", "--allow-remote", "--prompt-file", str(tmp_path / "prompt")],
    }
    assert cli.main(args[command]) == 1
    error = capsys.readouterr().err
    assert all(key in error for key in PROFILES[profile][1])


def test_profiles_list_status_and_residency(monkeypatch, capsys):
    monkeypatch.setenv("AZURE_API_KEY", "fictional-secret")
    monkeypatch.delenv("AZURE_API_BASE", raising=False)
    assert cli.main(["profiles"]) == 0
    out = capsys.readouterr().out
    assert "fictional-secret" not in out
    for name, location in [
        ("local", "local"),
        ("gemini", "managed API"),
        ("gateway", "gateway"),
        ("vertex", "dedicated cloud"),
        ("bedrock", "dedicated cloud"),
        ("azure", "dedicated cloud"),
    ]:
        line = next(line for line in out.splitlines() if line.startswith(name + ":"))
        assert f"location: {location}" in line and "residency:" in line
    azure = next(line for line in out.splitlines() if line.startswith("azure:"))
    assert "AZURE_API_BASE" in azure.split("missing:")[1]
    assert "AZURE_API_KEY" not in azure.split("missing:")[1]


@pytest.mark.parametrize("profile", PROFILES)
def test_agent_model_checks_before_generation(monkeypatch, profile):
    from ops_assist.models import build_model

    for key in PROFILES[profile][1]:
        monkeypatch.delenv(key, raising=False)
    model = build_model(load_settings({"OPS_ASSIST_PROFILE": profile}))
    with pytest.raises(ValueError, match=PROFILES[profile][1][0]):
        asyncio.run(anext(model.generate_content_async(None)))
