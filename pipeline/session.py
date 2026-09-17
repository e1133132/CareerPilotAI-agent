from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class RunSession:
    """API-facing view of one pipeline run (authoritative for frontend polling/SSE)."""

    run_id: str
    state: dict[str, Any]
    status: str
    resume_status: str
    apply_status: str
    report_text: str = ""
    latest_step_message: str = ""
    error: str | None = None
    trace: str | None = None

    def to_store_entry(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "resume_status": self.resume_status,
            "apply_status": self.apply_status,
            "state": self.state,
            "report_text": self.report_text,
            "latest_step_message": self.latest_step_message,
            "error": self.error,
            "trace": self.trace,
        }


class RunStore:
    """In-memory run registry (dev/prototype). Swap for Redis in multi-worker deployments."""

    def __init__(self) -> None:
        self._sessions: dict[str, RunSession] = {}
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue[None]]] = {}

    def create(
        self,
        *,
        run_id: str,
        state: dict[str, Any],
        plan_status: str,
        resume_status: str,
        apply_status: str,
        latest_step_message: str = "",
    ) -> RunSession:
        session = RunSession(
            run_id=run_id,
            state=state,
            status=plan_status,
            resume_status=resume_status,
            apply_status=apply_status,
            latest_step_message=latest_step_message,
        )
        with self._lock:
            self._sessions[run_id] = session
            self._notify_locked(run_id)
        return session

    def get(self, run_id: str) -> RunSession | None:
        with self._lock:
            return self._sessions.get(run_id)

    def get_entry(self, run_id: str) -> dict[str, Any] | None:
        session = self.get(run_id)
        return session.to_store_entry() if session else None

    def update(self, run_id: str, **kwargs: Any) -> None:
        with self._lock:
            session = self._sessions.get(run_id)
            if not session:
                return
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
            self._notify_locked(run_id)

    def replace(self, run_id: str, session: RunSession) -> None:
        with self._lock:
            self._sessions[run_id] = session
            self._notify_locked(run_id)

    def update_state(self, run_id: str, state: dict[str, Any]) -> None:
        with self._lock:
            session = self._sessions.get(run_id)
            if session:
                session.state = state
                self._notify_locked(run_id)

    def subscribe(self, run_id: str) -> queue.Queue[None]:
        """Register a waiter notified whenever this run_id changes."""
        q: queue.Queue[None] = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    def unsubscribe(self, run_id: str, q: queue.Queue[None]) -> None:
        with self._lock:
            waiters = self._subscribers.get(run_id)
            if not waiters:
                return
            try:
                waiters.remove(q)
            except ValueError:
                pass
            if not waiters:
                self._subscribers.pop(run_id, None)

    def _notify_locked(self, run_id: str) -> None:
        """Wake SSE subscribers. Caller must hold self._lock."""
        for q in self._subscribers.get(run_id, []):
            try:
                q.put_nowait(None)
            except queue.Full:
                pass


run_store = RunStore()
