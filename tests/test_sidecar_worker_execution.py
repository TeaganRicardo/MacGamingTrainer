"""A sidecar worker requests normal self execution before loading its runtime."""
import errno
import io
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core import sidecar
from games.hades2 import lldb_worker


with patch.object(sys, "platform", "darwin"), \
     patch.object(sidecar.os, "setpriority", create=True) as request:
    sidecar.prepare_worker_execution()
    request.assert_called_once_with(4, 0, 0)

with patch.object(sys, "platform", "linux"), \
     patch.object(sidecar.os, "setpriority", create=True) as request:
    sidecar.prepare_worker_execution()
    request.assert_not_called()

failure = OSError(errno.EPERM, "scheduling request denied")
with patch.object(sys, "platform", "darwin"), \
     patch.object(sidecar.os, "setpriority", side_effect=failure, create=True) as request:
    try:
        sidecar.prepare_worker_execution()
    except OSError as error:
        assert error is failure, "normal execution request hid the original OS error"
    else:
        raise AssertionError("failed scheduling request was ignored")
    request.assert_called_once_with(4, 0, 0)


# Use the actual default worker constructor, with only the imported transport
# replaced. Its lazy import must be reached after the Core scheduling request.
events = []


class FakeTransport:
    def __init__(self):
        events.append("transport.construct")

    def close(self):
        events.append("transport.close")


class TransportModule(ModuleType):
    def __getattr__(self, name):
        if name == "Hades2LuaTransport":
            assert events and events[0] == "policy", "transport loaded before worker execution policy"
            events.append("transport.import")
            return FakeTransport
        raise AttributeError(name)


transport_module = TransportModule("games.hades2.transport")


def request_normal_execution(*args):
    assert args == (4, 0, 0), "worker scheduling request selected another process or policy"
    assert not events, "normal execution request happened after runtime work"
    events.append("policy")


def serve(input_stream, output_stream, worker):
    events.append("serve")


with patch.dict(sys.modules, {"games.hades2.transport": transport_module}), \
     patch.object(sys, "platform", "darwin"), \
     patch.object(sidecar.os, "setpriority", side_effect=request_normal_execution, create=True) as request, \
     patch.object(lldb_worker, "serve_requests", side_effect=serve), \
     patch.object(lldb_worker.logging, "basicConfig"), \
     patch.object(sys, "stdin", io.StringIO()), patch.object(sys, "stdout", io.StringIO()):
    assert lldb_worker.main() == 0
    request.assert_called_once_with(4, 0, 0)
assert events[0] == "policy"
assert "transport.import" in events
assert events[-3:] == ["transport.construct", "serve", "transport.close"], events

events.clear()
with patch.dict(sys.modules, {"games.hades2.transport": transport_module}), \
     patch.object(sys, "platform", "darwin"), \
     patch.object(sidecar.os, "setpriority", side_effect=failure, create=True) as request, \
     patch.object(lldb_worker, "serve_requests") as serve_requests, \
     patch.object(lldb_worker.logging, "basicConfig"):
    try:
        lldb_worker.main()
    except OSError as error:
        assert error is failure, "worker startup replaced the OS error"
    else:
        raise AssertionError("worker entered its debugger after policy failure")
    request.assert_called_once_with(4, 0, 0)
    serve_requests.assert_not_called()
assert not events, "policy failure still imported or constructed the transport"

print("sidecar_worker_execution_ok")
