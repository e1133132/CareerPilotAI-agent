from __future__ import annotations

import contextvars

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    return _request_id_var.set(request_id)


def get_request_id() -> str | None:
    return _request_id_var.get()


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id_var.reset(token)


def set_run_id(run_id: str | None) -> contextvars.Token[str | None]:
    return _run_id_var.set(run_id)


def get_run_id() -> str | None:
    return _run_id_var.get()


def reset_run_id(token: contextvars.Token[str | None]) -> None:
    _run_id_var.reset(token)
