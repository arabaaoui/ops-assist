import asyncio

from ops_assist.agent import build_agent
from ops_assist.knowledge.embeddings import HashEmbedder
from ops_assist.knowledge.index import VectorIndex
from ops_assist.observability import ReplaySource
from ops_assist.security import TOOL_ACCESS, StateStore
from ops_assist.tools import make_graph_tool, make_knowledge_tool
from ops_assist.triage import pretriage


def call(tool, *args, **kwargs):
    return asyncio.run(tool(*args, **kwargs))


def test_graph_traversal_and_validation(monkeypatch):
    tool = make_graph_tool()
    result = call(tool, "checkout", depth=2)
    assert "payments-db" in result["nodes"]
    assert all(e["source"].endswith("graph.yaml") for e in result["edges"])
    assert "payments-db" not in call(tool, "checkout")["nodes"]
    assert "checkout" in call(tool, "payments-db", "upstream", 2)["nodes"]
    assert call(tool, "missing")["error"].startswith("unknown service")
    assert "payment-api" in call(tool, "missing")["error"]
    for kwargs in ({"depth": 0}, {"depth": 4}, {"depth": True}, {"direction": "sideways"}):
        assert call(tool, "checkout", **kwargs)["status"] == "error"
    monkeypatch.setenv("OPS_ASSIST_GRAPH_MAX_AGE_DAYS", "1")
    assert all(e["stale"] for e in call(tool, "payment-api")["edges"])
    monkeypatch.setenv("OPS_ASSIST_GRAPH_MAX_AGE_DAYS", "99999")
    assert not any(e["stale"] for e in call(tool, "payment-api")["edges"])
    monkeypatch.setenv("OPS_ASSIST_GRAPH_MAX_AGE_DAYS", "bad")
    assert call(tool, "payment-api")["status"] == "error"
    assert TOOL_ACCESS["get_dependencies"] == "read"
    assert "get_dependencies" in [getattr(t, "__name__", "") for t in build_agent().tools]


def test_triage_alerting_dependency():
    source = ReplaySource("payment-latency")
    original = source.alerts
    source.alerts = lambda: (
        original()
        + [
            {
                "id": "DB-1",
                "service": "orders-db",
                "severity": "warning",
                "since": "2026-03-12T09:01:00Z",
            }
        ]
    )
    hints = pretriage(source).dependency_hints
    assert len(hints) == 1
    assert hints[0]["service"] == "payment-api"
    assert hints[0]["dependency"] == "orders-db"
    assert not pretriage(ReplaySource("payment-latency")).dependency_hints


def test_expansion_offline():
    VectorIndex.build(HashEmbedder()).save(StateStore())
    tool = make_knowledge_tool()
    plain = call(tool, "payment-api", k=1)
    expanded = call(tool, "payment-api", k=1, expand=True)
    assert "expanded_chunks" not in plain
    assert any(c["source"].startswith("payments-db#") for c in expanded["expanded_chunks"])
    assert any(e["to"] == "payments-db" for e in expanded["expansion_edges"])
    assert len(expanded["expanded_chunks"]) <= 8
    assert call(tool, "payment-api", expand="yes")["status"] == "error"
    assert call(tool, "unrelated", expand=True)["expanded_chunks"] == []


def install_graph(monkeypatch, tmp_path, text):
    from ops_assist.knowledge import graph

    path = tmp_path / "data/knowledge/graph.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(graph, "files", lambda _: tmp_path)


def test_invalid_graph_keeps_triage_and_base_search(monkeypatch, tmp_path):
    import pytest

    from ops_assist.knowledge.graph import GraphError, dependencies, service_names

    VectorIndex.build(HashEmbedder()).save(StateStore())
    tool = make_knowledge_tool()
    base = call(tool, "payment-api", k=1)
    malformed = [
        "nodes: [broken",
        "nodes: not-a-list\nedges: []",
        "nodes: [payment-api, db]\nedges: [{source: payment-api, "
        "target: db, relation: calls, updated: bad}]",
        "nodes: [payment-api, db]\nedges: [{source: db, target: db, "
        "relation: calls, updated: bad}]",
        "nodes: [payment-api]\nedges: [42]",
    ]
    for text in malformed:
        install_graph(monkeypatch, tmp_path, text)
        with pytest.raises(GraphError):
            dependencies("payment-api")
        with pytest.raises(GraphError):
            service_names()
        triage = pretriage(ReplaySource("payment-latency"))
        assert triage.affected_services == ["payment-api"]
        assert len([w for w in triage.warnings if "dependency graph unavailable:" in w]) == 1
        expanded = call(tool, "payment-api", k=1, expand=True)
        assert expanded["status"] == "ok"
        assert expanded["chunks"] == base["chunks"]
        assert expanded["expansion_error"]
        if "updated: bad" in text:
            assert "updated date" in expanded["expansion_error"]
        assert call(make_graph_tool(), "payment-api")["status"] == "error"


def test_graph_future_bounded_and_deduplicated(monkeypatch, tmp_path):
    import yaml

    long_name = "d" * 700
    edge = {
        "source": "payment-api",
        "target": long_name,
        "relation": "depends_on",
        "updated": "9999-01-01",
        "extra": {"nested": "x" * 10000},
    }
    graph = {"nodes": ["payment-api", long_name], "edges": [edge, dict(edge)]}
    install_graph(monkeypatch, tmp_path, yaml.safe_dump(graph))
    result = call(make_graph_tool(), "payment-api")
    assert result["status"] == "ok" and result["truncated"]
    assert max(map(len, result["nodes"])) == 300
    assert len(result["edges"]) == 1
    row = result["edges"][0]
    assert set(row) == {"from", "to", "type", "updated", "stale", "source", "stale_reason"}
    assert len(row["to"]) == 300
    assert row["stale"] is True and row["stale_reason"] == "date in the future"
    assert all(len(v) <= 300 for v in row.values() if isinstance(v, str))


def test_unreadable_graph_and_late_expansion_error(monkeypatch, tmp_path):
    import pytest

    from ops_assist.knowledge import graph

    install_graph(monkeypatch, tmp_path, "nodes: [payment-api]\nedges: []")
    (tmp_path / "data/knowledge/graph.yaml").unlink()
    with pytest.raises(graph.GraphError):
        graph.service_names()
    assert (
        "dependency graph unavailable:" in pretriage(ReplaySource("payment-latency")).warnings[-1]
    )

    VectorIndex.build(HashEmbedder()).save(StateStore())
    tool = make_knowledge_tool()
    baseline = call(tool, "payment-api", k=1)
    monkeypatch.setattr(graph, "service_names", lambda: ["payment-api"])

    def unavailable(*args, **kwargs):
        raise graph.GraphError("invalid edge updated date")

    monkeypatch.setattr(graph, "dependencies", unavailable)
    result = call(tool, "payment-api", k=1, expand=True)
    assert result["status"] == "ok" and result["chunks"] == baseline["chunks"]
    assert result["expansion_error"] == "invalid edge updated date"


def test_invalid_age_is_graph_error_and_preserves_triage(monkeypatch):
    import pytest

    from ops_assist.knowledge.graph import GraphError, dependencies

    monkeypatch.setenv("OPS_ASSIST_GRAPH_MAX_AGE_DAYS", "9" * 5000)
    with pytest.raises(GraphError):
        dependencies("payment-api")
    assert (
        "dependency graph unavailable:" in pretriage(ReplaySource("payment-latency")).warnings[-1]
    )
