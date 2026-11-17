import asyncio
from types import SimpleNamespace

import litellm
import pytest

from ops_assist import cli
from ops_assist.knowledge.embeddings import HashEmbedder
from ops_assist.knowledge.evaluation import evaluate, metrics
from ops_assist.knowledge.index import VectorIndex
from ops_assist.knowledge.retrieval import (
    BM25Index,
    KeywordOverlapReranker,
    LLMReranker,
    configured_reranker,
    fuse,
    search,
)
from ops_assist.security import StateStore
from ops_assist.tools import make_knowledge_tool


def sample_index():
    chunks = [
        {"id": "a", "text": "red red apple", "title": "A"},
        {"id": "b", "text": "red pear", "title": "B"},
        {"id": "c", "text": "blue pear", "title": "C"},
    ]
    embedder = HashEmbedder()
    return VectorIndex(embedder, chunks, embedder.embed([c["text"] for c in chunks]))


def test_bm25_fusion_and_modes(monkeypatch):
    index = sample_index()
    bm25 = BM25Index(index.chunks)
    assert [x["id"] for x in bm25.search("red red apple", 2)] == ["a", "b"]
    assert BM25Index([]).search("red") == []
    assert bm25.search("unknown") == []
    assert bm25.search("") == []
    assert [r["id"] for r in bm25.search("apple")] == ["a"]
    hybrid = search(index, "unknown", 3, mode="hybrid")
    vector = index.search("unknown", 3)
    assert [r["id"] for r in hybrid] == [r["id"] for r in vector]
    assert [r["score"] for r in hybrid] == pytest.approx([1 / 61, 1 / 62, 1 / 63])
    with pytest.raises(ValueError):
        bm25.search("x", 0)
    a, b, c = index.chunks
    assert [x["id"] for x in fuse([[a, b], [c, b]], 3)] == ["b", "a", "c"]
    assert fuse([[a, a]], 2)[0]["score"] == pytest.approx(1 / 61)
    for mode in ("vector", "bm25", "hybrid"):
        monkeypatch.setenv("OPS_ASSIST_RETRIEVAL", mode)
        assert search(index, "red apple", 1)[0]["id"] == "a"
    monkeypatch.setenv("OPS_ASSIST_RETRIEVAL", "invalid")
    with pytest.raises(ValueError, match="RETRIEVAL"):
        search(index, "red")
    with pytest.raises(ValueError, match="between"):
        search(index, "red", 101)


def test_keyword_reranks_and_keeps_ties():
    index = sample_index()
    rows = [index.chunks[2], index.chunks[1], index.chunks[0]]
    assert [x["id"] for x in KeywordOverlapReranker().rerank("red pear", rows)] == ["b", "c", "a"]
    assert len(search(index, "red", 1, mode="hybrid", reranker=KeywordOverlapReranker())) == 1


def test_llm_reranker_mocked_and_strict(monkeypatch):
    calls = []
    values = iter(["0", "3", "2"])

    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=next(values)))]
        )

    monkeypatch.setattr(litellm, "completion", completion)
    rows = sample_index().chunks
    assert [
        x["id"] for x in LLMReranker("example/model", "http://localhost").rerank("red", rows)
    ] == ["b", "c", "a"]
    assert calls[0]["model"] == "example/model" and calls[0]["api_base"] == "http://localhost"
    assert calls[0]["metadata"] == {
        "agent_name": "reranker",
        "profile": "local",
        "ops_assist_version": "1.0.0",
    }
    assert "untrusted" in calls[0]["messages"][0]["content"]
    for invalid in ("3 points", "4", "-1", "3\n0", None):
        monkeypatch.setattr(
            litellm,
            "completion",
            lambda invalid=invalid, **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=invalid))]
            ),
        )
        with pytest.raises(ValueError, match="invalid score"):
            LLMReranker("example/model").rerank("red", rows[:1])
    monkeypatch.setattr(
        litellm, "completion", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("secret"))
    )
    with pytest.raises(ValueError, match="provider error") as exc:
        LLMReranker("example/model").rerank("red", rows[:1])
    assert "secret" not in str(exc.value)
    with pytest.raises(ValueError):
        LLMReranker(" ")


def test_configuration_and_tool_failure(monkeypatch):
    assert configured_reranker() is None
    monkeypatch.setenv("OPS_ASSIST_RERANKER", "keyword")
    assert isinstance(configured_reranker(), KeywordOverlapReranker)
    monkeypatch.setenv("OPS_ASSIST_RERANKER", "example/model")
    monkeypatch.setenv("OPS_ASSIST_RERANKER_API_BASE", "http://localhost")
    assert configured_reranker().api_base == "http://localhost"
    monkeypatch.setenv("OPS_ASSIST_RERANKER", "")
    with pytest.raises(ValueError):
        configured_reranker()
    VectorIndex.build(HashEmbedder()).save(StateStore())
    result = asyncio.run(make_knowledge_tool()("payment"))
    assert result["status"] == "error"


def test_metrics_and_bundled_evaluation(monkeypatch, capsys):
    assert metrics([["x", "a", "b"], ["z"]], [["a", "b"], ["q"]]) == pytest.approx((0.5, 0.25))
    assert metrics([["a", "a"]], [["a", "b"]]) == pytest.approx((0.5, 1))
    for ranks, expected in [([], []), ([["x"]], []), ([["x"]], [[]])]:
        with pytest.raises(ValueError):
            metrics(ranks, expected)
    scores = evaluate()
    assert {name: tuple(round(value, 3) for value in pair) for name, pair in scores.items()} == {
        "vector": (0.575, 0.675),
        "bm25": (0.783, 1.000),
        "hybrid": (0.758, 0.795),
        "hybrid+rerank": (0.783, 0.808),
    }
    for i in (0, 1):
        assert scores["hybrid"][i] >= min(scores["vector"][i], scores["bm25"][i])
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS", "unavailable/model")
    assert cli.main(["knowledge", "eval"]) == 0
    output = capsys.readouterr().out
    assert all(name + ":" in output for name in scores)


@pytest.mark.parametrize("failure", ["malformed", "provider"])
def test_reranking_failure_returns_initial_order_and_reports(monkeypatch, caplog, capsys, failure):
    index = VectorIndex.build(HashEmbedder())
    index.save(StateStore())
    monkeypatch.setenv("OPS_ASSIST_RETRIEVAL", "hybrid")
    monkeypatch.setenv("OPS_ASSIST_RERANKER", "example/model")
    calls = 0

    def completion(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if failure == "provider":
                raise RuntimeError("private provider detail")
            value = "3 points"
        else:
            value = "3"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])

    monkeypatch.setattr(litellm, "completion", completion)
    expected = search(index, "database connection leak", 20, mode="hybrid")[:5]
    result = asyncio.run(make_knowledge_tool()("database connection leak", 5))
    reason = "provider error" if failure == "provider" else "invalid score"
    assert result["status"] == "ok" and result["retrieval"] == "found"
    assert result["reranked"] is False and result["rerank_error"] == reason
    assert [row["source"] for row in result["chunks"]] == [row["id"] for row in expected]
    assert "Reranking skipped: " + reason in caplog.text
    assert "private provider detail" not in caplog.text
    calls = 0
    assert cli.main(["knowledge", "search", "database connection leak"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 5


def test_reranker_success_status(monkeypatch):
    monkeypatch.setattr(
        litellm,
        "completion",
        lambda **kwargs: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="2"))]
        ),
    )
    result = search(sample_index(), "red", reranker=LLMReranker("example/model"))
    assert result.reranked is True and result.rerank_error is None


def test_evaluation_annotations():
    from importlib.resources import files

    import yaml

    cases = yaml.safe_load(
        files("ops_assist").joinpath("data/knowledge/eval/questions.yaml").read_text()
    )
    assert len(cases) == 10
    assert cases[8]["expected"] == ["disk-incident#2"]
    assert cases[7]["expected"] == ["payment-processor-incident#1"]
    assert set(cases[1]["expected"]) == {
        "cache-stampede#1",
        "cache-stampede#2",
        "cache-incident#1",
        "cache-incident#2",
    }


def test_evaluation_ignores_approved_documents():
    before = evaluate()
    store = StateStore()
    store.write_knowledge(
        "approved",
        "extra.md",
        "---\nid: extra\ntitle: Extra\nservice: payment\nupdated: 2026-01-01\n"
        "owner: reviewer\n---\n# database connection leak payment latency timeouts\n"
        "database connection leak payment latency timeouts\n",
    )
    assert any(c["id"].startswith("extra#") for c in VectorIndex.build(HashEmbedder()).chunks)
    assert not any(
        c["id"].startswith("extra#")
        for c in VectorIndex.build(HashEmbedder(), include_approved=False).chunks
    )
    assert evaluate() == before
