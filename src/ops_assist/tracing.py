"""Opt-in, content-free investigation tracing with an isolated OTel provider."""

import os
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_current = ContextVar("ops_assist_tracer", default=None)


def _provider():
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError as exc:
        raise ValueError("Tracing requires the optional otel extra: uv sync --extra otel") from exc
    provider = TracerProvider(resource=Resource.create({"service.name": "ops-assist"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


@contextmanager
def investigation():
    """Record a root span only when enabled; finish and flush on every exit."""
    if os.environ.get("OPS_ASSIST_OTEL") != "1":
        yield
        return
    provider = _provider()
    tracer = provider.get_tracer("ops_assist")
    token = _current.set(tracer)
    try:
        with tracer.start_as_current_span(
            "investigation", record_exception=False, set_status_on_exception=False
        ) as span:
            try:
                yield
            except BaseException:
                span.set_attribute("outcome", "error")
                raise
            else:
                span.set_attribute("outcome", "ok")
    finally:
        _current.reset(token)
        provider.shutdown()


def start(name, attributes):
    """Start a child span containing only explicitly selected metadata."""
    tracer = _current.get()
    if tracer is None:
        return None
    return tracer.start_span(name, attributes=attributes)


def finish(span, attributes):
    """Finish a span without recording arguments, results, or exceptions."""
    if span is not None:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        span.end()
