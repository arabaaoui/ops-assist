import json
import math
import os
from types import SimpleNamespace

import litellm
import pytest
import yaml

from ops_assist import cli
from ops_assist.knowledge.embeddings import HashEmbedder, LiteLLMEmbedder, configured_embedder
from ops_assist.knowledge.index import VectorIndex, corpus_chunks
from ops_assist.security import StateStore


def test_hash_is_deterministic_normalized_and_case_insensitive():
    e = HashEmbedder()
    a, b, empty = e.embed(["Pool pool ERROR", "pool pool error", ""])
    assert a == b == HashEmbedder().embed(["Pool pool ERROR"])[0]
    assert math.isclose(sum(x * x for x in a), 1)
    assert sum(empty) == 0
    assert a != e.embed(["unrelated"])[0]


def test_corpus_and_round_trip(tmp_path):
    chunks = corpus_chunks()
    assert len(chunks) >= 20
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert all("#" in c["id"] and c["title"] and c["text"] for c in chunks)
    index = VectorIndex.build(HashEmbedder())
    store = StateStore()
    path = store.root / store.index_name()
    index.save(store)
    loaded = VectorIndex.load(store, HashEmbedder())
    assert loaded.search("payment database pool", 3) == index.search("payment database pool", 3)
    data = json.loads(path.read_text())
    assert data["dimension"] == 256 and data["embedder"] == HashEmbedder.id
    data["dimension"] = 3
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="dimension"):
        VectorIndex.load(store, HashEmbedder())


def test_mismatched_embedder_refused(tmp_path):
    store = StateStore()
    VectorIndex.build(HashEmbedder()).save(store)
    with pytest.raises(ValueError, match="embedder mismatch"):
        VectorIndex.load(store, LiteLLMEmbedder("example/model"))


def test_litellm_embedder_uses_model_endpoint_and_order(monkeypatch):
    calls = []

    def embedding(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            data=[{"index": 1, "embedding": [0, 3]}, {"index": 0, "embedding": [4, 0]}]
        )

    monkeypatch.setattr(litellm, "embedding", embedding)
    e = LiteLLMEmbedder("example/model", "http://localhost:1234")
    assert e.embed(["a", "b"]) == [[1, 0], [0, 1]]
    assert calls == [
        {"model": "example/model", "input": ["a", "b"], "api_base": "http://localhost:1234"}
    ]
    assert e.embed([]) == [] and len(calls) == 1
    assert e.id != LiteLLMEmbedder("example/model").id
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS", "example/model")
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS_API_BASE", "http://localhost:1234")
    assert configured_embedder().id == e.id


def test_similarity_is_not_relevance():
    results = VectorIndex.build(HashEmbedder()).search("payment latency timeouts", 5)
    assert results[0]["id"] == "payment-processor-incident#1"
    postmortem = " ".join(
        c["text"] for c in corpus_chunks() if c["id"].startswith("payment-processor-incident#")
    )
    assert "external card processor" in postmortem
    pool = " ".join(
        c["text"] for c in corpus_chunks() if c["id"].startswith("payment-pool-incident#")
    )
    assert "connection leak" in pool and "pool exhaustion" in pool
    from importlib.resources import files

    root = files("ops_assist").joinpath("data")
    document = root.joinpath("knowledge/postmortems/payment-processor-incident.md").read_text()
    metadata = yaml.safe_load(document.split("---", 2)[1])
    assert metadata["service"] == "payment-api"
    assert all(metadata[key] for key in ("id", "title", "updated", "owner"))
    assert "decoy" not in document.casefold() and "exercise" not in document.casefold()
    expected = json.loads(root.joinpath("incidents/payment-latency/expected.json").read_text())
    assert "connection pool" in expected["root_cause"]


def test_cli_offline_and_errors(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPS_ASSIST_INDEX_FILE", "index.json")
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS", "hash")
    assert cli.main(["knowledge", "index"]) == 0
    assert "Indexed" in capsys.readouterr().out
    assert cli.main(["knowledge", "search", "payment latency", "-k", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and all("#" in line for line in lines)
    assert cli.main(["knowledge", "search", "x", "-k", "0"]) == 1
    assert "between 1 and 100" in capsys.readouterr().err
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS", "example/model")
    assert cli.main(["knowledge", "search", "x"]) == 1
    assert "embedder mismatch" in capsys.readouterr().err


def test_embedding_response_validation_and_private_endpoint(monkeypatch):
    embedder = LiteLLMEmbedder("example/model", "http://user:secret@localhost")
    assert "secret" not in embedder.id
    monkeypatch.setattr(
        litellm,
        "embedding",
        lambda **kwargs: SimpleNamespace(data=[{"index": 3, "embedding": [1.0]}]),
    )
    with pytest.raises(ValueError, match="does not match"):
        embedder.embed(["one"])


def test_index_rejects_wrong_vector_shapes_and_nonfinite():
    e = HashEmbedder()
    with pytest.raises(ValueError, match="matching"):
        VectorIndex(e, [{}], [])
    with pytest.raises(ValueError, match="dimensions"):
        VectorIndex(e, [{}, {}], [[1], [1, 2]])
    with pytest.raises(ValueError, match="finite"):
        VectorIndex(e, [{}], [[float("nan")]])


def test_packaged_corpus_resources():
    from importlib.resources import files

    root = files("ops_assist").joinpath("data/knowledge")
    assert len(list(root.joinpath("runbooks").iterdir())) >= 6
    assert len(list(root.joinpath("postmortems").iterdir())) >= 4


@pytest.mark.parametrize("link_type", ["symlink", "hardlink"])
def test_index_rejects_links_on_read_and_write(monkeypatch, tmp_path, link_type):
    store = StateStore()
    store.directory()
    target = tmp_path / "target"
    target.write_text("do not overwrite")
    index_path = store.root / store.index_name()
    if link_type == "symlink":
        index_path.symlink_to(target)
    else:
        os.link(target, index_path)
    index = VectorIndex.build(HashEmbedder())
    with pytest.raises((OSError, ValueError)):
        index.save(store)
    with pytest.raises((OSError, ValueError)):
        VectorIndex.load(store, HashEmbedder())
    assert target.read_text() == "do not overwrite"


def test_interrupted_index_write_preserves_old_file(monkeypatch):
    store = StateStore()
    index = VectorIndex.build(HashEmbedder())
    index.save(store)
    path = store.root / store.index_name()
    original = path.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        index.save(store)
    assert path.read_bytes() == original
    assert VectorIndex.load(store, HashEmbedder()).search("payment")
    assert not list(store.root.glob(".knowledge-index-*"))


@pytest.mark.parametrize(
    "name", ["../index.json", "/tmp/index.json", "a/b", "incident-state.json", "audit.jsonl"]
)
def test_index_rejects_invalid_names(monkeypatch, name):
    monkeypatch.setenv("OPS_ASSIST_INDEX_FILE", name)
    with pytest.raises(ValueError):
        StateStore().write_index({})


@pytest.mark.parametrize(
    "exception_type",
    [
        litellm.AuthenticationError,
        litellm.APIConnectionError,
        litellm.RateLimitError,
        litellm.BadRequestError,
    ],
)
@pytest.mark.parametrize("command", ["index", "search"])
def test_cli_provider_errors_are_clean(monkeypatch, capsys, exception_type, command):
    model = "test/model"
    monkeypatch.setenv("OPS_ASSIST_EMBEDDINGS", model)
    store = StateStore()
    # Build a matching index without making a provider call.
    embedder = LiteLLMEmbedder(model)
    VectorIndex(embedder, [{"id": "x#1", "title": "x", "text": "x"}], [[1.0]]).save(store)

    def fail(**kwargs):
        raise exception_type(
            message="private details\nsecond line", model=model, llm_provider="test"
        )

    monkeypatch.setattr(litellm, "embedding", fail)
    args = ["knowledge", command] + (["query"] if command == "search" else [])
    assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert len(captured.err.splitlines()) == 1
    assert model in captured.err and "OPS_ASSIST_EMBEDDINGS=hash" in captured.err
    assert "private details" not in captured.err and "Traceback" not in captured.err


def test_partial_serialization_keeps_previous_index(monkeypatch):
    store = StateStore()
    index = VectorIndex.build(HashEmbedder())
    index.save(store)
    path = store.root / store.index_name()
    original = path.read_bytes()

    def fail_dump(data, stream, **kwargs):
        stream.write('{"partial":')
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", fail_dump)
    with pytest.raises(OSError, match="disk full"):
        index.save(store)
    assert path.read_bytes() == original
    assert not list(store.root.glob(".knowledge-index-*"))


def test_index_follows_configured_state_root(monkeypatch, tmp_path):
    root = tmp_path / "private-state"
    monkeypatch.setenv("OPS_ASSIST_STATE_DIR", str(root))
    monkeypatch.setenv("OPS_ASSIST_INDEX_FILE", "custom.json")
    store = StateStore()
    VectorIndex.build(HashEmbedder()).save(store)
    assert (root / "custom.json").is_file()
    assert VectorIndex.load(store, HashEmbedder()).search("payment")
