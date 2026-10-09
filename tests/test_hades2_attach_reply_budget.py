"""A slow LLDB attach must survive while ordinary sidecar calls remain bounded.

Exercises the real Core JSONL subprocess and Hades worker client with an
isolated fake LLDB worker. No game process, save or debugger is involved.
"""
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient
from games.hades2 import transport_client

FAKE_WORKER = r"""
import json
import sys
import time
for raw in sys.stdin:
    request = json.loads(raw)
    method = request["method"]
    if method == "hello":
        result = {"protocolVersion": 1}
    elif method in ("transport.attach", "transport.alive"):
        time.sleep(0.45)
        result = True
    elif method == "transport.close":
        result = True
    else:
        raise ValueError(method)
    print(json.dumps({"id": request["id"], "result": result, "state": {"pid": 4242}}), flush=True)
"""

def make_client():
    sidecar = JsonLineSidecarClient(
        [sys.executable, "-u", "-c", FAKE_WORKER],
        reply_timeout_seconds=0.25,
    )
    return transport_client._LLDBWorkerClient(sidecar=sidecar)

# Historical healthy attach took 29.139 seconds on the user's Mac. The next
# attach crossed the existing 30-second IPC budget and was reported as a
# misleading debuggerExited error; a 0.45-second worker models that relation.
with patch.object(transport_client, "LLDB_SIDECAR_ATTACH_REPLY_TIMEOUT_SECONDS", 0.75, create=True):
    client = make_client()
    try:
        result, state = client.call("transport.attach", {"pid": 4242})
        assert result is True and state["pid"] == 4242
        assert not client.terminal, "healthy slow attach poisoned LLDB sidecar trust"
    finally:
        client.close()

    client = make_client()
    try:
        try:
            client.call("transport.alive")
        except AdapterError as error:
            assert error.code == "restart_required", error.code
            assert "timed out" in str(error.diagnostic), error.diagnostic
        else:
            raise AssertionError("ordinary LLDB calls accidentally inherited attach budget")
    finally:
        client.close()

print("hades2_attach_reply_budget_ok")
