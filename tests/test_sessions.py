import asyncio
import os

import pytest
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from test_agent_loop import ScriptedModel

from ops_assist import cli
from ops_assist.config import load_settings
from ops_assist.run import investigate


@pytest.fixture(autouse=True)
def sandbox_event_loop_wakeup(monkeypatch):
    """Wake the selector when this sandbox suppresses cross-thread socket wakeups."""
    # Some sandboxes lose cross-thread selector wakeups; opt in only there.
    if os.environ.get("OPS_ASSIST_TEST_ASYNC_TICK") != "1":
        return
    original_run = asyncio.run

    def run_with_wakeup(coro, **kwargs):
        async def wrapped():
            async def tick():
                while True:
                    await asyncio.sleep(0.01)

            task = asyncio.create_task(tick())
            try:
                return await coro
            finally:
                task.cancel()

        return original_run(wrapped(), **kwargs)

    monkeypatch.setattr(asyncio, "run", run_with_wakeup)


def test_session_settings_defaults_and_override():
    assert load_settings(env={}).session_db is None
    assert load_settings(env={"OPS_ASSIST_SESSION_DB": ""}).session_db is None
    assert (
        load_settings(env={"OPS_ASSIST_SESSION_DB": "/tmp/example.db"}).session_db
        == "/tmp/example.db"
    )


def test_sqlite_session_persists_and_cli_resumes(monkeypatch, tmp_path, capsys):
    db = tmp_path / "sessions.db"
    monkeypatch.setenv("OPS_ASSIST_SESSION_DB", str(db))
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path / "memory"))
    report, trace = investigate("First question", model=ScriptedModel(seen=[]))
    assert db.is_file() and trace.session_id

    async def read():
        service = SqliteSessionService(str(db))
        return await service.get_session(
            app_name="ops_assist", user_id="user", session_id=trace.session_id
        )

    first = asyncio.run(read())
    assert first is not None and first.state["report"]["summary"] == report.summary
    assert first.events
    seen_prior = []

    class HistoryModel(ScriptedModel):
        async def generate_content_async(self, llm_request, stream=False):
            seen_prior.append("First question" in llm_request.model_dump_json())
            async for item in super().generate_content_async(llm_request, stream):
                yield item

    def scripted(question, settings, session_id):
        return investigate(
            question, settings=settings, session_id=session_id, model=HistoryModel(seen=[])
        )

    monkeypatch.setattr(cli, "investigate", scripted)
    assert cli.main(["investigate", "Second question", "--session", trace.session_id]) == 0
    assert f"Session: {trace.session_id}" in capsys.readouterr().out
    second = asyncio.run(read())
    assert second is not None and len(second.events) > len(first.events)
    assert seen_prior and seen_prior[0]


def test_explicit_missing_session_is_created(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_ASSIST_SESSION_DB", str(tmp_path / "db.sqlite"))
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path / "memory"))
    _, trace = investigate("question", session_id="new-session", model=ScriptedModel(seen=[]))
    assert trace.session_id == "new-session"


def test_resumed_session_requires_new_report(monkeypatch, tmp_path):
    import json

    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    from ops_assist.memory import list_memories

    monkeypatch.setenv("OPS_ASSIST_SESSION_DB", str(tmp_path / "session.db"))

    class FinalModel(ScriptedModel):
        answer: str = ""

        async def generate_content_async(self, llm_request, stream=False):
            yield LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text=self.answer)])
            )

    def answer(summary):
        return json.dumps({"summary": summary, "status": "insufficient_data"})

    first, trace = investigate("first", model=FinalModel(answer=answer("first")))
    second, _ = investigate(
        "second", session_id=trace.session_id, model=FinalModel(answer=answer("second"))
    )
    assert first.summary == "first" and second.summary == "second"
    before = list_memories()
    with pytest.raises(ValueError, match="agent returned no report"):
        investigate("empty", session_id=trace.session_id, model=FinalModel(answer=""))
    assert list_memories() == before
