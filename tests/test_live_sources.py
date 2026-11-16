import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from contract import ObservationContract

from ops_assist.observability import (
    CompositeSource,
    LokiSource,
    ObservationError,
    PrometheusSource,
    ReplaySource,
    source_from_env,
)
from ops_assist.tools import make_tools

RECORDINGS = Path(__file__).parent / "recordings"


def handler(request):
    if request.url.path == "/api/v1/alerts":
        file = "prometheus_alerts.json"
    elif request.url.path == "/api/v1/query_range":
        file = "prometheus_metric.json"
        if not request.url.params["query"].startswith("latency{"):
            return httpx.Response(200, json={"status": "success", "data": {"result": []}})
    elif request.url.path == "/loki/api/v1/label/service/values":
        file = "loki_services.json"
    else:
        file = "loki_logs.json"
        payload = json.loads((RECORDINGS / file).read_text())
        query = request.url.params["query"]
        streams = payload["data"]["result"]
        streams = [
            stream
            for stream in streams
            if f'service="{stream["stream"]["service"]}"' in query
            and (",level=" not in query or f'level="{stream["stream"]["level"]}"' in query)
        ]
        payload["data"]["result"] = streams
        return httpx.Response(200, json=payload)
    return httpx.Response(200, json=json.loads((RECORDINGS / file).read_text()))


def sources():
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PrometheusSource("http://example", client=client), LokiSource(
        "http://example", client=client
    )


class TestLiveContract(ObservationContract):
    @pytest.fixture(params=["prometheus", "loki", "composite"])
    def source(self, request):
        prometheus, loki = sources()
        return {
            "prometheus": prometheus,
            "loki": loki,
            "composite": CompositeSource(prometheus, loki, ReplaySource("payment-latency")),
        }[request.param]

    @pytest.fixture
    def sample(self):
        return {
            "service": "payment-api",
            "silent_service": "orders-db",
            "metric": "latency",
            "foreign_metric": "foreign",
            "unknown_metric": "nope",
        }


def test_connector_paths_and_unsupported_changes():
    prometheus, loki = sources()
    assert prometheus.alerts()[0]["name"] == "Latency"
    assert prometheus.metric("latency", "payment-api")["points"][0][1] == 0.5
    assert loki.logs("payment-api", level="error", limit=1)[0]["message"] == "failed"
    for source in (prometheus, loki):
        with pytest.raises(ObservationError, match="changes are not supported"):
            source.changes("payment-api")
    with pytest.raises(ObservationError, match="invalid metric name"):
        prometheus.metric("x} or up", "s")


def test_http_errors_and_invalid_responses():
    for response in (
        httpx.Response(500),
        httpx.Response(200, json={"status": "error"}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json="x"),
    ):
        client = httpx.Client(
            transport=httpx.MockTransport(lambda request, response=response: response)
        )
        with pytest.raises(ObservationError, match="request failed"):
            PrometheusSource("http://example", client=client).alerts()


def test_source_selection(monkeypatch):
    assert isinstance(source_from_env("payment-latency"), ReplaySource)
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "live")
    with pytest.raises(ValueError, match="requires"):
        source_from_env("payment-latency")
    monkeypatch.setenv("OPS_ASSIST_PROMETHEUS_URL", "http://prometheus")
    monkeypatch.setenv("OPS_ASSIST_LOKI_URL", "http://loki")
    assert isinstance(source_from_env("payment-latency"), CompositeSource)
    monkeypatch.setenv("OPS_ASSIST_HTTP_TIMEOUT", "0")
    with pytest.raises(ValueError, match="TIMEOUT"):
        source_from_env("payment-latency")
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "invalid")
    with pytest.raises(ValueError, match="SOURCE"):
        source_from_env("payment-latency")


def test_timeout_does_not_block_event_loop(monkeypatch):
    monkeypatch.setenv("OPS_ASSIST_TOOL_TIMEOUT", "0.02")

    class Slow:
        def alerts(self):
            time.sleep(0.15)
            return []

    async def run():
        tool = make_tools(Slow())[0]
        task = asyncio.create_task(tool())
        await asyncio.sleep(0.04)
        assert task.done()
        assert (await task)["error"] == "get_alerts timed out after 0.02 seconds"

    asyncio.run(run())


def test_adk_exposes_typed_async_tool_declaration():
    from google.adk.tools.function_tool import FunctionTool

    declaration = FunctionTool(make_tools(ReplaySource("payment-latency"))[2])._get_declaration()
    assert declaration.name == "get_logs"
    assert "log" in declaration.description.lower()
    assert set(declaration.parameters_json_schema["properties"]) == {"service", "level", "limit"}
    assert declaration.parameters_json_schema["required"] == ["service"]


def test_live_changes_require_an_explicit_file(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_SOURCE", "live")
    monkeypatch.setenv("OPS_ASSIST_PROMETHEUS_URL", "http://prometheus")
    monkeypatch.setenv("OPS_ASSIST_LOKI_URL", "http://loki")
    source = source_from_env("nonexistent-incident")
    with pytest.raises(
        ObservationError,
        match="changes are not available in live mode; set OPS_ASSIST_CHANGES_FILE",
    ):
        source.changes("payment-api")
    path = tmp_path / "changes.json"
    path.write_text(
        json.dumps(
            [
                {"id": "older", "ts": "2026-01-01", "service": "payment-api"},
                {"id": "newer", "ts": "2026-01-02", "service": "payment-api"},
                {"id": "other", "ts": "2026-01-03", "service": "other"},
            ]
        )
    )
    monkeypatch.setenv("OPS_ASSIST_CHANGES_FILE", str(path))
    source = source_from_env("nonexistent-incident")
    changes = source.changes("payment-api")
    assert [item["id"] for item in changes] == ["newer", "older"]
    assert all(str(path) in item["source"] for item in changes)
    with pytest.raises(ObservationError, match="known services"):
        source.changes("absent")
    path.write_text("[]x")
    with pytest.raises(ObservationError, match="cannot read changes file"):
        source.changes("payment-api")
    path.write_text('[{"id": "broken"}]')
    with pytest.raises(ObservationError, match="cannot read changes file"):
        source.changes("payment-api")
    path.unlink()
    with pytest.raises(ObservationError, match="cannot read changes file"):
        source.changes("payment-api")


def test_loki_filters_level_before_server_limit():
    payload = json.loads((RECORDINGS / "loki_many_logs.json").read_text())
    requests = []

    def serve(request):
        requests.append(request)
        query = request.url.params["query"]
        streams = payload["data"]["result"]
        if 'level="error"' in query:
            streams = [stream for stream in streams if stream["stream"]["level"] == "error"]
        values = sorted(
            (
                (int(ts), line, stream["stream"])
                for stream in streams
                for ts, line in stream["values"]
            ),
            reverse=True,
        )
        values = values[: int(request.url.params["limit"])]
        result = [{"stream": labels, "values": [[str(ts), line]]} for ts, line, labels in values]
        return httpx.Response(200, json={"status": "success", "data": {"result": result}})

    source = LokiSource("http://example", client=httpx.Client(transport=httpx.MockTransport(serve)))
    assert source.logs("payment-api", "error")[0]["message"] == "older error"
    assert 'level="error"' in requests[0].url.params["query"]
    assert len(source.logs("payment-api", limit=200)) == 200


def test_capabilities_are_pinned():
    assert PrometheusSource.capabilities == frozenset({"alerts", "metric"})
    assert LokiSource.capabilities == frozenset({"logs"})


def test_blocked_worker_does_not_delay_process_exit():
    script = r"""
import asyncio
import threading
from ops_assist.tools import make_tools

class Stuck:
    def alerts(self):
        threading.Event().wait()

async def main():
    loop = asyncio.get_running_loop()
    def tick():
        loop.call_soon(tick)
    loop.call_soon(tick)
    result = await make_tools(Stuck())[0]()
    assert result == {"status": "error", "error": "get_alerts timed out after 0.02 seconds"}
    print("returned", flush=True)

asyncio.run(main())
"""
    env = dict(os.environ, OPS_ASSIST_TOOL_TIMEOUT="0.02", LITELLM_LOCAL_MODEL_COST_MAP="True")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert "returned" in result.stdout


def test_tool_executor_bounds_workers_and_queue():
    import threading

    from ops_assist.executor import ToolExecutor

    started = threading.Event()
    release = threading.Event()
    ran_queued = threading.Event()
    pool = ToolExecutor(workers=1, capacity=1)

    def block():
        started.set()
        release.wait()
        return "done"

    first = pool.submit(block)
    assert started.wait(2)
    queued = pool.submit(ran_queued.set)
    with pytest.raises(ObservationError, match="pool is full"):
        pool.submit(lambda: None)
    assert queued.cancel()
    release.set()
    assert first.result(timeout=2) == "done"
    pool._queue.join()
    assert not ran_queued.is_set()


def test_loki_unknown_service_names_known_services():
    _, loki = sources()
    with pytest.raises(ObservationError, match=r"unknown service 'absent'.*orders-db.*payment-api"):
        loki.logs("absent")


@pytest.mark.parametrize(
    ("index", "args", "name"),
    [
        (0, (), "get_alerts"),
        (1, ("metric", "service"), "get_metric"),
        (2, ("service",), "get_logs"),
        (3, ("service",), "get_changes"),
        (4, ("service",), "recall_past_incidents"),
    ],
)
def test_each_tool_names_its_timeout(monkeypatch, index, args, name):
    import ops_assist.tools as tools

    monkeypatch.setenv("OPS_ASSIST_TOOL_TIMEOUT", "0.01")

    def slow(*args):
        time.sleep(0.05)
        return []

    class SlowSource:
        alerts = staticmethod(slow)
        metric = staticmethod(slow)
        logs = staticmethod(slow)
        changes = staticmethod(slow)

    monkeypatch.setattr(tools, "list_memories", slow)
    result = asyncio.run(make_tools(SlowSource())[index](*args))
    assert result == {"status": "error", "error": f"{name} timed out after 0.01 seconds"}
