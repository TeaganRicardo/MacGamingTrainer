"""Xcode-Python worker that owns the Hades II LLDB objects.

This module is launched only by transport_client under /usr/bin/xcrun python3.
It keeps LLDB's Python ABI isolated from the bundled application backend and
exposes a small JSONL RPC surface over stdio.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from core.adapter import AdapterError
from core.process_time_warp import LLDBProcessTimeWarpDriver, ProcessTimeWarpController


WORKER_PROTOCOL_VERSION = 1


def _error_payload(error):
    if isinstance(error, AdapterError):
        return {
            "code": error.code,
            "presentation": error.presentation,
            "diagnostic": error.diagnostic,
            "arguments": list(error.arguments),
        }
    return {
        "code": "debugger_worker_internal",
        "presentation": "LLDB 调试后端发生内部错误。",
        "diagnostic": "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        ),
        "arguments": [],
    }


class Hades2LLDBWorker:
    def __init__(self, transport=None, time_warp_factory=None):
        if transport is None:
            from .transport import Hades2LuaTransport
            transport = Hades2LuaTransport()
        self.transport = transport
        self.time_warp = None
        self._time_warp_config = None
        self._time_warp_factory = time_warp_factory or self._default_time_warp_factory

    @staticmethod
    def _default_time_warp_factory(transport, helper_path, image_names):
        return ProcessTimeWarpController(
            LLDBProcessTimeWarpDriver(transport),
            Path(helper_path),
            list(image_names),
        )

    def state(self):
        return {
            "pid": self.transport.pid,
            "tainted": bool(self.transport.tainted),
            "lastDuration": float(getattr(self.transport, "last_duration", 0.0) or 0.0),
            "lastExpressionDuration": float(
                getattr(self.transport, "last_expression_duration", 0.0) or 0.0
            ),
            "lastAttachProfile": dict(
                getattr(self.transport, "last_attach_profile", {}) or {}
            ),
        }

    @staticmethod
    def _require_params(params):
        if not isinstance(params, dict):
            raise ValueError("worker params must be an object")
        return params

    def _configure_time_warp(self, params):
        params = self._require_params(params)
        helper_path = params.get("helperPath")
        image_names = params.get("imageNames")
        if not isinstance(helper_path, str) or not helper_path:
            raise ValueError("time_warp helperPath must be a non-empty string")
        if (
            not isinstance(image_names, list)
            or not image_names
            or any(not isinstance(name, str) or not name for name in image_names)
        ):
            raise ValueError("time_warp imageNames must be non-empty strings")
        config = (helper_path, tuple(image_names))
        if config != self._time_warp_config:
            self.time_warp = self._time_warp_factory(
                self.transport,
                helper_path,
                image_names,
            )
            self._time_warp_config = config
        return True

    def _require_time_warp(self):
        if self.time_warp is None:
            raise ValueError("time_warp is not configured")
        return self.time_warp

    def dispatch(self, method, params):
        params = self._require_params(params)
        if method == "hello":
            return {
                "protocolVersion": WORKER_PROTOCOL_VERSION,
                "pythonVersion": ".".join(str(part) for part in sys.version_info[:3]),
            }
        if method == "transport.alive":
            return bool(self.transport.alive())
        if method == "transport.attach":
            pid = params.get("pid")
            if type(pid) is not int or pid <= 0:
                raise ValueError("transport.attach requires a positive integer pid")
            self.transport.attach(pid)
            return True
        if method == "transport.detach":
            self.transport.detach()
            return True
        if method == "transport.close":
            self.transport.close()
            return True
        if method == "transport.set_tainted":
            value = params.get("value")
            if type(value) is not bool:
                raise ValueError("transport.set_tainted requires a boolean value")
            self.transport.tainted = value
            return True
        if method == "transport.execute":
            source = params.get("source")
            timeout = params.get("expressionTimeoutSeconds")
            if not isinstance(source, str):
                raise ValueError("transport.execute requires string source")
            if timeout is None:
                return self.transport.execute(source)
            return self.transport.execute(
                source,
                expression_timeout_seconds=timeout,
            )
        if method == "time_warp.configure":
            return self._configure_time_warp(params)
        if method == "time_warp.set_speed":
            return self._require_time_warp().set_speed(params.get("value"))
        if method == "time_warp.current_speed":
            return self._require_time_warp().current_speed()
        if method == "time_warp.reset":
            return self._require_time_warp().reset()
        raise ValueError(f"unsupported worker method: {method}")


def serve_requests(input_stream, output_stream, worker):
    for raw in input_stream:
        request_id = None
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError("worker request must be an object")
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("worker request id must be a non-empty string")
            if not isinstance(method, str) or not method:
                raise ValueError("worker method must be a non-empty string")
            result = worker.dispatch(method, params)
            response = {
                "id": request_id,
                "result": result,
                "state": worker.state(),
            }
        except Exception as error:
            response = {
                "id": request_id,
                "error": _error_payload(error),
                "state": worker.state(),
            }
        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()


def main():
    worker = Hades2LLDBWorker()
    try:
        serve_requests(sys.stdin, sys.stdout, worker)
    finally:
        try:
            worker.transport.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
