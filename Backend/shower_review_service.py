#!/usr/bin/env python3
"""Bounded asynchronous preparation for order-review contexts."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Hashable


ReviewCallback = Callable[[Any | None, BaseException | None], None]


class ReviewContextPrefetcher:
    """Deduplicate review loads and keep expensive preparation off Tk's thread."""

    def __init__(self, *, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix="shower-review",
        )
        self._lock = threading.RLock()
        self._generation = 0
        self._pending: dict[Hashable, tuple[Future[Any], list[ReviewCallback], int]] = {}

    def request(
        self,
        key: Hashable,
        loader: Callable[[], Any],
        callback: ReviewCallback | None = None,
    ) -> bool:
        """Schedule one load; duplicate callers share the same future."""
        with self._lock:
            pending = self._pending.get(key)
            if pending is not None:
                if callback is not None:
                    pending[1].append(callback)
                return False
            generation = self._generation
            callbacks = [callback] if callback is not None else []
            future = self._executor.submit(loader)
            self._pending[key] = (future, callbacks, generation)

        def complete(done: Future[Any]) -> None:
            try:
                value = done.result()
                error: BaseException | None = None
            except BaseException as exc:
                value = None
                error = exc
            with self._lock:
                current = self._pending.pop(key, None)
                active = current is not None and current[2] == self._generation
                notify = list(current[1]) if current is not None and active else []
            for handler in notify:
                handler(value, error)

        future.add_done_callback(complete)
        return True

    def cancel_pending(self) -> None:
        with self._lock:
            self._generation += 1
            pending = list(self._pending.values())
            self._pending.clear()
        for future, _callbacks, _generation in pending:
            future.cancel()

    def shutdown(self) -> None:
        self.cancel_pending()
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

