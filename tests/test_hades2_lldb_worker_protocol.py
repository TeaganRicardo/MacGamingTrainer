import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from core.sidecar import SidecarStartError, SidecarTerminalError
from games.hades2.config import LLDB_SIDECAR_REPLY_TIMEOUT_SECONDS
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import _LLDBWorkerClient


class FakeTransport:
    def __init__(self):
        self.pid = None
        self.tainted = False
        self.last_duration = 0.0
        self.last_expression_duration = 0.0
        self.last_attach_profile = {}

    def alive(self):
        return self.pid is not None

    def attach(self, pid):
        self.pid = pid
        self.last_attach_profile = {"attachProcess": 0.01}

    def detach(self):
        self.pid = None
        self.tainted = False

    def close(self):
        self.detach()

    def execute(self, source, *, expression_timeout_seconds=2.0):
        self.last_duration = 0.25
        self.last_expression_duration = expression_timeout_seconds
        if source == "fail":
            self.tainted = True
            raise AdapterError(
                "outcome_unknown",
                "unknown outcome",
                diagnostic="fake uncertain result",
                arguments=("fake",),
            )
        return "result:" + source


class FakeTimeWarp:
    def __init__(self):
        self.speed = 1.0

    def set_speed(self, value):
        self.speed = float(value)
        return self.speed

    def current_speed(self):
        return self.speed

    def reset(self):
        self.speed = 1.0
        return self.speed


created = []


def make_time_warp(transport, helper_path, image_names):
    assert transport is fake_transport
    assert helper_path == "/tmp/libMGTTimeWarp.dylib"
    assert image_names == ["Hades II"]
    controller = FakeTimeWarp()
    created.append(controller)
    return controller


fake_transport = FakeTransport()
worker = Hades2LLDBWorker(
    transport=fake_transport,
    time_warp_factory=make_time_warp,
)
requests = [
    {"id": "1", "method": "hello", "params": {}},
    {"id": "2", "method": "transport.attach", "params": {"pid": 4242}},
    {
        "id": "3",
        "method": "transport.execute",
        "params": {"source": "return true", "expressionTimeoutSeconds": 4.5},
    },
    {
        "id": "4",
        "method": "time_warp.configure",
        "params": {
            "helperPath": "/tmp/libMGTTimeWarp.dylib",
            "imageNames": ["Hades II"],
        },
    },
    {"id": "5", "method": "time_warp.set_speed", "params": {"value": 2.5}},
    {"id": "6", "method": "time_warp.current_speed", "params": {}},
    {"id": "7", "method": "transport.execute", "params": {"source": "fail"}},
]
input_stream = io.StringIO(
    "".join(json.dumps(request) + "\n" for request in requests)
)
output_stream = io.StringIO()
serve_requests(input_stream, output_stream, worker)
replies = [json.loads(line) for line in output_stream.getvalue().splitlines()]

assert [reply["id"] for reply in replies] == [str(index) for index in range(1, 8)]
assert replies[0]["result"]["protocolVersion"] == 1
assert replies[1]["state"]["pid"] == 4242
assert replies[1]["state"]["lastAttachProfile"] == {"attachProcess": 0.01}
assert replies[2]["result"] == "result:return true"
assert replies[2]["state"]["lastDuration"] == 0.25
assert replies[2]["state"]["lastExpressionDuration"] == 4.5
assert replies[4]["result"] == 2.5
assert replies[5]["result"] == 2.5
assert len(created) == 1
assert replies[6]["error"] == {
    "code": "outcome_unknown",
    "presentation": "unknown outcome",
    "diagnostic": "fake uncertain result",
    "arguments": ["fake"],
}
assert replies[6]["state"]["tainted"] is True


class FakeSidecar:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.marked_unknown = []
        self.started = True
        self.terminal = False
        self.closed = False

    def request(self, method, params=None, *, outcome_unknown_on_loss=False):
        self.calls.append((method, dict(params or {}), outcome_unknown_on_loss))
        if not self.responses:
            raise AssertionError(f"unexpected sidecar request: {method}")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            self.started = False
            if not isinstance(response, SidecarStartError):
                self.terminal = True
            raise response
        self.started = True
        return response

    def invalidate(self, detail, *, outcome_unknown=False):
        self.terminal = True
        self.started = False
        raise SidecarTerminalError(detail, outcome_unknown=outcome_unknown)

    def mark_outcome_unknown(self, detail):
        self.marked_unknown.append(detail)
        self.terminal = True
        self.started = False

    def close(self):
        self.closed = True
        self.started = False


# Hades owns the worker handshake, method risk classification, timeout budget
# and presentation mapping while Core owns the underlying request/reply mechanics.
configured_sidecar = _LLDBWorkerClient._make_sidecar()
assert configured_sidecar.reply_timeout_seconds == LLDB_SIDECAR_REPLY_TIMEOUT_SECONDS
configured_sidecar.close()

healthy_sidecar = FakeSidecar([
    {"id": "1", "result": {"protocolVersion": 1}},
    {"id": "2", "result": True, "state": {"pid": 4242}},
])
healthy_client = _LLDBWorkerClient(sidecar=healthy_sidecar)
assert healthy_client.call("transport.alive") == (True, {"pid": 4242})
assert healthy_sidecar.calls == [
    ("hello", {}, False),
    ("transport.alive", {}, False),
]

recoverable_sidecar = FakeSidecar([
    {"id": "1", "result": {"protocolVersion": 1}},
    {"id": "2", "result": True, "state": {"pid": 4242}},
    {"id": "3", "result": {"protocolVersion": 1}},
    {"id": "4", "result": True, "state": {"pid": None}},
])
recoverable_client = _LLDBWorkerClient(sidecar=recoverable_sidecar)
assert recoverable_client.call("transport.alive")[0] is True
recoverable_sidecar.started = False
assert recoverable_client.started, (
    "an established Hades worker must remain restartable after a between-request child exit"
)
assert recoverable_client.call("transport.alive")[0] is True
assert [method for method, _, _ in recoverable_sidecar.calls] == [
    "hello",
    "transport.alive",
    "hello",
    "transport.alive",
]

lost_mutation_sidecar = FakeSidecar([
    {"id": "1", "result": {"protocolVersion": 1}},
    SidecarTerminalError("lost LLDB acknowledgement", outcome_unknown=True),
])
lost_mutation_client = _LLDBWorkerClient(sidecar=lost_mutation_sidecar)
try:
    lost_mutation_client.call("transport.execute", {"source": "return true"})
except AdapterError as error:
    assert error.code == "outcome_unknown", error.code
    assert error.presentation == "hades2.error.outcomeUnknownGeneric"
else:
    raise AssertionError("lost mutating LLDB reply was not outcome-unknown")
assert lost_mutation_sidecar.calls[-1][2] is True
try:
    lost_mutation_client.call("transport.alive")
except AdapterError as error:
    assert error.code == "outcome_unknown", "terminal trust failure was not sticky"
else:
    raise AssertionError("terminal LLDB sidecar was reused")

reported_unknown_sidecar = FakeSidecar([
    {"id": "1", "result": {"protocolVersion": 1}},
    {
        "id": "2",
        "error": {
            "code": "outcome_unknown",
            "presentation": "hades2.error.outcomeUnknownGeneric",
            "diagnostic": "worker lost mutation acknowledgement",
            "arguments": [],
        },
        "state": {"tainted": True},
    },
])
reported_unknown_client = _LLDBWorkerClient(sidecar=reported_unknown_sidecar)
try:
    reported_unknown_client.call("transport.execute", {"source": "return true"})
except AdapterError as error:
    assert error.code == "outcome_unknown"
else:
    raise AssertionError("worker outcome_unknown was accepted")
assert reported_unknown_sidecar.marked_unknown == [
    "worker lost mutation acknowledgement"
]
assert reported_unknown_client.terminal

unavailable_sidecar = FakeSidecar([
    SidecarStartError("xcrun python3 unavailable"),
    {"id": "1", "result": {"protocolVersion": 1}},
    {"id": "2", "result": True, "state": {"pid": None}},
])
unavailable_client = _LLDBWorkerClient(sidecar=unavailable_sidecar)
try:
    unavailable_client.call("transport.alive")
except AdapterError as error:
    assert error.code == "debugger_unavailable", error.code
    assert error.presentation == "hades2.error.debuggerUnavailable"
else:
    raise AssertionError("sidecar start failure lost Hades debugger presentation")
assert not unavailable_client.terminal
assert not unavailable_client.started
assert unavailable_client.call("transport.alive")[0] is True

protocol_sidecar = FakeSidecar([
    {"id": "1", "result": {"protocolVersion": 999}},
    {"id": "2", "result": {"protocolVersion": 1}},
    {"id": "3", "result": True, "state": {"pid": None}},
])
protocol_client = _LLDBWorkerClient(sidecar=protocol_sidecar)
try:
    protocol_client.call("transport.alive")
except AdapterError as error:
    assert error.code == "debugger_protocol", error.code
else:
    raise AssertionError("worker protocol mismatch was accepted")
assert not protocol_client.terminal
assert not protocol_client.started
assert protocol_client.call("transport.alive")[0] is True

print("hades2_lldb_worker_protocol_ok")
