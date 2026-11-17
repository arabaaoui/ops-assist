import builtins
import json
import os

import pytest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from test_agent_loop import ScriptedModel

from ops_assist import tracing
from ops_assist.observability import ReplaySource
from ops_assist.run import investigate


class LogsModel(ScriptedModel):
    async def generate_content_async(self, llm_request, stream=False):
        responses = [
            p.function_response
            for c in llm_request.contents
            for p in c.parts or []
            if p.function_response
        ]
        if not responses:
            part = types.Part(
                function_call=types.FunctionCall(name="get_logs", args={"service": "payment-api"})
            )
        else:
            report = {
                "summary": "Logs examined",
                "status": "insufficient_data",
                "facts": [],
                "hypotheses": [],
                "unknowns": ["cause"],
            }
            part = types.Part(text=json.dumps(report))
        yield LlmResponse(
            content=types.Content(role="model", parts=[part]),
            model_version="scripted",
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=3, candidates_token_count=2, total_token_count=5
            ),
        )


def test_investigation_spans_are_content_free(monkeypatch):
    secret = "fictional-unguessable-secret-3497"
    source = ReplaySource("payment-latency")
    original = source.logs

    def logs(*args, **kwargs):
        return [{**line, "message": secret} for line in original(*args, **kwargs)]

    source.logs = logs
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setenv("OPS_ASSIST_OTEL", "1")
    monkeypatch.setattr(tracing, "_provider", lambda: provider)
    investigate(f"Investigate {secret}", source=source, model=LogsModel(seen=[]), save_memory=False)
    spans = exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "investigation")
    models = [s for s in spans if s.name == "model_call"]
    tool = next(s for s in spans if s.name == "tool_call")
    assert root.attributes["outcome"] == "ok"
    assert len(models) == 2 and all(s.attributes["agent"] == "ops_assist" for s in models)
    assert all(
        s.attributes["input_tokens"] == 3 and s.attributes["output_tokens"] == 2 for s in models
    )
    assert all("model" in s.attributes for s in models)
    assert tool.attributes["tool"] == "get_logs" and tool.attributes["outcome"] == "ok"
    assert all(s.parent.span_id == root.context.span_id for s in [*models, tool])
    assert tool.end_time >= tool.start_time
    assert secret not in str([(dict(s.attributes), s.events, s.status.description) for s in spans])


def test_disabled_and_missing_extra(monkeypatch):
    monkeypatch.setattr(tracing, "_provider", lambda: pytest.fail("provider started"))
    monkeypatch.delenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", raising=False)
    investigate("Why?", model=ScriptedModel(seen=[]), save_memory=False)
    assert os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "false"
    monkeypatch.undo()
    monkeypatch.setenv("OPS_ASSIST_OTEL", "1")
    original_import = builtins.__import__

    def missing_exporter(name, *args, **kwargs):
        if name == "opentelemetry.exporter.otlp.proto.http.trace_exporter":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_exporter)
    with pytest.raises(ValueError, match="optional otel extra"):
        tracing._provider()


def test_failed_investigation_ends_without_recording_exception(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setenv("OPS_ASSIST_OTEL", "1")
    monkeypatch.setattr(tracing, "_provider", lambda: provider)
    with pytest.raises(RuntimeError):
        with tracing.investigation():
            raise RuntimeError("fictional-private-message")
    span = exporter.get_finished_spans()[0]
    assert span.attributes["outcome"] == "error"
    assert not span.events
    assert "fictional-private-message" not in str(span.attributes)
