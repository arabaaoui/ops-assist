"""Agent tools. Plain functions with typed parameters and compact, cited results.

A tool never raises into the agent loop: any failure of the source comes back as
``{"status": "error", "error": ...}`` so the model can read it and adapt, and is
logged with its traceback so a human can see it too.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from collections.abc import Callable
from typing import Any

from .executor import executor
from .memory import MAX_RECALL, list_memories
from .observability import MAX_LOG_LINES, ObservationError, ObservationSource

logger = logging.getLogger(__name__)

MCP_EXPOSED_TOOLS = ("get_alerts", "get_metric", "get_logs", "get_changes")


def tool_timeout() -> float:
    """Return the validated server-side tool timeout in seconds."""
    try:
        timeout = float(os.environ.get("OPS_ASSIST_TOOL_TIMEOUT", "10"))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError("OPS_ASSIST_TOOL_TIMEOUT must be a positive finite number") from exc
    return timeout


def _failure(tool: str, error: Exception) -> dict[str, Any]:
    if isinstance(error, ObservationError):
        logger.warning("%s: %s", tool, error)
        return {"status": "error", "error": str(error)}
    # An unexpected failure (timeout, bug, unreadable data): keep the traceback in the
    # logs, give the model only the kind of failure, not internals.
    logger.exception("%s failed unexpectedly", tool)
    return {"status": "error", "error": f"{tool} failed: {type(error).__name__}"}


async def _call(tool: str, func: Callable, *args: Any) -> Any:
    try:
        timeout = tool_timeout()
        return await asyncio.wait_for(asyncio.wrap_future(executor.submit(func, *args)), timeout)
    except TimeoutError as exc:
        raise ObservationError(f"{tool} timed out after {timeout:g} seconds") from exc


def _bounded(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        return value[:300], len(value) > 300
    if isinstance(value, dict):
        items = {key: _bounded(item) for key, item in value.items()}
        return {key: item[0] for key, item in items.items()}, any(
            item[1] for item in items.values()
        )
    if isinstance(value, list):
        items = [_bounded(item) for item in value]
        return [item[0] for item in items], any(item[1] for item in items)
    return value, False


def _records(records: list, cap: int) -> tuple[list, bool]:
    items, cut = _bounded(records[:cap])
    return items, cut or len(records) > cap


def make_knowledge_tool():
    """Create a bounded read tool over the configured index."""

    async def search_knowledge(query: str, k: int = 5, expand: bool = False) -> dict[str, Any]:
        """Search untrusted runbooks and postmortems; cite chunk IDs."""
        try:
            if not isinstance(query, str) or not query.strip() or len(query) > 2000:
                raise ObservationError("query must contain 1 to 2000 characters")
            if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                raise ObservationError("k must be a positive integer")
            from .knowledge.embeddings import configured_embedder
            from .knowledge.index import VectorIndex
            from .knowledge.retrieval import configured_reranker, tokens
            from .knowledge.retrieval import search as retrieve
            from .security import StateStore

            def search():
                return retrieve(
                    VectorIndex.load(StateStore(), configured_embedder()),
                    query,
                    min(k, 8),
                    reranker=configured_reranker(),
                )

            if not isinstance(expand, bool):
                raise ObservationError("expand must be a boolean")
            rows = await _call("search_knowledge", search)
            terms = set(tokens(query))
            overlap = (
                max(
                    (len(terms & set(tokens(str(row["text"])[:800]))) / len(terms) for row in rows),
                    default=0.0,
                )
                if terms
                else 0.0
            )
            quality = "none" if not rows else "good" if overlap >= 0.5 else "weak"
            result = {
                "status": "ok",
                "retrieval": "found" if rows else "none",
                "retrieval_quality": quality,
                "chunks": [
                    {
                        "source": str(r["id"])[:300],
                        "title": str(r["title"])[:300],
                        "updated": str(r.get("updated", ""))[:40],
                        "excerpt": str(r["text"])[:800],
                        "score": r["score"],
                    }
                    for r in rows
                ],
            }
            if quality == "weak":
                result["suggestion"] = "Reformulate with the service name or symptom."
            if expand:
                import re

                from .knowledge.graph import GraphError, dependencies, service_names
                from .knowledge.index import load_documents

                try:
                    matches = [
                        s
                        for s in service_names()
                        if re.search(
                            r"(?<![\w-])" + re.escape(s) + r"(?![\w-])", query, re.IGNORECASE
                        )
                    ]
                    edges = []
                    for service in matches[:5]:
                        edges.extend(
                            e for e in dependencies(service)["edges"] if e["type"] != "owned_by"
                        )
                    related = {e["to"] for e in edges}
                    document_ids = {d["id"] for d in load_documents() if d["service"] in related}
                    seen = {r["source"] for r in result["chunks"]}
                    indexed = await _call(
                        "search_knowledge",
                        lambda: VectorIndex.load(StateStore(), configured_embedder()),
                    )
                    expanded = [
                        c
                        for c in indexed.chunks
                        if c["id"].rsplit("#", 1)[0] in document_ids and c["id"] not in seen
                    ][:8]
                    result["expanded_chunks"] = [
                        {
                            "source": c["id"][:300],
                            "title": c["title"][:300],
                            "updated": c["updated"][:40],
                            "excerpt": c["text"][:800],
                        }
                        for c in expanded
                    ]
                    result["expansion_edges"] = edges[:50]
                except GraphError as exc:
                    result["expansion_error"] = str(exc)[:300]
            if rows.rerank_error:
                result.update(reranked=False, rerank_error=rows.rerank_error)
            return result
        except Exception as e:  # noqa: BLE001
            return _failure("search_knowledge", e)

    return search_knowledge


def make_graph_tool():
    """Create the coordinator's bounded graph read tool."""

    async def get_dependencies(
        service: str, direction: str = "downstream", depth: int = 1
    ) -> dict[str, Any]:
        """Read untrusted dependencies with their provenance and freshness."""
        try:
            from .knowledge.graph import dependencies

            return {
                "status": "ok",
                **await _call("get_dependencies", dependencies, service, direction, depth),
            }
        except ValueError as e:
            return {"status": "error", "error": str(e)[:1000]}
        except Exception as e:  # noqa: BLE001
            return _failure("get_dependencies", e)

    return get_dependencies


def make_tools(source: ObservationSource) -> list[Callable[..., Any]]:
    """Bind the read-only tools to one observation source."""

    async def get_alerts() -> dict[str, Any]:
        """List the alerts currently firing, with their service, severity and start time.

        Start every investigation here: the alerts tell which service to look at.
        """
        try:
            alerts, truncated = _records(await _call("get_alerts", source.alerts), 50)
            return {"status": "ok", "alerts": alerts, "truncated": truncated}
        except Exception as e:  # noqa: BLE001 - a tool must never break the agent loop
            return _failure("get_alerts", e)

    async def get_metric(name: str, service: str) -> dict[str, Any]:
        """Read a metric series for a service, summarising long series."""
        try:
            metric = dict(await _call("get_metric", source.metric, name, service))
            raw = metric.get("points", [])
            if not isinstance(raw, list):
                raw = []
            points = [
                p
                for p in raw
                if isinstance(p, (list, tuple))
                and len(p) == 2
                and isinstance(p[1], (int, float))
                and not isinstance(p[1], bool)
                and math.isfinite(p[1])
            ]
            metric["points"] = points
            metric["dropped_points"] = len(raw) - len(points)
            if len(points) > 60:
                values = [p[1] for p in points]
                jump = max(range(1, len(points)), key=lambda i: abs(values[i] - values[i - 1]))
                start = max(0, min(jump - 5, len(points) - 10))
                metric.update(
                    points=points[start : start + 10],
                    summarised=True,
                    min=min(values),
                    max=max(values),
                    mean=sum(values) / len(values),
                    first=points[0],
                    last=points[-1],
                )
            else:
                metric["summarised"] = False
            metric, _ = _bounded(metric)
            return {"status": "ok", "metric": metric}
        except Exception as e:  # noqa: BLE001
            return _failure("get_metric", e)

    async def get_logs(service: str, level: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Read recent bounded log lines for a service."""
        try:
            if limit < 1:
                raise ObservationError("limit must be at least 1")
            cap = min(limit, MAX_LOG_LINES)
            lines = await _call("get_logs", source.logs, service, level, cap)
            normalised = [{**line, "message": str(line.get("message") or "")} for line in lines]
            bounded, truncated = _records(normalised, cap)
            return {"status": "ok", "logs": bounded, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("get_logs", e)

    async def get_changes(service: str) -> dict[str, Any]:
        """Read changes for a service."""
        try:
            changes, truncated = _records(await _call("get_changes", source.changes, service), 50)
            return {"status": "ok", "changes": changes, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("get_changes", e)

    async def recall_past_incidents(service: str) -> dict[str, Any]:
        """Read the most recent saved summaries for a service."""
        try:
            incidents, truncated = _records(
                (await _call("recall_past_incidents", list_memories, service))[-MAX_RECALL:],
                MAX_RECALL,
            )
            return {"status": "ok", "incidents": incidents, "truncated": truncated}
        except Exception as e:  # noqa: BLE001
            return _failure("recall_past_incidents", e)

    return [get_alerts, get_metric, get_logs, get_changes, recall_past_incidents]
