import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from litellm.types.utils import ModelResponseStream

from ops_assist import cli
from ops_assist.bench import benchmark
from ops_assist.config import load_settings


def chunk(content=None, tokens=None):
    return ModelResponseStream(
        choices=[{"delta": {"content": content}}] if content else [],
        usage={"completion_tokens": tokens} if tokens else None,
    )


def test_benchmark_timing_usage_and_summary():
    times = iter([0, 1, 2, 3, 4, 10, 12, 14, 15, 16])
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return iter([chunk("one"), chunk("two"), chunk(tokens=5)])

    result = benchmark(
        load_settings(env={}), "hello", 2, clock=lambda: next(times), completion=completion
    )
    assert result["runs"] == [
        {"ttft_seconds": 1, "decode_tokens_per_second": 4, "total_seconds": 4, "output_tokens": 5},
        {"ttft_seconds": 2, "decode_tokens_per_second": 2, "total_seconds": 6, "output_tokens": 5},
    ]
    assert result["summary"]["ttft_seconds"] == {"median": 1.5, "min": 1, "max": 2, "samples": 2}
    assert result["summary"]["decode_tokens_per_second"]["median"] == 3
    assert all(
        c["stream"]
        and c["stream_options"] == {"include_usage": True}
        and c["max_tokens"] == 512
        and c["api_base"]
        for c in calls
    )
    assert calls[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert calls[0]["metadata"] == {
        "agent_name": "benchmark",
        "profile": "local",
        "ops_assist_version": "0.1.0",
    }


def test_missing_usage_and_empty_stream():
    clock = iter([0, 1, 2])
    result = benchmark(
        load_settings(env={}),
        "x",
        1,
        clock=lambda: next(clock),
        completion=lambda **kw: iter([chunk("one")]),
    )
    assert result["summary"]["decode_tokens_per_second"] is None
    assert result["runs"][0]["output_tokens"] is None
    with pytest.raises(ValueError, match="no visible text"):
        benchmark(load_settings(env={}), "x", 1, clock=lambda: 0, completion=lambda **kw: iter([]))


def test_guards_and_errors():
    local = load_settings(env={})
    for settings in [
        replace(local, profile="api"),
        replace(local, models=["openai/example"]),
        replace(local, api_base="http://remote.invalid"),
    ]:
        with pytest.raises(ValueError, match="allow-remote"):
            benchmark(settings, "x", 1)
    for n in [0, 101]:
        with pytest.raises(ValueError, match="runs"):
            benchmark(local, "x", n)
    for prompt in [" ", "x" * 65537]:
        with pytest.raises(ValueError, match="prompt"):
            benchmark(local, prompt, 1)

    def fail(**kwargs):
        raise RuntimeError("secret")

    with pytest.raises(ValueError, match="RuntimeError") as error:
        benchmark(local, "x", 1, completion=fail)
    assert "secret" not in str(error.value)


def test_memory_probe_and_remote_opt_in():
    settings = load_settings(env={"OPS_ASSIST_MODELS": "ollama_chat/example"})
    probes = NS(
        ollama=lambda: {"models": [{"name": "example:latest", "size": 100, "size_vram": 80}]}
    )

    def run(probes):
        clock = iter([0, 1, 2, 3])
        return benchmark(
            replace(settings, profile="api"),
            "x",
            1,
            allow_remote=True,
            ollama=True,
            probes=probes,
            clock=lambda: next(clock),
            completion=lambda **kw: iter([chunk("a"), chunk(tokens=2)]),
        )

    assert run(probes)["ollama_memory"]["size_vram"] == 80
    assert run(NS(ollama=lambda: {}))["ollama_memory"] is None


def test_cli_json_table_and_refusal(monkeypatch, tmp_path, capsys):
    path = tmp_path / "prompt.txt"
    path.write_text("fictional", encoding="utf-8")
    monkeypatch.setattr("litellm.completion", lambda **kw: iter([chunk("answer"), chunk(tokens=2)]))
    assert (
        cli.main(
            ["bench", "--profile", "local", "--runs", "1", "--prompt-file", str(path), "--json"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["runs"][0]["output_tokens"] == 2
    assert cli.main(["bench", "--prompt-file", str(path), "--runs", "1"]) == 0
    assert "Median" in capsys.readouterr().out
    assert cli.main(["bench", "--profile", "api", "--prompt-file", str(path)]) == 1
    assert "allow-remote" in capsys.readouterr().err


def test_environment_endpoint_guard(monkeypatch):
    settings = replace(load_settings(env={}), api_base=None)
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return iter([chunk("ok")])

    monkeypatch.setenv("OLLAMA_API_BASE", "http://remote.invalid")
    with pytest.raises(ValueError, match="allow-remote"):
        benchmark(settings, "x", 1, completion=completion)
    benchmark(settings, "x", 1, completion=completion, allow_remote=True)
    assert calls[-1]["api_base"] == "http://remote.invalid"
    for base in ("http://localhost:11434", "http://[::1]:11434"):
        monkeypatch.setenv("OLLAMA_API_BASE", base)
        benchmark(settings, "x", 1, completion=completion)
        assert calls[-1]["api_base"] == base
    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost.evil")
    with pytest.raises(ValueError, match="allow-remote"):
        benchmark(settings, "x", 1, completion=completion)


def test_hosted_model_never_gets_the_ollama_endpoint(monkeypatch):
    settings = replace(load_settings(env={}), models=["openai/gpt-4o-mini"], api_base=None)
    calls = []

    def completion(**kwargs):
        calls.append(kwargs)
        return iter([chunk("ok")])

    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:11434")
    benchmark(settings, "x", 1, completion=completion, allow_remote=True)
    assert "api_base" not in calls[-1]


def test_prompt_file_size_before_decoding(tmp_path, capsys):
    path = tmp_path / "large"
    path.write_bytes(b"\xff" * 65537)
    assert cli.main(["bench", "--prompt-file", str(path)]) == 1
    assert "65536 bytes" in capsys.readouterr().err
