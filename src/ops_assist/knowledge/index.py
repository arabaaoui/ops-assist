"""Small persistent flat cosine index for packaged Markdown knowledge."""

import hashlib
import json
import re
from importlib.resources import files

import yaml

from ..security import StateStore
from .embeddings import Embedder, normalize


def parse_document(text: str, name: str) -> dict:
    """Validate front matter and calculate a content checksum."""
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"invalid front matter: {name}")
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict) or not all(
        meta.get(k) for k in ("id", "title", "service", "updated", "owner")
    ):
        raise ValueError(f"incomplete front matter: {name}")
    return {
        "id": str(meta["id"]),
        "title": str(meta["title"]),
        "service": str(meta["service"]),
        "updated": str(meta["updated"]),
        "body": parts[2],
        "checksum": hashlib.sha256(text.encode()).hexdigest(),
    }


def load_documents(*, include_approved: bool = True) -> list[dict]:
    """Load packaged and human-approved local documents, never drafts."""
    packaged = files("ops_assist").joinpath("data/knowledge")
    paths = [
        path
        for folder in ("runbooks", "postmortems")
        for path in sorted(packaged.joinpath(folder).iterdir(), key=lambda p: p.name)
        if path.name.endswith(".md")
    ]
    documents, seen = [], set()
    sources = [(path.name, path.read_text(encoding="utf-8")) for path in paths]
    if include_approved:
        store = StateStore()
        sources.extend(
            (name, store.read_knowledge("approved", name))
            for name in store.list_knowledge("approved")
            if name.endswith(".md")
        )
    for name, text in sources:
        doc = parse_document(text, name)
        if doc["id"] in seen:
            raise ValueError(f"duplicate document id: {doc['id']}")
        seen.add(doc["id"])
        documents.append(doc)
    return documents


def chunk_document(document: dict) -> list[dict]:
    """Split one document at headings."""
    sections = [s.strip() for s in re.split(r"(?m)(?=^#{1,6}\s)", document["body"]) if s.strip()]
    return [
        {
            "id": f"{document['id']}#{n}",
            "title": document["title"],
            "updated": document["updated"],
            "text": section,
        }
        for n, section in enumerate(sections, 1)
    ]


def corpus_chunks() -> list[dict]:
    """Load and chunk the corpus."""
    return [c for d in load_documents() for c in chunk_document(d)]


class VectorIndex:
    """Flat cosine index with an explicit embedding identity and dimension."""

    def __init__(
        self,
        embedder: Embedder,
        chunks: list[dict],
        vectors: list[list[float]],
        manifest: list[dict] | None = None,
    ):
        """Validate and store vectors normalized for cosine similarity."""
        if len(chunks) != len(vectors):
            raise ValueError("index must contain matching chunks and vectors")
        self.manifest = manifest or []
        self.embedder = embedder
        self.dimension = len(vectors[0]) if vectors else 0
        if (vectors and not self.dimension) or any(len(v) != self.dimension for v in vectors):
            raise ValueError("inconsistent embedding dimensions")
        self.chunks = chunks
        self.vectors = [normalize(v) for v in vectors]

    @classmethod
    def build(
        cls,
        embedder: Embedder,
        previous: "VectorIndex | None" = None,
        *,
        include_approved: bool = True,
    ) -> "VectorIndex":
        """Load, chunk, embed changed documents and assemble the index."""
        docs = load_documents(include_approved=include_approved)
        old_manifest = (
            {d["id"]: d for d in previous.manifest}
            if previous and previous.embedder.id == embedder.id
            else {}
        )
        old_rows = (
            {c["id"]: (c, v) for c, v in zip(previous.chunks, previous.vectors, strict=True)}
            if previous
            else {}
        )
        chunks, vectors, manifest = [], [], []
        for doc in docs:
            parts = chunk_document(doc)
            entry = {"id": doc["id"], "checksum": doc["checksum"], "chunk_count": len(parts)}
            manifest.append(entry)
            reusable = old_manifest.get(doc["id"]) == entry and all(
                c["id"] in old_rows and old_rows[c["id"]][0] == c for c in parts
            )
            rows = (
                [old_rows[c["id"]][1] for c in parts]
                if reusable
                else embedder.embed([c["text"] for c in parts])
            )
            if len(rows) != len(parts):
                raise ValueError("embedding response does not match chunks")
            chunks.extend(parts)
            vectors.extend(rows)
        return cls(embedder, chunks, vectors, manifest)

    def save(self, store: StateStore) -> None:
        """Persist the index as JSON."""
        store.write_index(
            {
                "embedder": self.embedder.id,
                "dimension": self.dimension,
                "manifest": self.manifest,
                "chunks": self.chunks,
                "vectors": self.vectors,
            }
        )

    @classmethod
    def load(cls, store: StateStore, embedder: Embedder) -> "VectorIndex":
        """Load only indexes made with the same embedding space."""
        try:
            with store.open_index() as stream:
                data = json.load(stream)
            if data["embedder"] != embedder.id:
                raise ValueError("index embedder mismatch; rebuild the index")
            index = cls(embedder, data["chunks"], data["vectors"], data.get("manifest", []))
            if data["dimension"] != index.dimension:
                raise ValueError("index dimension mismatch")
            return index
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("invalid knowledge index") from exc

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return up to k highest-scoring sections; results are untrusted data."""
        if not 1 <= k <= 100:
            raise ValueError("k must be between 1 and 100")
        if not self.chunks:
            return []
        vectors = self.embedder.embed([query])
        if len(vectors) != 1 or len(vectors[0]) != self.dimension:
            raise ValueError("query embedding dimension mismatch")
        vector = normalize(vectors[0])
        from .living import freshness

        scored = [
            {
                **chunk,
                **freshness(chunk.get("updated", "")),
                "score": sum(a * b for a, b in zip(vector, row, strict=True)),
            }
            for chunk, row in zip(self.chunks, self.vectors, strict=True)
        ]
        return sorted(scored, key=lambda item: (-item["score"], item["id"]))[:k]
