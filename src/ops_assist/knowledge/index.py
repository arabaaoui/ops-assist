"""Small persistent flat cosine index for packaged Markdown knowledge."""

import json
import re
from importlib.resources import files

import yaml

from ..security import StateStore
from .embeddings import Embedder, normalize


def corpus_chunks() -> list[dict]:
    """Read packaged documents and split their body by Markdown headings."""
    root = files("ops_assist").joinpath("data/knowledge")
    chunks = []
    seen = set()
    for folder in ("runbooks", "postmortems"):
        for path in sorted(root.joinpath(folder).iterdir(), key=lambda p: p.name):
            if not path.name.endswith(".md"):
                continue
            text = path.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) != 3 or parts[0].strip():
                raise ValueError(f"invalid front matter: {path.name}")
            meta = yaml.safe_load(parts[1])
            if not isinstance(meta, dict) or not all(
                meta.get(k) for k in ("id", "title", "service", "updated", "owner")
            ):
                raise ValueError(f"incomplete front matter: {path.name}")
            if meta["id"] in seen:
                raise ValueError(f"duplicate document id: {meta['id']}")
            seen.add(meta["id"])
            sections = [s.strip() for s in re.split(r"(?m)(?=^#{1,6}\s)", parts[2]) if s.strip()]
            for number, section in enumerate(sections, 1):
                chunks.append(
                    {"id": f"{meta['id']}#{number}", "title": meta["title"], "text": section}
                )
    return chunks


class VectorIndex:
    """Flat cosine index with an explicit embedding identity and dimension."""

    def __init__(self, embedder: Embedder, chunks: list[dict], vectors: list[list[float]]):
        """Validate and store vectors normalized for cosine similarity."""
        if not chunks or len(chunks) != len(vectors):
            raise ValueError("index must contain matching chunks and vectors")
        self.embedder = embedder
        self.dimension = len(vectors[0])
        if not self.dimension or any(len(v) != self.dimension for v in vectors):
            raise ValueError("inconsistent embedding dimensions")
        self.chunks = chunks
        self.vectors = [normalize(v) for v in vectors]

    @classmethod
    def build(cls, embedder: Embedder) -> "VectorIndex":
        """Embed every section in the packaged corpus."""
        chunks = corpus_chunks()
        return cls(embedder, chunks, embedder.embed([c["text"] for c in chunks]))

    def save(self, store: StateStore) -> None:
        """Persist the index as JSON."""
        store.write_index(
            {
                "embedder": self.embedder.id,
                "dimension": self.dimension,
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
            index = cls(embedder, data["chunks"], data["vectors"])
            if data["dimension"] != index.dimension:
                raise ValueError("index dimension mismatch")
            return index
        except (KeyError, TypeError, IndexError) as exc:
            raise ValueError("invalid knowledge index") from exc

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return up to k highest-scoring sections; results are untrusted data."""
        if not 1 <= k <= 100:
            raise ValueError("k must be between 1 and 100")
        vectors = self.embedder.embed([query])
        if len(vectors) != 1 or len(vectors[0]) != self.dimension:
            raise ValueError("query embedding dimension mismatch")
        vector = normalize(vectors[0])
        scored = [
            {**chunk, "score": sum(a * b for a, b in zip(vector, row, strict=True))}
            for chunk, row in zip(self.chunks, self.vectors, strict=True)
        ]
        return sorted(scored, key=lambda item: (-item["score"], item["id"]))[:k]
