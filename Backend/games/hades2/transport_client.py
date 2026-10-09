"""Main-backend client for the Hades II Xcode-Python LLDB sidecar.

The application backend runs on bundled CPython. Only the game-owned debugger
sidecar runs under Xcode's Python so the LLDB extension ABI cannot constrain the
rest of the backend runtime. Core owns generic child-process/JSONL mechanics;
all LLDB methods, failure meaning and runtime state remain Hades-owned here.
"""
from __future__ import annotations

import os
from pathlib import Path

from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient, SidecarStartError, SidecarTerminalError

from .config import (
    LLDB_SIDECAR_ATTACH_REPLY_TIMEOUT_SECONDS,
    LLDB_SIDECAR_REPLY_TIMEOUT_SECONDS,
)


_WORKER_PROTOCOL_VERSION = 1
_RISKY_METHODS = frozenset({
    "transport.execute",
    "time_warp.set_speed",
    "time_warp.reset",
})


class _LLDBWorkerClient:
    def __init__(self, sidecar=None, on_state=None):
        self._sidecar = sidecar or self._make_sidecar()
        self._on_state = on_state
        self._hello_complete = False
        self._terminal_error = None

    @staticmethod
    def _backend_root():
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _make_sidecar(cls):
        backend_root = cls._backend_root()
        environment = dict(os.environ)
        existing_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = (
            str(backend_root)
            if not existing_path
            else str(backend_root) + os.pathsep + existing_path
        )
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return JsonLineSidecarClient(
            [
                "/usr/bin/xcrun",
                "python3",
                "-u",
                "-m",
                "games.hades2.lldb_worker",
            ],
            cwd=backend_root,
            env=environment,
            reply_timeout_seconds=LLDB_SIDECAR_REPLY_TIMEOUT_SECONDS,
        )

    @property
    def started(self):
        # Preserve the Hades transport's established-session meaning: once the
        # worker handshake succeeded, a child that exits between requests may
        # be recreated safely by the next call. Terminal in-flight failures are
        # tracked separately and remain non-recoverable.
        return self._hello_complete

    @property
    def terminal(self):
        return self._terminal_error is not None or self._sidecar.terminal

    def _raise_sidecar_failure(self, error):
        if self._terminal_error is not None:
            raise self._terminal_error
        if isinstance(error, SidecarStartError):
            self._hello_complete = False
            raise AdapterError(
                "debugger_unavailable",
                "hades2.error.debuggerUnavailable",
                diagnostic=error.detail,
            ) from error
        if error.outcome_unknown:
            raised = AdapterError(
                "outcome_unknown",
                "hades2.error.outcomeUnknownGeneric",
                diagnostic=error.detail,
            )
        else:
            raised = AdapterError(
                "restart_required",
                "hades2.error.debuggerExited",
                diagnostic=error.detail,
            )
        self._terminal_error = raised
        raise raised from error

    def _request(self, method, params=None):
        # Game process attach may take significantly longer than a Lua/readout
        # exchange. Apply its Hades-owned budget only to that method.
        timeout_override = (
            {"reply_timeout_seconds": LLDB_SIDECAR_ATTACH_REPLY_TIMEOUT_SECONDS}
            if method == "transport.attach"
            else {}
        )
        try:
            return self._sidecar.request(
                method,
                params or {},
                outcome_unknown_on_loss=method in _RISKY_METHODS,
                allow_start=False,
                **timeout_override,
            )
        except (SidecarStartError, SidecarTerminalError) as error:
            self._raise_sidecar_failure(error)

    def _start(self):
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._hello_complete and self._sidecar.started:
            return
        try:
            response = self._sidecar.request("hello", {})
        except (SidecarStartError, SidecarTerminalError) as error:
            self._raise_sidecar_failure(error)

        result = response.get("result")
        if (
            not isinstance(result, dict)
            or result.get("protocolVersion") != _WORKER_PROTOCOL_VERSION
        ):
            self._sidecar.close()
            self._hello_complete = False
            raise AdapterError(
                "debugger_protocol",
                "hades2.error.debuggerProtocol",
                diagnostic=f"worker hello={result!r}",
            )
        self._hello_complete = True

    def _protocol_failure(self, method, detail):
        try:
            self._sidecar.invalidate(
                detail,
                outcome_unknown=method in _RISKY_METHODS,
            )
        except SidecarTerminalError as error:
            self._raise_sidecar_failure(error)

    def call(self, method, params=None):
        if self._terminal_error is not None:
            raise self._terminal_error
        self._start()
        response = self._request(method, params)
        error = response.get("error")
        if error is not None and not isinstance(error, dict):
            self._protocol_failure(method, f"Malformed worker error: {error!r}")
        # A method can fail after changing the attachment. Adopt the worker's
        # authoritative observation before propagating either result or error.
        if self._on_state is not None:
            self._on_state(response.get("state"))
        if error is not None:
            raised = AdapterError(
                str(error.get("code") or "debugger_error"),
                str(error.get("presentation") or "hades2.error.debuggerCallFailed"),
                diagnostic=(
                    str(error["diagnostic"])
                    if error.get("diagnostic") is not None
                    else None
                ),
                arguments=(
                    error.get("arguments")
                    if isinstance(error.get("arguments"), list)
                    else ()
                ),
            )
            if raised.code == "outcome_unknown":
                # The worker method's semantic uncertainty is Hades-owned.
                # Stop this wrapper from issuing further calls; the generic
                # sidecar only terminalizes itself for IPC trust failures.
                self._terminal_error = raised
            raise raised
        return response.get("result"), response.get("state")

    def mark_tainted(self, value):
        if self._terminal_error is not None or not self.started:
            return
        try:
            self.call("transport.set_tainted", {"value": bool(value)})
        except AdapterError:
            # The caller is already handling an outcome-unknown path. Do not
            # mask that primary failure with a secondary sidecar notification.
            pass

    def close(self):
        # Do not respawn a child merely to close an already-dead sidecar.
        if self._sidecar.started and not self.terminal:
            try:
                self.call("transport.close")
            except AdapterError:
                pass
        self._sidecar.close()
        self._hello_complete = False


class Hades2LuaTransport:
    """Resident-session transport facade backed by one LLDB sidecar process."""

    def __init__(self):
        self.pid = None
        self.last_duration = 0.0
        self.last_expression_duration = 0.0
        self.last_attach_profile = {}
        self._tainted = False
        self._worker = _LLDBWorkerClient(on_state=self._adopt_state)

    def _adopt_state(self, state):
        if not isinstance(state, dict):
            return
        pid = state.get("pid")
        self.pid = pid if type(pid) is int and pid > 0 else None
        self._tainted = state.get("tainted") is True
        duration = state.get("lastDuration")
        self.last_duration = float(duration) if type(duration) in (int, float) else 0.0
        expression = state.get("lastExpressionDuration")
        self.last_expression_duration = (
            float(expression) if type(expression) in (int, float) else 0.0
        )
        profile = state.get("lastAttachProfile")
        self.last_attach_profile = dict(profile) if isinstance(profile, dict) else {}

    def _call(self, method, params=None):
        result, _ = self._worker.call(method, params)
        return result

    @property
    def tainted(self):
        return self._tainted or self._worker.terminal

    @tainted.setter
    def tainted(self, value):
        self._tainted = bool(value)
        self._worker.mark_tainted(self._tainted)

    def alive(self):
        if not self._worker.started or self._worker.terminal:
            return False
        try:
            return bool(self._call("transport.alive"))
        except AdapterError:
            return False

    def attach(self, pid):
        self._call("transport.attach", {"pid": pid})

    def detach(self):
        if not self._worker.started:
            self.pid = None
            self._tainted = False
            return
        self._call("transport.detach")

    def execute(self, source, *, expression_timeout_seconds=2.0):
        return self._call(
            "transport.execute",
            {
                "source": source,
                "expressionTimeoutSeconds": expression_timeout_seconds,
            },
        )

    def create_time_warp_controller(self, helper_path, image_names):
        return RemoteProcessTimeWarpController(
            self,
            helper_path=helper_path,
            image_names=image_names,
        )

    def close(self):
        self._worker.close()
        self.pid = None


class RemoteProcessTimeWarpController:
    """Process Time Warp facade executed inside the same LLDB sidecar."""

    def __init__(self, transport, *, helper_path, image_names):
        self._transport = transport
        self._helper_path = str(Path(helper_path))
        self._image_names = list(image_names)

    def _configure(self):
        # Configuration belongs to a worker process. Reassert it through the
        # worker's idempotent owner so an idle child restart cannot lose it.
        self._transport._call(
            "time_warp.configure",
            {
                "helperPath": self._helper_path,
                "imageNames": self._image_names,
            },
        )

    def _call(self, method, params=None):
        self._configure()
        return self._transport._call(method, params or {})

    def set_speed(self, value):
        return self._call("time_warp.set_speed", {"value": value})

    def current_speed(self):
        if not self._transport.alive():
            return 1.0
        return self._call("time_warp.current_speed")

    def reset(self):
        if not self._transport.alive():
            return 1.0
        return self._call("time_warp.reset")


LuaTransport = Hades2LuaTransport
