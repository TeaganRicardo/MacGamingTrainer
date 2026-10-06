"""Main-backend client for the Hades II Xcode-Python LLDB sidecar.

The application backend runs on bundled CPython. Only the game-owned debugger
sidecar runs under Xcode's Python so the LLDB extension ABI cannot constrain the
rest of the backend runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from core.adapter import AdapterError
from core.process_time_warp import ProcessTimeWarpError


_WORKER_PROTOCOL_VERSION = 1
_RISKY_METHODS = frozenset({
    "transport.execute",
    "time_warp.set_speed",
    "time_warp.reset",
})


class _LLDBWorkerClient:
    def __init__(self):
        self._process = None
        self._next_id = 1
        self._terminal_error = None

    @property
    def started(self):
        return self._process is not None

    @property
    def terminal(self):
        return self._terminal_error is not None

    def _backend_root(self):
        return Path(__file__).resolve().parents[2]

    def _start(self):
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._process is not None and self._process.poll() is None:
            return

        backend_root = self._backend_root()
        environment = dict(os.environ)
        existing_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = (
            str(backend_root)
            if not existing_path
            else str(backend_root) + os.pathsep + existing_path
        )
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            self._process = subprocess.Popen(
                [
                    "/usr/bin/xcrun",
                    "python3",
                    "-u",
                    "-m",
                    "games.hades2.lldb_worker",
                ],
                cwd=str(backend_root),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
            response = self._exchange("hello", {}, allow_start=False)
        except (OSError, AdapterError) as error:
            self._terminate()
            if isinstance(error, AdapterError):
                raise
            raise AdapterError(
                "debugger_unavailable",
                "hades2.error.debuggerUnavailable",
                diagnostic=str(error),
            ) from error

        result = response.get("result")
        if (
            not isinstance(result, dict)
            or result.get("protocolVersion") != _WORKER_PROTOCOL_VERSION
        ):
            self._terminate()
            raise AdapterError(
                "debugger_protocol",
                "hades2.error.debuggerProtocol",
                diagnostic=f"worker hello={result!r}",
            )

    def _communication_failure(self, method, detail):
        self._terminate()
        if method in _RISKY_METHODS:
            error = AdapterError(
                "outcome_unknown",
                "hades2.error.outcomeUnknownGeneric",
                diagnostic=detail,
            )
        else:
            error = AdapterError(
                "restart_required",
                "hades2.error.debuggerExited",
                diagnostic=detail,
            )
        self._terminal_error = error
        raise error

    def _exchange(self, method, params, *, allow_start=True):
        if allow_start:
            self._start()
        process = self._process
        if process is None or process.poll() is not None:
            return self._communication_failure(method, "LLDB sidecar is not running.")
        if process.stdin is None or process.stdout is None:
            return self._communication_failure(method, "LLDB sidecar stdio is unavailable.")

        request_id = str(self._next_id)
        self._next_id += 1
        request = {
            "id": request_id,
            "method": method,
            "params": dict(params or {}),
        }
        try:
            process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            process.stdin.flush()
            raw = process.stdout.readline()
        except (KeyboardInterrupt, SystemExit):
            # Backend shutdown must not leave the Xcode-Python debugger child
            # attached after the bundled worker exits. Preserve the terminating
            # exception after releasing sidecar ownership.
            self._terminate()
            raise
        except (BrokenPipeError, OSError) as error:
            return self._communication_failure(method, str(error))
        if not raw:
            return self._communication_failure(
                method,
                f"LLDB sidecar exited with status {process.poll()!r}.",
            )
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as error:
            return self._communication_failure(
                method,
                f"LLDB sidecar returned invalid JSON: {error}",
            )
        if not isinstance(response, dict) or response.get("id") != request_id:
            return self._communication_failure(
                method,
                f"LLDB sidecar reply identity mismatch: {response!r}",
            )
        return response

    def call(self, method, params=None):
        if self._terminal_error is not None:
            raise self._terminal_error
        response = self._exchange(method, params or {})
        error = response.get("error")
        if error is not None:
            if not isinstance(error, dict):
                self._communication_failure(method, f"Malformed worker error: {error!r}")
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
                self._terminal_error = raised
            raise raised
        return response.get("result"), response.get("state")

    def mark_tainted(self, value):
        if self._terminal_error is not None:
            return
        if not self.started:
            return
        try:
            self.call("transport.set_tainted", {"value": bool(value)})
        except AdapterError:
            # The caller is already handling an outcome-unknown path. Do not
            # mask that primary failure with a secondary sidecar notification.
            pass

    def _terminate(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

    def close(self):
        process = self._process
        if process is not None and process.poll() is None:
            try:
                self.call("transport.close")
            except AdapterError:
                pass
        self._terminate()


class Hades2LuaTransport:
    """Resident-session transport facade backed by one LLDB sidecar process."""

    def __init__(self):
        self._worker = _LLDBWorkerClient()
        self.pid = None
        self.last_duration = 0.0
        self.last_expression_duration = 0.0
        self.last_attach_profile = {}
        self._tainted = False

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
        result, state = self._worker.call(method, params)
        self._adopt_state(state)
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
        self._worker = transport._worker
        self._helper_path = str(Path(helper_path))
        self._image_names = list(image_names)
        self._configured = False

    def _configure(self):
        if self._configured:
            return
        _, state = self._worker.call(
            "time_warp.configure",
            {
                "helperPath": self._helper_path,
                "imageNames": self._image_names,
            },
        )
        self._transport._adopt_state(state)
        self._configured = True

    def _call(self, method, params=None):
        self._configure()
        result, state = self._worker.call(method, params or {})
        self._transport._adopt_state(state)
        return result

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
