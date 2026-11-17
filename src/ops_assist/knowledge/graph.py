"""Validated, bounded traversal of the untrusted service dependency graph."""

import os
from datetime import UTC, date, datetime
from importlib.resources import files

import yaml

from ..observability import ObservationError


class GraphError(ObservationError):
    """The graph or its freshness configuration is unavailable or invalid."""


def _load_graph() -> tuple[list[str], list[dict]]:
    """Read and validate the complete graph before returning any data."""
    try:
        raw = files("ops_assist").joinpath("data/knowledge/graph.yaml").read_text(encoding="utf-8")
        graph = yaml.safe_load(raw)
        if not isinstance(graph, dict):
            raise ValueError("expected a mapping")
        nodes, edges = graph.get("nodes"), graph.get("edges")
        if not isinstance(nodes, list) or not all(isinstance(n, str) and n for n in nodes):
            raise ValueError("nodes must be a list of nonempty strings")
        if not isinstance(edges, list):
            raise ValueError("edges must be a list")
        known = set(nodes)
        result = []
        seen = set()
        for edge in edges:
            if not isinstance(edge, dict):
                raise ValueError("edge must be a mapping")
            start, end, kind, updated = (
                edge.get(k) for k in ("source", "target", "relation", "updated")
            )
            if not all(isinstance(v, str) and v for v in (start, end, kind)):
                raise ValueError("edge source, target and relation must be nonempty strings")
            if start not in known or end not in known:
                raise ValueError("edge refers to an unknown node")
            if kind not in ("calls", "depends_on", "owned_by"):
                raise ValueError("invalid edge relation")
            try:
                parsed = date.fromisoformat(str(updated))
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid edge updated date") from exc
            key = (start, end, kind, parsed.isoformat())
            if key not in seen:
                seen.add(key)
                result.append(
                    {"from": start, "to": end, "type": kind, "updated": parsed.isoformat()}
                )
        return nodes, result
    except Exception as exc:  # noqa: BLE001 - invalid graph must not interrupt callers
        raise GraphError(f"invalid or unreadable graph: {str(exc)[:200]}") from exc


def dependencies(service: str, direction: str = "downstream", depth: int = 1) -> dict:
    """Return reachable nodes and sourced edges; downstream follows dependency arrows."""
    nodes, edges = _load_graph()
    if not isinstance(service, str) or service not in nodes:
        names = ", ".join(n[:300] for n in nodes[:50])[:800]
        raise ValueError(f"unknown service {str(service)[:100]!r}; known services: {names}")
    if direction not in ("downstream", "upstream"):
        raise ValueError("direction must be downstream or upstream")
    if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 3:
        raise ValueError("depth must be between 1 and 3")
    raw_age = os.environ.get("OPS_ASSIST_GRAPH_MAX_AGE_DAYS", "90")
    try:
        if not raw_age.isascii() or not raw_age.isdecimal() or int(raw_age) < 1:
            raise ValueError
        max_age = int(raw_age)
    except ValueError as exc:
        raise GraphError("OPS_ASSIST_GRAPH_MAX_AGE_DAYS must be a positive integer") from exc
    today = datetime.now(UTC).date()
    visited = {service}
    frontier = {service}
    result = []
    for _ in range(depth):
        following = set()
        for edge in edges:
            start, end = (
                (edge["from"], edge["to"])
                if direction == "downstream"
                else (edge["to"], edge["from"])
            )
            if start in frontier:
                following.add(end)
                updated = date.fromisoformat(edge["updated"])
                future = updated > today
                result.append(
                    {
                        "from": edge["from"][:300],
                        "to": edge["to"][:300],
                        "type": edge["type"][:300],
                        "updated": edge["updated"][:300],
                        "stale": future or (today - updated).days > max_age,
                        "source": "data/knowledge/graph.yaml",
                        **({"stale_reason": "date in the future"} if future else {}),
                    }
                )
        frontier = following - visited
        visited.update(following)
    return {
        "nodes": [n[:300] for n in sorted(visited)[:50]],
        "edges": result[:50],
        "truncated": len(visited) > 50 or len(result) > 50 or any(len(n) > 300 for n in visited),
    }


def service_names() -> list[str]:
    """List validated names in the bundled graph."""
    return _load_graph()[0]
