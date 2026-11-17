"""Reproducible offline retrieval evaluation."""

from importlib.resources import files

import yaml

from .embeddings import HashEmbedder
from .index import VectorIndex
from .retrieval import KeywordOverlapReranker, search


def metrics(
    rankings: list[list[str]], expected: list[list[str]], k: int = 5
) -> tuple[float, float]:
    """Compute mean recall at k and mean reciprocal rank at k."""
    if len(rankings) != len(expected) or not rankings or k < 1:
        raise ValueError("evaluation requires matching nonempty cases and positive k")
    recalls, reciprocal = [], []
    for ranking, answers in zip(rankings, expected, strict=True):
        relevant = set(answers)
        if not relevant:
            raise ValueError("each question needs expected chunk IDs")
        top = ranking[:k]
        recalls.append(len(set(top) & relevant) / len(relevant))
        reciprocal.append(
            next(
                (1 / rank for rank, identifier in enumerate(top, 1) if identifier in relevant), 0.0
            )
        )
    return sum(recalls) / len(recalls), sum(reciprocal) / len(reciprocal)


def evaluate() -> dict[str, tuple[float, float]]:
    """Evaluate all methods using a fresh hash index and packaged questions."""
    cases = yaml.safe_load(
        files("ops_assist")
        .joinpath("data/knowledge/eval/questions.yaml")
        .read_text(encoding="utf-8")
    )
    index = VectorIndex.build(HashEmbedder(), include_approved=False)
    identifiers = {chunk["id"] for chunk in index.chunks}
    if any(not set(case["expected"]) <= identifiers for case in cases):
        raise ValueError("evaluation references unknown chunk IDs")
    output = {}
    for label, mode, reranker in [
        ("vector", "vector", None),
        ("bm25", "bm25", None),
        ("hybrid", "hybrid", None),
        ("hybrid+rerank", "hybrid", KeywordOverlapReranker()),
    ]:
        rankings = [
            [row["id"] for row in search(index, case["question"], 5, mode=mode, reranker=reranker)]
            for case in cases
        ]
        output[label] = metrics(rankings, [case["expected"] for case in cases])
    return output
