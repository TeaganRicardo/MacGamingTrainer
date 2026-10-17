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
from core.protocol import JsonlRequestRouter
from core.sidecar import SidecarTerminalError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.persistence import PersistenceError
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient
from hades2_resident_session_fakes import FakeTimeWarpController


class NativeTransport:
    pid = None
    tainted = False

    def __init__(self):
        self.entries = 0
        self.loss = None
        self.pending_receipt = False
        self.acknowledged = 0
        self.result = None
        self.sources = []

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
        assert not self.pending_receipt, "a second command overwrote an unaccepted receipt"
        self.entries += 1
        self.sources.append(source)
        if self.loss == "after_execution":
            raise SidecarTerminalError("reply lost", outcome_unknown=True)
        self.pending_receipt = True
        return json.dumps(self.result or {"status": "ready", "scene": "run",
                                         "capabilities": {"setFeature": True},
                                         "desiredFeatures": {}, "activeFeatures": {}})

    def acknowledge_result(self):
        assert self.pending_receipt
        self.pending_receipt = False
        self.acknowledged += 1


class LoopbackSidecar:
    started = True
    terminal = False

    def __init__(self, native):
        self.worker = Hades2LLDBWorker(transport=native)
        self.calls = []
        self.ack_loss = None

    def request(self, method, params=None, **options):
        self.calls.append(method)
        # IPC loss is outside the worker's semantic error envelope.
        if method == "transport.execute" and self.worker.transport.loss:
            return self.worker.dispatch(method, params)
        if method == "transport.acknowledge_result" and self.ack_loss == "before":
            self.started = False
            raise SidecarTerminalError("ACK request lost before release", outcome_unknown=False)
        request = {"id": str(len(self.calls)), "method": method, "params": params or {}}
        output = io.StringIO()
        serve_requests(io.StringIO(json.dumps(request) + "\n"), output, self.worker)
        if method == "transport.acknowledge_result" and self.ack_loss == "after":
            self.started = False
            raise SidecarTerminalError("ACK reply lost after release", outcome_unknown=False)
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
            assert sidecar.calls == ["transport.execute", "transport.acknowledge_result"], sidecar.calls

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

    class ObservedTimeWarp(FakeTimeWarpController):
        def current_speed(self):
            self.calls.append(("observe",))
            return super().current_speed()

    # Public input crosses the real command contract, resident owner, facade,
    # worker dispatch and response router. Losing ACK on either side of its
    # release must preserve the original known outcome while blocking every
    # later command, including dirty preference replay and TimeWarp observation.
    for mode, command, outcome in (
        ("before", "spawn_reward", "completed"),
        ("after", "spawn_reward", "completed"),
        ("before", "open_special_choice", "accepted"),
        ("before", "set_desired", "completed"),
        ("before", "set_resource", "completed"),
        ("persistence_failure", "set_resource", "completed"),
        ("before", "status", "failed"),
    ):
        native = NativeTransport()
        sidecar = LoopbackSidecar(native)
        sidecar.ack_loss = "after" if mode == "after" else "before"
        speed = ObservedTimeWarp()
        request_id = f"known-{mode}-{command}"
        receipt = {"requestId": request_id, "command": command, "outcome": outcome}
        native.result = {"status": "ready", "scene": "run", "capabilities": {"setFeature": True},
                         "desiredFeatures": {}, "activeFeatures": {}, "resources": [],
                         "requestId": request_id, "applied": outcome == "completed",
                         "actionOutcome": outcome, "lastAction": receipt, "money": 321}
        with patch.object(preparation, "DATA", Path(temporary)), patch.object(
            _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
        ):
            transport = Hades2LuaTransport()
            transport.attach(4242)
            adapter = Hades2Adapter(transport=transport, time_warp_controller=speed)
            adapter.preference_initialized = True
            adapter.preference_dirty = True
            adapter.preferences["invincibility"] = True
            adapter.preferences["gameSpeed"] = 2.0
            if command == "set_resource":
                adapter.preferences["resourceLocks"] = {"Money": 100}
                native.result["moneyLocked"] = True
            if mode == "persistence_failure":
                def fail_persistence(_):
                    raise PersistenceError("fixture durable write failure after known action")
                adapter.preference_store.save = fail_persistence
            adapter.state.update(connected=True, pid=4242, capabilities={"setFeature": True})
            router = JsonlRequestRouter(adapter, save_data_root=Path(temporary) / request_id)
            params = {
                "spawn_reward": {"reward": "Money"},
                "open_special_choice": {"source": "Artemis"},
                "set_desired": {"feature": "invincibility", "value": True},
                "set_resource": {"resource": "Money", "amount": 321},
            }.get(command, {})
            request = {"id": request_id, "command": command, "params": params}
            def handled(request):
                with patch("logging.exception"):
                    return router.handle(request)
            sidecar.calls.clear()
            reply = handled(request)
            assert reply["ok"] is False
            assert reply["error"]["code"] == "restart_required", reply
            assert reply["error"]["presentation"] == "hades2.error.commandResultConnectionLost"
            state = reply["state"]
            assert state["lastAction"] == receipt and state["actionOutcome"] == outcome, reply
            assert state["applied"] is (outcome == "completed")
            assert state["money"] == 321
            assert state["status"] == "restart_required" and state["connected"] is False
            assert state["capabilities"]["setFeature"] is False
            assert native.entries == 1 and not speed.calls
            assert native.pending_receipt is (mode != "after")
            assert native.acknowledged == (1 if mode == "after" else 0)
            assert sidecar.calls == ["transport.execute", "transport.acknowledge_result"]
            # A retried identical Host request is served from its original
            # complete error envelope, retaining the known action receipt.
            assert handled(request) == reply
            later = handled({"id": request_id + "-status", "command": "status", "params": {}})
            assert later["error"]["code"] == "restart_required"
            assert later["state"]["lastAction"] == receipt
            try:
                transport.attach(4242, recover_lost_attach=True)
            except AdapterError as error:
                assert error.code == "restart_required"
            else:
                raise AssertionError("ACK failure recreated an unverified game connection")
            assert native.entries == 1 and not speed.calls
            assert sidecar.calls == ["transport.execute", "transport.acknowledge_result"]
            if command == "set_resource":
                assert adapter.preferences["resourceLocks"]["Money"] == 321
                assert adapter._preference_persistence_dirty is (mode == "persistence_failure")
            teardown = handled({"id": request_id + "-cleanup", "command": "disable_all", "params": {}})
            assert teardown["error"]["code"] == "restart_required", teardown
            assert native.entries == 1 and not speed.calls
            transport.close()

print("hades2_operation_liveness_ok")
