"""Opt-in, body-free phase records through the existing logging channel.

No files, retention, sessions or export policy are owned here. Durations are
local monotonic intervals; nested intervals must not be added together.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import logging
import os
import time

_current = ContextVar("operation_profile", default=None)
_FIELDS = frozenset({"method", "request_bytes", "reply_bytes", "response_kind", "count", "outcome"})


def enabled():
    return os.environ.get("MGT_PROFILE_OPERATIONS") == "1"


def correlation():
    return _current.get()


@contextmanager
def operation(request_id, command):
    # Correlation is transport metadata, never params/state/error text.
    if (not enabled() or not isinstance(request_id, str) or not 0 < len(request_id) <= 128
            or not isinstance(command, str) or len(command) > 128):
        yield
        return
    token = _current.set({"request_id": request_id, "command": command})
    try:
        yield
    finally:
        _current.reset(token)


def record(phase, seconds, **fields):
    identity = _current.get()
    if identity is None:
        return
    value = {"schema": 1, "component": "backend", **identity,
             "phase": phase, "seconds": seconds}
    value.update({key: value for key, value in fields.items() if key in _FIELDS})
    logging.info("OperationProfile %s", json.dumps(value, ensure_ascii=True, allow_nan=False))


@contextmanager
def phase(name, **fields):
    if _current.get() is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        record(name, time.perf_counter() - started, **fields)


def profiled(name):
    def decorate(method):
        @wraps(method)
        def measured(*args, **kwargs):
            with phase(name):
                return method(*args, **kwargs)
        return measured
    return decorate
