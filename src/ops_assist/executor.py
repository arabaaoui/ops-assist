"""A small daemon worker pool for potentially blocking tool calls."""

from concurrent.futures import Future
from queue import Full, Queue
from threading import Lock, Thread
from typing import Any

from .observability import ObservationError


class ToolExecutor:
    """Bound workers and queued work; daemon workers do not prevent process exit."""

    def __init__(self, workers: int = 4, capacity: int = 4):
        """Create workers lazily and bound the waiting queue."""
        self._queue = Queue(maxsize=capacity)
        self._workers = workers
        self._started = False
        self._lock = Lock()

    def _run(self):
        while True:
            future, func, args = self._queue.get()
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(func(*args))
                    except BaseException as exc:
                        future.set_exception(exc)
            finally:
                self._queue.task_done()

    def submit(self, func, *args: Any) -> Future:
        """Queue work, refusing excess load rather than growing without bound."""
        with self._lock:
            if not self._started:
                for _ in range(self._workers):
                    Thread(target=self._run, daemon=True, name="ops-assist-tool").start()
                self._started = True
        future = Future()
        try:
            self._queue.put_nowait((future, func, args))
        except Full as exc:
            raise ObservationError("tool worker pool is full") from exc
        return future


executor = ToolExecutor()
