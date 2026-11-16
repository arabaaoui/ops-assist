import os
import sys
from pathlib import Path

import pytest

# Some tests import LiteLLM before ops_assist; keep collection offline too.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # lets tests import contract.py


@pytest.fixture
def incidents_dir() -> Path:
    return ROOT / "src" / "ops_assist" / "data" / "incidents"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    """Keep all tests independent of the user's environment and memory."""
    for key in list(os.environ):
        if key.startswith("OPS_ASSIST_") and key != "OPS_ASSIST_TEST_ASYNC_TICK":
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPS_ASSIST_MEMORY_DIR", str(tmp_path / "memory"))


@pytest.fixture(autouse=True)
def sandbox_async_wakeup(monkeypatch):
    """Keep sandbox event loops polling while worker threads and timers complete."""
    if os.environ.get("OPS_ASSIST_TEST_ASYNC_TICK") != "1":
        return
    import asyncio

    original = asyncio.run

    def run(coro, **kwargs):
        async def wrapped():
            loop = asyncio.get_running_loop()

            def tick():
                loop.call_soon(tick)

            loop.call_soon(tick)
            return await coro

        return original(wrapped(), **kwargs)

    monkeypatch.setattr(asyncio, "run", run)
