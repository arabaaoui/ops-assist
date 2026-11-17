import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from ops_assist.agent import build_agent
from ops_assist.knowledge import index as knowledge
from ops_assist.knowledge.embeddings import HashEmbedder
from ops_assist.run import investigate
from ops_assist.security import TOOL_ACCESS, StateStore
from ops_assist.tools import MCP_EXPOSED_TOOLS, make_knowledge_tool


class CountingEmbedder(HashEmbedder):
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return super().embed(texts)


def test_incremental_ingestion(monkeypatch):
    documents = knowledge.load_documents()
    monkeypatch.setattr(knowledge, "load_documents", lambda: documents)
    embedder = CountingEmbedder()
    first = knowledge.VectorIndex.build(embedder)
    assert len(embedder.calls) == len(documents)
    first.save(StateStore())
    previous = knowledge.VectorIndex.load(StateStore(), embedder)
    embedder.calls.clear()
    second = knowledge.VectorIndex.build(embedder, previous)
    assert not embedder.calls and second.vectors == previous.vectors
    changed = dict(documents[0], body=documents[0]["body"] + "\nnew content", checksum="changed")
    monkeypatch.setattr(knowledge, "load_documents", lambda: [changed, *documents[1:-1]])
    third = knowledge.VectorIndex.build(embedder, second)
    assert len(embedder.calls) == 1
    assert len(embedder.calls[0]) == third.manifest[0]["chunk_count"]
    assert third.manifest[0]["checksum"] == "changed"
    assert len(third.manifest) == len(documents) - 1


def test_tool_boundary_and_failure(monkeypatch):
    tool = make_knowledge_tool()
    assert TOOL_ACCESS["search_knowledge"] == "read"
    assert "search_knowledge" not in MCP_EXPOSED_TOOLS
    assert asyncio.run(tool("payment"))["status"] == "error"
    knowledge.VectorIndex.build(HashEmbedder()).save(StateStore())
    result = asyncio.run(tool("payment", 100))
    assert result["status"] == "ok" and result["retrieval"] == "found"
    assert len(result["chunks"]) == 8
    assert all(
        set(c) == {"source", "title", "updated", "stale", "stale_reason", "excerpt", "score"}
        and len(c["excerpt"]) <= 800
        and c["updated"]
        and isinstance(c["stale"], bool)
        for c in result["chunks"]
    )
    assert asyncio.run(tool("payment", 0))["status"] == "error"
    assert asyncio.run(tool(""))["status"] == "error"
    monkeypatch.setenv("OPS_ASSIST_TOPOLOGY", "experts")
    agent = build_agent()
    assert any(getattr(t, "__name__", "") == "search_knowledge" for t in agent.tools)
    assert all(
        all(getattr(t, "__name__", "") != "search_knowledge" for t in expert.tools)
        for expert in agent.sub_agents
    )


class CitationModel(BaseLlm):
    model: str = "scripted"
    citation: str

    async def generate_content_async(
        self, llm_request, stream=False
    ) -> AsyncGenerator[LlmResponse, None]:
        report = {
            "summary": "Guidance found.",
            "status": "insufficient_data",
            "facts": [{"statement": "A procedure exists.", "source": self.citation}],
        }
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=json.dumps(report))])
        )


@pytest.mark.parametrize("citation,flagged", [("payment-latency#1", False), ("fake#999", True)])
def test_scripted_citation_and_cli(monkeypatch, capsys, citation, flagged):
    from ops_assist import cli

    knowledge.VectorIndex.build(HashEmbedder()).save(StateStore())
    report, trace = investigate("question", model=CitationModel(citation=citation))
    assert any("knowledge, not observation" in w for w in report.citation_warnings)
    assert any("Unknown knowledge citation" in w for w in report.citation_warnings) is flagged
    assert trace.warnings == report.citation_warnings
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, trace))
    assert cli.main(["investigate", "question"]) == 0
    captured = capsys.readouterr()
    assert bool("Unknown knowledge citation" in captured.err) is flagged
    assert (
        json.JSONDecoder().raw_decode(captured.out)[0]["citation_warnings"]
        == report.citation_warnings
    )


def test_index_unavailable_flags_citations():
    report, trace = investigate("question", model=CitationModel(citation="payment-latency#1"))
    assert (
        "Knowledge citations could not be verified: index unavailable" in report.citation_warnings
    )
    assert any("knowledge, not observation" in w for w in report.citation_warnings)
    assert trace.warnings == report.citation_warnings


def test_changed_embedding_space_reembeds_all(monkeypatch):
    docs = knowledge.load_documents()[:2]
    monkeypatch.setattr(knowledge, "load_documents", lambda: docs)
    old = knowledge.VectorIndex.build(HashEmbedder())
    new = CountingEmbedder()
    new.id = "different-space"
    rebuilt = knowledge.VectorIndex.build(new, old)
    assert len(new.calls) == 2
    assert rebuilt.manifest == old.manifest


def test_coordinator_keeps_search_in_mcp_mode(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOLS", "mcp")
    agent = build_agent()
    assert any(getattr(tool, "__name__", "") == "search_knowledge" for tool in agent.tools)


class ReportModel(BaseLlm):
    model: str = "scripted"
    report: dict

    async def generate_content_async(
        self, llm_request, stream=False
    ) -> AsyncGenerator[LlmResponse, None]:
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=json.dumps(self.report))])
        )


@pytest.mark.parametrize(
    "field,citation",
    [
        ("summary", "fake-summary#99"),
        ("hypothesis", "runbook:missing#23"),
        ("unknown", "postmortem:missing#3"),
        ("reason", "missing-action#4"),
        ("fact_statement", "missing-fact#5"),
    ],
)
def test_citations_anywhere_in_report(field, citation):
    knowledge.VectorIndex.build(HashEmbedder()).save(StateStore())
    data = {
        "summary": "Incident.",
        "status": "hypotheses_only",
        "facts": [{"statement": "A latency alert fired.", "source": "replay:x/alerts"}],
        "hypotheses": [{"statement": "Possibly slow.", "confidence": 0.5, "supporting_facts": [0]}],
        "unknowns": ["Details missing."],
        "proposed_action": {"kind": "rollback_deployment", "target": "payment", "reason": "Test."},
    }
    if field == "summary":
        data["summary"] = f"See:{citation}."
    elif field == "hypothesis":
        data["hypotheses"][0]["statement"] = f"Suggested by {citation}."
    elif field == "unknown":
        data["unknowns"] = [f"Need {citation}."]
    elif field == "reason":
        data["proposed_action"]["reason"] = f"Consult {citation}."
    else:
        data["facts"][0]["statement"] = f"Consult {citation}."
    report, trace = investigate("question", model=ReportModel(report=data))
    assert f"Unknown knowledge citation: {citation}" in report.citation_warnings
    assert trace.warnings == report.citation_warnings


def test_root_cause_requires_observation_support(monkeypatch, capsys):
    from ops_assist import cli

    knowledge.VectorIndex.build(HashEmbedder()).save(StateStore())
    data = {
        "summary": "Pool may be saturated.",
        "status": "root_cause_identified",
        "facts": [
            {"statement": "The runbook recommends a check.", "source": "payment-latency#1"},
            {"statement": "Pool is saturated.", "source": "replay:payment/metrics/pool"},
        ],
        "hypotheses": [
            {"statement": "Pool exhaustion.", "confidence": 0.9, "supporting_facts": [0]}
        ],
    }
    with pytest.raises(ValueError, match="requires observation support"):
        investigate("question", model=ReportModel(report=data))
    data["hypotheses"][0]["supporting_facts"] = [0, 1]
    report, trace = investigate("question", model=ReportModel(report=data))
    assert report.status == "root_cause_identified"
    assert any("knowledge, not observation" in w for w in report.citation_warnings)
    monkeypatch.setattr(cli, "investigate", lambda *a, **kw: (report, trace))
    assert cli.main(["investigate", "question"]) == 0
    captured = capsys.readouterr()
    assert "knowledge, not observation" in captured.err
    assert (
        "knowledge, not observation"
        in json.JSONDecoder().raw_decode(captured.out)[0]["citation_warnings"][0]
    )
    data["facts"][1]["source"] = "recall_past_incidents"
    with pytest.raises(ValueError, match="requires observation support"):
        investigate("question", model=ReportModel(report=data))


def test_empty_corpus_replaces_old_index_without_embedding(monkeypatch, capsys):
    from ops_assist import cli

    old = knowledge.VectorIndex.build(HashEmbedder())
    old.save(StateStore())
    monkeypatch.setattr(knowledge, "load_documents", lambda: [])
    assert cli.main(["knowledge", "index"]) == 0
    assert "Indexed 0 chunks" in capsys.readouterr().out
    embedder = CountingEmbedder()
    index = knowledge.VectorIndex.load(StateStore(), embedder)
    assert index.chunks == index.vectors == index.manifest == []
    assert index.dimension == 0
    assert index.search("query") == [] and not embedder.calls
    assert cli.main(["knowledge", "search", "query"]) == 0
    assert capsys.readouterr().out.strip() == "retrieval: none"
    result = asyncio.run(make_knowledge_tool()("query"))
    assert result == {
        "status": "ok",
        "retrieval": "none",
        "retrieval_quality": "none",
        "chunks": [],
    }
    assert knowledge.VectorIndex.build(embedder, index).chunks == [] and not embedder.calls


def test_prompt_requires_observation_and_citations():
    from ops_assist.agent import INSTRUCTION

    assert "Procedures are guidance, not incident observations" in INSTRUCTION
    assert "supporting fact from alerts, metrics, logs, or changes" in INSTRUCTION
    assert "exact chunk ID wherever referenced" in INSTRUCTION
