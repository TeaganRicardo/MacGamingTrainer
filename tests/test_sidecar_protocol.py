import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.sidecar import (
    JsonLineSidecarClient,
    SidecarStartError,
    SidecarTerminalError,
    serve_jsonl_requests,
)


class FakeProcess:
    def __init__(self, replies=b""):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(replies)
        self.terminated = False
        self.killed = False

    def poll(self):
        return -15 if self.terminated or self.killed else None

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.poll()


def factory_for(process):
    def create(*args, **kwargs):
        return process
    return create


process = FakeProcess(b'{"id":"1","result":{"ok":true}}\n')
client = JsonLineSidecarClient(["fake"], reply_timeout_seconds=1.0, process_factory=factory_for(process))
reply = client.request("ping", {"value": 7})
assert reply["result"] == {"ok": True}
request = json.loads(process.stdin.getvalue())
assert request == {"id": "1", "method": "ping", "params": {"value": 7}}
assert client.started

# A child that exits between requests has no in-flight result to distrust. Reap
# it and start a fresh child instead of turning a known crash into a terminal
# request outcome.
restart_first = FakeProcess(b'{"id":"1","result":"first"}\n')
restart_second = FakeProcess(b'{"id":"2","result":"second"}\n')
restart_processes = [restart_first, restart_second]


def restart_factory(*args, **kwargs):
    return restart_processes.pop(0)


restartable = JsonLineSidecarClient(["fake"], reply_timeout_seconds=1.0, process_factory=restart_factory)
assert restartable.request("observe")["result"] == "first"
restart_first.terminated = True
assert restartable.request("observe")["result"] == "second"
assert not restart_processes

mismatch_process = FakeProcess(b'{"id":"wrong","result":true}\n')
mismatch = JsonLineSidecarClient(["fake"], reply_timeout_seconds=1.0, process_factory=factory_for(mismatch_process))
try:
    mismatch.request("ping")
except SidecarTerminalError as error:
    assert error.outcome_unknown is False
    assert "identity mismatch" in str(error)
else:
    raise AssertionError("reply identity mismatch was accepted")
assert mismatch.terminal
assert mismatch_process.terminated or mismatch_process.killed

lost_process = FakeProcess(b"")
lost = JsonLineSidecarClient(["fake"], reply_timeout_seconds=1.0, process_factory=factory_for(lost_process))
try:
    lost.request("mutate", outcome_unknown_on_loss=True)
except SidecarTerminalError as error:
    assert error.outcome_unknown is True
else:
    raise AssertionError("lost mutating reply was not outcome-unknown")
try:
    lost.request("observe")
except SidecarTerminalError as error:
    assert error.outcome_unknown is True, "terminal outcome-unknown trust was not sticky"
else:
    raise AssertionError("terminal sidecar was reused")

oversized_process = FakeProcess(b"x" * 65 + b"\n")
oversized = JsonLineSidecarClient(
    ["fake"],
    reply_timeout_seconds=1.0,
    process_factory=factory_for(oversized_process),
    max_line_bytes=64,
)
try:
    oversized.request("ping")
except SidecarTerminalError as error:
    assert "exceeded" in str(error)
else:
    raise AssertionError("oversized reply was accepted")


class InterruptingOutput:
    def readline(self, size=-1):
        raise KeyboardInterrupt()


interrupted_process = FakeProcess()
interrupted_process.stdout = InterruptingOutput()
interrupted = JsonLineSidecarClient(["fake"], reply_timeout_seconds=1.0, process_factory=factory_for(interrupted_process))
try:
    interrupted.request("observe")
except KeyboardInterrupt:
    pass
else:
    raise AssertionError("sidecar interruption was swallowed")
assert interrupted_process.terminated or interrupted_process.killed
assert not interrupted.started


class PipeProcess(FakeProcess):
    def __init__(self):
        super().__init__()
        read_fd, self.write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb", buffering=0)

    def terminate(self):
        super().terminate()
        try:
            os.close(self.write_fd)
        except OSError:
            pass

    def kill(self):
        super().kill()
        try:
            os.close(self.write_fd)
        except OSError:
            pass


timeout_process = PipeProcess()
timed = JsonLineSidecarClient(
    ["fake"],
    process_factory=factory_for(timeout_process),
    reply_timeout_seconds=0.01,
)
try:
    timed.request("observe")
except SidecarTerminalError as error:
    assert error.outcome_unknown is False
    assert "timed out" in str(error)
else:
    raise AssertionError("sidecar reply timeout was not enforced")

partial_process = PipeProcess()
os.write(partial_process.write_fd, b'{"id":"1"')
partial = JsonLineSidecarClient(
    ["fake"],
    process_factory=factory_for(partial_process),
    reply_timeout_seconds=0.01,
)
try:
    partial.request("observe")
except SidecarTerminalError as error:
    assert error.outcome_unknown is False
    assert "timed out" in str(error)
else:
    raise AssertionError("partial sidecar reply escaped the total frame timeout")


def unavailable_factory(*args, **kwargs):
    raise OSError("runtime missing")


recovered_start = FakeProcess(b'{"id":"1","result":"ok"}\n')
start_attempts = 0


def unavailable_then_ready(*args, **kwargs):
    global start_attempts
    start_attempts += 1
    if start_attempts == 1:
        raise OSError("runtime missing")
    return recovered_start


unavailable = JsonLineSidecarClient(
    ["missing"],
    reply_timeout_seconds=1.0,
    process_factory=unavailable_then_ready,
)
try:
    unavailable.request("hello")
except SidecarStartError as error:
    assert error.outcome_unknown is False
    assert "runtime missing" in str(error)
else:
    raise AssertionError("sidecar start failure lost its identity")
assert not unavailable.terminal, "pre-request start failure incorrectly terminated trust"
assert unavailable.request("hello")["result"] == "ok"
assert start_attempts == 2

seen = []


def dispatch(method, params):
    seen.append((method, params))
    return {"method": method}


def error_payload(error):
    return {"code": "invalid", "detail": str(error)}


input_stream = io.StringIO(
    json.dumps({"id": "a", "method": "ping", "params": {"n": 1}}) + "\n"
    + ("x" * 300) + "\n"
)
output_stream = io.StringIO()
serve_jsonl_requests(
    input_stream,
    output_stream,
    dispatch,
    error_payload=error_payload,
    state=lambda: {"ready": True},
    max_line_bytes=256,
)
server_replies = [json.loads(line) for line in output_stream.getvalue().splitlines()]
assert server_replies[0] == {
    "id": "a",
    "result": {"method": "ping"},
    "state": {"ready": True},
}
assert server_replies[1]["id"] is None
assert server_replies[1]["error"]["code"] == "invalid"
assert seen == [("ping", {"n": 1})]

oversized_output = io.StringIO()
try:
    serve_jsonl_requests(
        io.StringIO(json.dumps({"id": "big", "method": "ping"}) + "\n"),
        oversized_output,
        lambda method, params: {"payload": "x" * 512},
        error_payload=error_payload,
        max_line_bytes=256,
    )
except ValueError as error:
    assert "reply exceeded" in str(error)
else:
    raise AssertionError("oversized sidecar reply was emitted")
assert oversized_output.getvalue() == ""

print("sidecar_protocol_ok")
