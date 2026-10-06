import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests


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

print("hades2_lldb_worker_protocol_ok")
