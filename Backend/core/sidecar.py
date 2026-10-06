"""Generic optional-sidecar lifecycle and bounded JSONL request/reply transport."""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from pathlib import Path


DEFAULT_MAX_LINE_BYTES = 8 * 1024 * 1024


class SidecarTerminalError(RuntimeError):
    """Terminal loss of a sidecar request/reply trust boundary."""

    def __init__(self, detail, *, outcome_unknown=False):
        super().__init__(str(detail))
        self.detail = str(detail)
        self.outcome_unknown = bool(outcome_unknown)


class SidecarStartError(SidecarTerminalError):
    """The sidecar process could not be created."""


class JsonLineSidecarClient:
    """Own one child process and a sequential bounded JSONL request/reply seam.

    Method names and payload semantics remain caller-owned. Core owns only
    process lifetime, request identity, bounded framing, reply timeout and the
    terminal distinction between known failure and outcome-unknown loss.
    """

    def __init__(
        self,
        command,
        *,
        reply_timeout_seconds,
        cwd=None,
        env=None,
        max_line_bytes=DEFAULT_MAX_LINE_BYTES,
        process_factory=subprocess.Popen,
    ):
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("sidecar command must contain non-empty strings")
        if reply_timeout_seconds <= 0:
            raise ValueError("sidecar reply timeout must be positive")
        if type(max_line_bytes) is not int or max_line_bytes <= 0:
            raise ValueError("sidecar max line bytes must be a positive integer")
        self.command = tuple(command)
        self.cwd = str(Path(cwd)) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.reply_timeout_seconds = float(reply_timeout_seconds)
        self.max_line_bytes = max_line_bytes
        self._process_factory = process_factory
        self._process = None
        self._next_id = 1
        self._terminal_error = None

    @property
    def started(self):
        return self._process is not None and self._process.poll() is None

    @property
    def terminal(self):
        return self._terminal_error is not None

    def start(self):
        if self._terminal_error is not None:
            raise self._terminal_error
        if self.started:
            return
        if self._process is not None:
            # The previous child exited between requests, so no request outcome
            # is in doubt. Reap it and allow a fresh process to be started.
            self._terminate_process()
        try:
            self._process = self._process_factory(
                list(self.command),
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                bufsize=0,
            )
        except OSError as error:
            # No request crossed the seam, so there is no outcome to distrust.
            # Let the game/runtime decide whether a later explicit action retries.
            self._terminate_process()
            raise SidecarStartError(str(error), outcome_unknown=False) from error

    def _terminate_process(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (AttributeError, OSError):
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
        try:
            if process.stdout is not None:
                process.stdout.close()
        except (AttributeError, OSError):
            pass

    def _fail_terminal(self, detail, *, outcome_unknown):
        error = SidecarTerminalError(detail, outcome_unknown=outcome_unknown)
        self._terminal_error = error
        self._terminate_process()
        raise error

    def invalidate(self, detail, *, outcome_unknown=False):
        self._fail_terminal(detail, outcome_unknown=outcome_unknown)

    def mark_outcome_unknown(self, detail):
        if self._terminal_error is None:
            self._terminal_error = SidecarTerminalError(detail, outcome_unknown=True)
        self._terminate_process()

    def _readline(self, stream):
        try:
            fileno = stream.fileno()
        except (AttributeError, OSError, ValueError):
            return stream.readline(self.max_line_bytes + 1)

        deadline = time.monotonic() + self.reply_timeout_seconds
        chunks = []
        total = 0
        selector = selectors.DefaultSelector()
        try:
            selector.register(stream, selectors.EVENT_READ)
            while total <= self.max_line_bytes:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError(
                        f"sidecar reply timed out after {self.reply_timeout_seconds:g}s"
                    )
                chunk = os.read(
                    fileno,
                    min(65536, self.max_line_bytes + 1 - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if b"\n" in chunk:
                    break
        finally:
            selector.close()
        return b"".join(chunks)

    def request(self, method, params=None, *, outcome_unknown_on_loss=False):
        if self._terminal_error is not None:
            raise self._terminal_error
        if not isinstance(method, str) or not method:
            raise ValueError("sidecar method must be a non-empty string")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError("sidecar params must be an object")
        self.start()
        process = self._process
        if process is None or process.poll() is not None:
            status = None if process is None else process.poll()
            self._fail_terminal(
                f"sidecar is not running (status {status!r}).",
                outcome_unknown=outcome_unknown_on_loss,
            )
        if process.stdin is None or process.stdout is None:
            self._fail_terminal(
                "sidecar stdio is unavailable.",
                outcome_unknown=outcome_unknown_on_loss,
            )

        request_id = str(self._next_id)
        self._next_id += 1
        encoded = (
            json.dumps(
                {"id": request_id, "method": method, "params": params},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(encoded) > self.max_line_bytes:
            raise ValueError("sidecar request exceeded the configured line limit")

        try:
            process.stdin.write(encoded)
            process.stdin.flush()
            raw = self._readline(process.stdout)
        except (KeyboardInterrupt, SystemExit):
            self._terminate_process()
            raise
        except TimeoutError as error:
            self._fail_terminal(str(error), outcome_unknown=outcome_unknown_on_loss)
        except (BrokenPipeError, OSError) as error:
            self._fail_terminal(str(error), outcome_unknown=outcome_unknown_on_loss)

        if isinstance(raw, str):
            raw_bytes = raw.encode("utf-8")
            raw_text = raw
        else:
            raw_bytes = raw
            try:
                raw_text = raw.decode("utf-8")
            except UnicodeDecodeError as error:
                self._fail_terminal(
                    f"sidecar returned invalid UTF-8: {error}",
                    outcome_unknown=outcome_unknown_on_loss,
                )
        if not raw_bytes:
            self._fail_terminal(
                f"sidecar exited with status {process.poll()!r}.",
                outcome_unknown=outcome_unknown_on_loss,
            )
        if len(raw_bytes) > self.max_line_bytes:
            self._fail_terminal(
                "sidecar reply exceeded the configured line limit.",
                outcome_unknown=outcome_unknown_on_loss,
            )
        try:
            response = json.loads(
                raw_text,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON value: " + value)
                ),
            )
        except (json.JSONDecodeError, ValueError) as error:
            self._fail_terminal(
                f"sidecar returned invalid JSON: {error}",
                outcome_unknown=outcome_unknown_on_loss,
            )
        if not isinstance(response, dict) or response.get("id") != request_id:
            self._fail_terminal(
                f"sidecar reply identity mismatch: {response!r}",
                outcome_unknown=outcome_unknown_on_loss,
            )
        return response

    def close(self):
        self._terminate_process()


def _line_size(raw):
    return len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)


def _line_ended(raw):
    return raw.endswith("\n") if isinstance(raw, str) else raw.endswith(b"\n")


def _write_json_line(output_stream, payload, max_line_bytes):
    encoded = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        + b"\n"
    )
    if len(encoded) > max_line_bytes:
        raise ValueError("sidecar reply exceeded the configured line limit")
    try:
        output_stream.write(encoded)
    except TypeError:
        output_stream.write(encoded.decode("utf-8"))
    output_stream.flush()


def serve_jsonl_requests(
    input_stream,
    output_stream,
    dispatch,
    *,
    error_payload,
    state=lambda: {},
    max_line_bytes=DEFAULT_MAX_LINE_BYTES,
):
    """Serve sequential bounded JSONL requests without owning method semantics."""
    if type(max_line_bytes) is not int or max_line_bytes <= 0:
        raise ValueError("sidecar max line bytes must be a positive integer")
    stream = getattr(input_stream, "buffer", input_stream)
    while True:
        raw = stream.readline(max_line_bytes + 1)
        if not raw:
            break
        request_id = None
        try:
            if _line_size(raw) > max_line_bytes:
                while raw and not _line_ended(raw):
                    raw = stream.readline(max_line_bytes + 1)
                raise ValueError("sidecar request exceeded the configured line limit")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            request = json.loads(
                raw,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError("non-finite JSON value: " + value)
                ),
            )
            if not isinstance(request, dict):
                raise ValueError("sidecar request must be an object")
            request_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("sidecar request id must be a non-empty string")
            if not isinstance(method, str) or not method:
                raise ValueError("sidecar method must be a non-empty string")
            if not isinstance(params, dict):
                raise ValueError("sidecar params must be an object")
            response = {
                "id": request_id,
                "result": dispatch(method, params),
                "state": state(),
            }
        except Exception as error:
            response = {
                "id": request_id,
                "error": error_payload(error),
                "state": state(),
            }
        # A post-dispatch serialization/size failure must terminate the worker
        # rather than invent an ordinary error reply: the caller alone knows
        # whether a lost mutation acknowledgement means outcome_unknown.
        _write_json_line(output_stream, response, max_line_bytes)
