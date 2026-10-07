"""Disconnect outcomes cross the real worker, facade and adapter interfaces."""
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient


class NativeTransport:
    pid = None
    tainted = False

    def __init__(self, outcome):
        self.outcome = outcome
        self.native_entries = 0

    def alive(self):
        return self.pid is not None

    def attach(self, pid):
        self.pid = pid
        if self.outcome == "attach_release_failed":
            self.pid = None
            raise AdapterError("resume_failed", "hades2.error.resumeFailed",
                               diagnostic="OS resume denied", arguments=["OS resume denied"])

    def detach(self):
        if self.pid is None:
            return
        if self.outcome == "restore_failed":
            raise AdapterError("restore_failed", "hades2.error.focusNotRestored")
        self.pid = None
        if self.outcome == "resume_failed":
            raise AdapterError("resume_failed", "hades2.error.resumeFailed",
                               diagnostic="OS resume denied", arguments=["OS resume denied"])

    def close(self):
        self.detach()

    def execute(self, source, **options):
        self.native_entries += 1
        self.tainted = True
        raise AdapterError("outcome_unknown", "hades2.error.outcomeUnknownGeneric")


class LoopbackSidecar:
    started = True
    terminal = False

    def __init__(self, worker):
        self.worker = worker
        self.calls = []

    def request(self, method, params=None, **options):
        self.calls.append(method)
        request = json.dumps({"id": str(len(self.calls)), "method": method, "params": params or {}})
        output = io.StringIO()
        serve_requests(io.StringIO(request + "\n"), output, self.worker)
        return json.loads(output.getvalue())

    def close(self):
        self.started = False


with tempfile.TemporaryDirectory(prefix="mgt-disconnect-lifecycle-") as temporary:
    for operation in ("disconnect", "connect_cleanup", "scan_replacement", "attach_failure", "connect_unknown"):
        outcomes = {
            "attach_failure": ("attach_release_failed",),
            "connect_unknown": ("outcome_unknown",),
        }.get(operation, ("resume_failed", "restore_failed", "success"))
        for outcome in outcomes:
            native = NativeTransport(outcome)
            sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
            with patch.object(preparation, "DATA", Path(temporary) / operation / outcome), patch.object(
                _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
            ), patch.object(preparation, "compatibility", return_value={
                "version": "1.143476", "steam_build": "fixture", "warnings": [],
            }), patch("games.hades2.adapter.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout="4343\n" if operation == "scan_replacement" else "4242\n", stderr="",
            )):
                transport = Hades2LuaTransport()
                adapter = Hades2Adapter(transport=transport)
                if operation != "attach_failure":transport.attach(4242)
                adapter.state.update(connected=True, pid=4242, status="ready", scene="run")
                desired = dict(adapter.preferences)

                def perform():
                    if operation == "disconnect":return adapter.disconnect()
                    if operation == "scan_replacement":return adapter.scan()
                    if operation == "connect_unknown":return adapter.connect()
                    with patch.object(adapter, "execute", side_effect=AdapterError(
                        "incompatible", "fixture bootstrap failure",
                    )):
                        return adapter.connect()

                try:
                    if outcome == "success" and operation != "connect_cleanup":
                        assert perform()["connected"] is False
                    else:
                        try:
                            perform()
                        except AdapterError as error:
                            expected = ("incompatible" if outcome == "success" else
                                        "resume_failed" if outcome == "attach_release_failed" else outcome)
                            assert error.code == expected, (operation, outcome, error.code)
                            if error.code == "resume_failed":
                                assert error.diagnostic == "OS resume denied"
                        else:
                            raise AssertionError("disconnect error was lost")
                    if outcome == "outcome_unknown":
                        assert native.pid == transport.pid == 4242
                        assert transport.tainted and adapter.state["status"] == "restart_required"
                        assert adapter.state["connected"] is True, "uncertain attachment was described as released"
                        try:
                            transport.execute("another native mutation")
                        except AdapterError as error:
                            assert error.code == "outcome_unknown"
                        else:
                            raise AssertionError("terminal connection allowed another mutation")
                        assert native.native_entries == 1, "unknown native call was replayed"
                        assert "transport.detach" not in sidecar.calls, "terminal worker accepted cleanup RPC"
                    elif outcome == "restore_failed":
                        assert native.pid == transport.pid == 4242
                        assert adapter.state["connected"] is True, "failed pre-detach recovery lost its attachment"
                    else:
                        assert native.pid is None and transport.pid is None, "released worker state was lost"
                        assert adapter.state["connected"] is False, "released debugger still projected connected"
                        assert adapter.state["status"] == "disconnected"
                    if outcome != "outcome_unknown":
                        assert "transport.execute" not in sidecar.calls, "disconnect replayed a Lua operation"
                    assert adapter.preferences == desired, "attachment cleanup changed durable desired state"
                finally:
                    # Release the temporary fake attachment without hiding assertions.
                    native.outcome = "success"
                    transport.close()
                    native.close()

print("hades2_disconnect_lifecycle_ok")
