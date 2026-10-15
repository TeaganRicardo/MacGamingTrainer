"""Ordinary operations cross one authoritative worker execution boundary."""
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests")]

from core.adapter import AdapterError
from core.sidecar import SidecarTerminalError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient
from hades2_resident_session_fakes import FakeTimeWarpController


class NativeTransport:
    pid = None
    tainted = False

    def __init__(self):
        self.entries = 0
        self.loss = None

    def alive(self):
        return self.pid is not None

    def attach(self, pid):
        self.pid = pid

    def detach(self):
        self.pid = None

    def close(self):
        self.detach()

    def execute(self, source, **options):
        if not self.alive():
            raise AdapterError("disconnected", "target exited before execution")
        self.entries += 1
        if self.loss == "after_execution":
            raise SidecarTerminalError("reply lost", outcome_unknown=True)
        return json.dumps({"status": "ready", "scene": "run",
                           "capabilities": {"setFeature": True},
                           "desiredFeatures": {}, "activeFeatures": {}})


class LoopbackSidecar:
    started = True
    terminal = False

    def __init__(self, native):
        self.worker = Hades2LLDBWorker(transport=native)
        self.calls = []

    def request(self, method, params=None, **options):
        self.calls.append(method)
        # IPC loss is outside the worker's semantic error envelope.
        if method == "transport.execute" and self.worker.transport.loss:
            return self.worker.dispatch(method, params)
        request = {"id": str(len(self.calls)), "method": method, "params": params or {}}
        output = io.StringIO()
        serve_requests(io.StringIO(json.dumps(request) + "\n"), output, self.worker)
        return json.loads(output.getvalue())

    def close(self):
        self.started = False


with tempfile.TemporaryDirectory(prefix="mgt-operation-liveness-") as temporary:
    native = NativeTransport()
    sidecar = LoopbackSidecar(native)
    with patch.object(preparation, "DATA", Path(temporary)), patch.object(
        _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
    ):
        transport = Hades2LuaTransport()
        transport.attach(4242)
        adapter = Hades2Adapter(transport=transport, time_warp_controller=FakeTimeWarpController())
        adapter.preference_initialized = True
        adapter.preference_dirty = False
        adapter.state.update(connected=True, pid=4242, capabilities={"setFeature": True})

        for operation in (
            lambda: adapter.execute("status", {}),
            lambda: adapter.set_desired("invincibility", True),
            lambda: adapter.execute("set_resource", {"resource": "Money", "amount": 10}),
        ):
            sidecar.calls.clear()
            assert operation()["connected"] is True
            assert sidecar.calls == ["transport.execute"], sidecar.calls

        # A target that exits while the worker stays alive is discovered by the
        # actual execution, before entering a mutation; a later attach is safe.
        native.pid = None
        entries = native.entries
        try:
            adapter.execute("set_resource", {"resource": "Money", "amount": 20})
        except AdapterError as error:
            assert error.code == "disconnected"
        else:
            raise AssertionError("target loss was accepted")
        assert native.entries == entries and transport.pid is None
        assert adapter.state["connected"] is False
        transport.attach(4343)
        assert adapter.execute("status", {})["pid"] == 4343

        # Known idle worker loss must not spawn a fresh un-attached worker and
        # send the original operation into it.
        sidecar.started = False
        sidecar.calls.clear()
        entries = native.entries
        try:
            adapter.execute("set_resource", {"resource": "Money", "amount": 30})
        except AdapterError as error:
            assert error.code == "disconnected"
        else:
            raise AssertionError("idle worker loss was accepted")
        assert not sidecar.calls and native.entries == entries

        sidecar.started = True
        transport.attach(4343)
        native.loss = "after_execution"
        sidecar.calls.clear()
        try:
            adapter.execute("set_resource", {"resource": "Money", "amount": 40})
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("lost mutation reply was accepted")
        assert sidecar.calls == ["transport.execute"]
        entries = native.entries
        try:
            adapter.execute("set_resource", {"resource": "Money", "amount": 40})
        except AdapterError as error:
            assert error.code in ("outcome_unknown", "restart_required")
        else:
            raise AssertionError("uncertain mutation was replayed")
        assert native.entries == entries and sidecar.calls == ["transport.execute"]

print("hades2_operation_liveness_ok")
