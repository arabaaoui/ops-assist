"""Configurable text embeddings, including a deterministic offline baseline."""

import hashlib
import math
import os
import re
from typing import Protocol

import litellm

from .. import call_metadata


class EmbeddingProviderError(ValueError):
    """A provider call failed without exposing its potentially sensitive details."""


class Embedder(Protocol):
    """Embed texts in a stable vector space identified by id."""

    @property
    def id(self) -> str:
        """Identify the vector space."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text."""
        ...


def normalize(vector: list[float]) -> list[float]:
    """Normalize a finite vector; retain the zero vector."""
    if not vector or any(not math.isfinite(x) for x in vector):
        raise ValueError("embedding must be a non-empty finite vector")
    norm = math.sqrt(sum(x * x for x in vector))
    if not math.isfinite(norm):
        raise ValueError("embedding norm must be finite")
    return [x / norm for x in vector] if norm else vector


class HashEmbedder:
    """Token-hashing bag of words with deterministic SHA-256 buckets."""

    id = "hash-sha256-bow-256-v1"
    dimension = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Hash case-folded words into a normalized frequency vector."""
        result = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in re.findall(r"\w+", text.casefold()):
                bucket = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
                vector[bucket % self.dimension] += 1
            result.append(normalize(vector))
        return result


class LiteLLMEmbedder:
    """Embedding provider accessed through LiteLLM."""

    def __init__(self, model: str, api_base: str | None = None):
        """Store the model and optional endpoint."""
        if not model.strip():
            raise ValueError("embedding model must not be empty")
        self.model = model
        self.api_base = api_base

    @property
    def id(self) -> str:
        """Include endpoint because identical names can denote different models."""
        endpoint = hashlib.sha256((self.api_base or "").encode()).hexdigest()
        return f"litellm:{self.model}:{endpoint}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Call LiteLLM and normalize embeddings in input order."""
        if not texts:
            return []
        kwargs = {"api_base": self.api_base} if self.api_base else {}
        try:
            response = litellm.embedding(
                model=self.model, input=texts, metadata=call_metadata("embeddings"), **kwargs
            )
        except Exception as exc:
            model = " ".join(self.model.split())
            raise EmbeddingProviderError(
                f"Embedding provider failed for {model}; "
                "use OPS_ASSIST_EMBEDDINGS=hash for offline search"
            ) from exc
        data = sorted(response.data, key=lambda item: item["index"])
        if [item["index"] for item in data] != list(range(len(texts))):
            raise ValueError("embedding response does not match input")
        return [normalize(item["embedding"]) for item in data]


def configured_embedder() -> Embedder:
    """Construct the embedder selected by the environment."""
    model = os.environ.get("OPS_ASSIST_EMBEDDINGS", "hash").strip()
    if model == "hash":
        return HashEmbedder()
    return LiteLLMEmbedder(model, os.environ.get("OPS_ASSIST_EMBEDDINGS_API_BASE") or None)
