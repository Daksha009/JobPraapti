"""Structured, context-local progress events; no log scraping or secret values."""

from contextvars import ContextVar
from contextlib import contextmanager

_sink = ContextVar("jobpilot_progress", default=None)


def emit(
    stage,
    message,
    *,
    platform=None,
    state="running",
    current=None,
    total=None,
    metrics=None,
):
    sink = _sink.get()
    if sink:
        sink(
            {
                "stage": stage,
                "platform": platform,
                "state": state,
                "message": message,
                "current": current,
                "total": total,
                "metrics": metrics or {},
            }
        )


@contextmanager
def reporting_to(sink):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)
