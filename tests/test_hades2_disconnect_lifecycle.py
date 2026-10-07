"""Disconnect outcomes cross the real worker, facade and adapter interfaces."""
import io
import json
import sys
import tempfile
from pathlib import Path
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

    def alive(self):
        return self.pid is not None

    def attach(self, pid):
        self.pid = pid

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
    for outcome in ("resume_failed", "restore_failed", "success"):
        native = NativeTransport(outcome)
        sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
        with patch.object(preparation, "DATA", Path(temporary) / outcome), patch.object(
            _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
        ):
            transport = Hades2LuaTransport()
            adapter = Hades2Adapter(transport=transport)
            transport.attach(4242)
            adapter.state.update(connected=True, pid=4242, status="ready", scene="run")
            try:
                if outcome == "success":
                    assert adapter.disconnect()["connected"] is False
                else:
                    try:
                        adapter.disconnect()
                    except AdapterError as error:
                        assert error.code == outcome, error.code
                        if outcome == "resume_failed":
                            assert error.diagnostic == "OS resume denied"
                    else:
                        raise AssertionError("disconnect error was lost")
                if outcome == "restore_failed":
                    assert native.pid == transport.pid == 4242
                    assert adapter.state["connected"] is True, "failed pre-detach recovery lost its attachment"
                else:
                    assert native.pid is None and transport.pid is None, "released worker state was lost"
                    assert adapter.state["connected"] is False, "released debugger still projected connected"
                    assert adapter.state["status"] == "disconnected"
                assert "transport.execute" not in sidecar.calls, "disconnect replayed a Lua operation"
            finally:
                # Release the temporary fake attachment without hiding assertions.
                native.outcome = "success"
                transport.close()

print("hades2_disconnect_lifecycle_ok")
