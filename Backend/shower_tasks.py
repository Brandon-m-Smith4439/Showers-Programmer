#!/usr/bin/env python3
"""Reusable cancellable background task runner for the Tk desktop application."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


class TaskCancelled(RuntimeError):
    pass


@dataclass
class TaskSnapshot:
    task_id: str
    name: str
    message: str
    current: int = 0
    total: int = 0
    cancellable: bool = True
    started_at: float = field(default_factory=time.monotonic)


class TaskContext:
    def __init__(
        self,
        snapshot: TaskSnapshot,
        cancel_event: threading.Event,
        progress_callback: Callable[[TaskSnapshot], None],
    ) -> None:
        self.snapshot = snapshot
        self._cancel_event = cancel_event
        self._progress_callback = progress_callback

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled(f"{self.snapshot.name} was cancelled.")

    def progress(self, current: int, total: int, message: str) -> None:
        self.check_cancelled()
        self.snapshot.current = max(0, int(current))
        self.snapshot.total = max(0, int(total))
        self.snapshot.message = str(message)
        self._progress_callback(self.snapshot)

    def stage(self, message: str) -> None:
        self.progress(self.snapshot.current, self.snapshot.total, message)


class BackgroundTaskManager:
    """Own one user-visible long-running task at a time.

    The application already intentionally serializes production-affecting actions.
    Centralizing that rule here avoids each workflow inventing its own threading,
    cancellation, and progress lifecycle.
    """

    def __init__(
        self,
        event_callback: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._event_callback = event_callback
        self._lock = threading.RLock()
        self._active: TaskSnapshot | None = None
        self._cancel_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        # Retain terminal outcomes until the Tk queue acknowledges them. This
        # gives the GUI heartbeat a deterministic recovery path if the cross-
        # thread callback is interrupted while a window is being closed.
        self._terminal_events: dict[str, tuple[str, dict[str, Any]]] = {}

    @property
    def active(self) -> TaskSnapshot | None:
        with self._lock:
            return self._active

    def start(
        self,
        name: str,
        worker: Callable[[TaskContext], Any],
        *,
        message: str,
        total: int = 0,
        cancellable: bool = True,
    ) -> TaskSnapshot:
        with self._lock:
            if self._active is not None:
                raise RuntimeError(f"Background task already running: {self._active.name}")
            snapshot = TaskSnapshot(
                task_id=uuid.uuid4().hex,
                name=str(name),
                message=str(message),
                total=max(0, int(total)),
                cancellable=bool(cancellable),
            )
            cancel_event = threading.Event()
            self._active = snapshot
            self._cancel_event = cancel_event

        def emit_progress(updated: TaskSnapshot) -> None:
            self._event_callback(
                "task_progress",
                {
                    "task_id": updated.task_id,
                    "name": updated.name,
                    "message": updated.message,
                    "current": updated.current,
                    "total": updated.total,
                    "cancellable": updated.cancellable,
                },
            )

        def run() -> None:
            context = TaskContext(snapshot, cancel_event, emit_progress)
            terminal_kind = "task_done"
            terminal_payload: dict[str, Any]
            try:
                emit_progress(snapshot)
                result = worker(context)
                context.check_cancelled()
                terminal_payload = {
                    "task_id": snapshot.task_id,
                    "name": snapshot.name,
                    "result": result,
                    "elapsed_ms": (time.monotonic() - snapshot.started_at) * 1000.0,
                }
            except TaskCancelled as exc:
                terminal_kind = "task_cancelled"
                terminal_payload = {
                    "task_id": snapshot.task_id,
                    "name": snapshot.name,
                    "error": exc,
                    "elapsed_ms": (time.monotonic() - snapshot.started_at) * 1000.0,
                }
            except BaseException as exc:
                terminal_kind = "task_error"
                terminal_payload = {
                    "task_id": snapshot.task_id,
                    "name": snapshot.name,
                    "error": exc,
                    "traceback": traceback.format_exc(),
                    "elapsed_ms": (time.monotonic() - snapshot.started_at) * 1000.0,
                }
            finally:
                with self._lock:
                    if self._active is snapshot:
                        self._active = None
                        self._cancel_event = None
                        self._thread = None
                    self._terminal_events[snapshot.task_id] = (terminal_kind, terminal_payload)
                    while len(self._terminal_events) > 32:
                        self._terminal_events.pop(next(iter(self._terminal_events)))

            # A terminal callback may immediately start the next workflow stage.
            # Release this task first so that chained managed tasks are accepted.
            try:
                self._event_callback(terminal_kind, terminal_payload)
            except Exception:
                # The retained outcome is picked up by the GUI heartbeat. Never
                # strand the interface because an event handoff failed once.
                return

        try:
            thread = threading.Thread(target=run, name=f"shower-task-{name.casefold().replace(' ', '-')}", daemon=True)
            with self._lock:
                self._thread = thread
            thread.start()
        except Exception:
            with self._lock:
                if self._active is snapshot:
                    self._active = None
                    self._cancel_event = None
                    self._thread = None
            raise
        return snapshot

    def cancel(self) -> bool:
        with self._lock:
            if self._active is None or self._cancel_event is None or not self._active.cancellable:
                return False
            self._cancel_event.set()
            return True

    def terminal_event(self, task_id: str) -> tuple[str, dict[str, Any]] | None:
        """Return a retained terminal outcome without consuming it."""
        with self._lock:
            event = self._terminal_events.get(str(task_id))
            if event is None:
                return None
            kind, payload = event
            return kind, dict(payload)

    def acknowledge_terminal(self, task_id: str) -> None:
        """Forget a terminal outcome after Tk consumes the queue event."""
        with self._lock:
            self._terminal_events.pop(str(task_id), None)
