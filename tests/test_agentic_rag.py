import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from ops_assist import cli
from ops_assist.agent import INSTRUCTION
from ops_assist.knowledge.embeddings import HashEmbedder
from ops_assist.knowledge.index import VectorIndex
from ops_assist.run import investigate
from ops_assist.security import SecurityBoundary, StateStore
from ops_assist.tools import make_knowledge_tool


def test_quality_thresholds_and_empty(monkeypatch):
    from ops_assist.knowledge import retrieval

    VectorIndex.build(HashEmbedder()).save(StateStore())
    tool = make_knowledge_tool()
    row = {"id": "fiction#1", "title": "Fiction", "text": "alpha", "score": 999}
    monkeypatch.setattr(retrieval, "search", lambda *a, **kw: retrieval.SearchResults([row], False))
    good = asyncio.run(tool("alpha beta"))
    assert good["retrieval_quality"] == "good" and "suggestion" not in good
    weak = asyncio.run(tool("alpha beta gamma"))
    assert weak["retrieval_quality"] == "weak"
    assert "service name or symptom" in weak["suggestion"]
    monkeypatch.setattr(retrieval, "search", lambda *a, **kw: retrieval.SearchResults([], False))
    assert asyncio.run(tool("alpha"))["retrieval_quality"] == "none"


class SearchingModel(BaseLlm):
    model: str = "scripted"
    seen: list = []

    async def generate_content_async(
        self, llm_request, stream=False
    ) -> AsyncGenerator[LlmResponse, None]:
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in (c.parts or [])
            if p.function_response and p.function_response.name == "search_knowledge"
        ]
        if len(responses) < 4:
            part = types.Part(
                function_call=types.FunctionCall(
                    name="search_knowledge", args={"query": f"fiction {len(responses)}"}
                )
            )
        else:
            self.seen.extend(r.response for r in responses)
            part = types.Part(
                text=json.dumps(
                    {
                        "summary": "Unknown.",
                        "status": "insufficient_data",
                        "unknowns": ["No reliable guidance."],
                    }
                )
            )
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def test_search_limit_trace_and_cli(monkeypatch, capsys):
    VectorIndex.build(HashEmbedder()).save(StateStore())
    model = SearchingModel(seen=[])
    report, trace = investigate("question", model=model, show_context=True)
    assert len(model.seen) == 4
    assert model.seen[-1] == {"status": "denied", "reason": "knowledge_search_limit"}
    calls = [call for call in trace if call.name == "search_knowledge"]
    assert [c.args["query"] for c in calls] == [f"fiction {i}" for i in range(4)]
    assert [c.retrieval_quality for c in calls] == [
        r.get("retrieval_quality", r.get("reason")) for r in model.seen
    ]
    assert all(
        c.retrieval_quality in {"good", "weak", "none", "knowledge_search_limit"} for c in calls
    )
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, trace))
    assert cli.main(["investigate", "question", "--show-context"]) == 0
    out = capsys.readouterr().out
    for call in calls:
        assert f'"query": "{call.args["query"]}"' in out
        assert f"quality={call.retrieval_quality}" in out


def test_configuration_and_prompt(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_MAX_SEARCHES", "0")
    with pytest.raises(ValueError, match="OPS_ASSIST_MAX_SEARCHES"):
        SecurityBoundary()
    monkeypatch.setenv("OPS_ASSIST_MAX_SEARCHES", "1")
    assert SecurityBoundary().max_searches == 1
    assert "only when it helps" in INSTRUCTION
    assert "once or twice" in INSTRUCTION and "record what remains unknown" in INSTRUCTION


def test_quality_uses_visible_excerpt(monkeypatch):
    from ops_assist.knowledge import retrieval

    VectorIndex.build(HashEmbedder()).save(StateStore())
    row = {"id": "fiction#1", "title": "Fiction", "text": "x" * 800 + " alpha beta", "score": 1}
    monkeypatch.setattr(retrieval, "search", lambda *a, **kw: retrieval.SearchResults([row], False))
    result = asyncio.run(make_knowledge_tool()("alpha beta"))
    assert len(result["chunks"][0]["excerpt"]) == 800
    assert result["retrieval_quality"] == "weak" and result["suggestion"]


def test_trace_redaction_limits_and_unknown(monkeypatch, capsys):
    from ops_assist.run import InvestigationTrace

    trace = InvestigationTrace()
    for i in range(101):
        trace.record_call(
            types.FunctionCall(
                id=str(i),
                name="search_knowledge",
                args={"query": "token=fictionalsecret " + "x" * 300},
            )
        )
        trace.record_response(
            types.FunctionResponse(
                id=str(i),
                name="search_knowledge",
                response={"status": "denied", "reason": "knowledge_search_limit"},
            )
        )
    assert len(trace) == 50 and trace.omitted_calls == 51
    assert all(c.retrieval_quality == "knowledge_search_limit" for c in trace)
    assert all(
        len(c.args["query"]) == 200
        and "fictionalsecret" not in c.args["query"]
        and "[redacted]" in c.args["query"]
        for c in trace
    )
    other = InvestigationTrace()
    other.record_call(
        types.FunctionCall(id="one", name="search_knowledge", args={"query": "example"})
    )
    other.record_response(
        types.FunctionResponse(
            id="wrong", name="search_knowledge", response={"retrieval_quality": "good"}
        )
    )
    assert other[0].retrieval_quality == "outcome unknown"
    other.record_response(
        types.FunctionResponse(name="search_knowledge", response={"retrieval_quality": "good"})
    )
    assert other[0].retrieval_quality == "outcome unknown"
    report, _ = investigate("question", model=SearchingModel(seen=[]))
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, trace))
    assert cli.main(["investigate", "question", "--show-context"]) == 0
    out = capsys.readouterr().out
    assert "... 51 more tool calls" in out and "fictionalsecret" not in out
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, other))
    assert cli.main(["investigate", "question"]) == 0
    out = capsys.readouterr().out
    assert '"query": "example"' in out and "quality=outcome unknown" in out


class ResumeSearchModel(BaseLlm):
    model: str = "scripted"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        searches = [r for r in responses if r.name == "search_knowledge"]
        rollback = [r for r in responses if r.name == "rollback_deployment"]
        if not searches:
            call = types.FunctionCall(name="search_knowledge", args={"query": "payment"})
        elif not rollback:
            call = types.FunctionCall(
                name="rollback_deployment",
                args={"service": "payment-api", "deployment_id": "DEP-2140"},
            )
        elif len(searches) == 1:
            call = types.FunctionCall(name="search_knowledge", args={"query": "payment again"})
        else:
            self.seen.extend(r.response for r in searches)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=json.dumps(
                                {
                                    "summary": "unknown",
                                    "status": "insufficient_data",
                                    "unknowns": ["cause"],
                                }
                            )
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(function_call=call)])
        )


def test_search_budget_audited_across_confirmation(monkeypatch):
    import os
    from pathlib import Path

    monkeypatch.setenv("OPS_ASSIST_ALLOW_WRITES", "1")
    monkeypatch.setenv("OPS_ASSIST_MAX_SEARCHES", "1")
    VectorIndex.build(HashEmbedder()).save(StateStore())
    model = ResumeSearchModel(seen=[])
    decisions = []
    _, trace = investigate(
        "question", model=model, confirm_tool=lambda name, args: decisions.append(name) or True
    )
    assert decisions == ["rollback_deployment"]
    assert model.seen[0]["status"] == "ok"
    assert model.seen[1] == {"status": "denied", "reason": "knowledge_search_limit"}
    assert [c.retrieval_quality for c in trace if c.name == "search_knowledge"] == [
        model.seen[0]["retrieval_quality"],
        "knowledge_search_limit",
    ]
    entries = [
        json.loads(line)
        for line in (Path(os.environ["OPS_ASSIST_STATE_DIR"]) / "audit.jsonl")
        .read_text()
        .splitlines()
    ]
    assert any(
        e["tool"] == "search_knowledge"
        and e["args"]["query"] == "payment again"
        and e["outcome"] == "denied"
        for e in entries
    )


class BurstModel(BaseLlm):
    model: str = "scripted"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response and p.function_response.name == "search_knowledge"
        ]
        if not responses:
            parts = [
                types.Part(
                    function_call=types.FunctionCall(
                        name="search_knowledge", args={"query": "payment"}
                    )
                )
            ]
        elif len(responses) == 1:
            parts = [
                types.Part(
                    function_call=types.FunctionCall(
                        name="search_knowledge",
                        args={"query": "token=fictionalsecret " + "x" * 300 + str(i)},
                    )
                )
                for i in range(100)
            ]
        else:
            self.seen.extend(r.response for r in responses)
            parts = [
                types.Part(
                    text=json.dumps(
                        {"summary": "unknown", "status": "insufficient_data", "unknowns": ["cause"]}
                    )
                )
            ]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


def test_trace_bounded_with_real_refusals(monkeypatch, capsys):
    monkeypatch.setenv("OPS_ASSIST_MAX_SEARCHES", "1")
    monkeypatch.setenv("OPS_ASSIST_MAX_TOOL_CALLS", "1000")
    VectorIndex.build(HashEmbedder()).save(StateStore())
    model = BurstModel(seen=[])
    report, trace = investigate("question", model=model)
    assert len(model.seen) == 101
    assert all(
        r == {"status": "denied", "reason": "knowledge_search_limit"} for r in model.seen[1:]
    )
    assert len(trace) == 50 and trace.omitted_calls == 51
    assert all(c.retrieval_quality == "knowledge_search_limit" for c in trace[1:])
    assert all(
        len(c.args["query"]) <= 200 and "fictionalsecret" not in c.args["query"] for c in trace
    )
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, trace))
    assert cli.main(["investigate", "question"]) == 0
    out = capsys.readouterr().out
    assert "... 51 more tool calls" in out and "fictionalsecret" not in out
