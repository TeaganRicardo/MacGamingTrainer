"""Lost initial LLDB attach acknowledgment must not poison a later explicit connect.

This exercises the real JSONL subprocess boundary without attaching to a game or
touching user saves. Only a lost, mutation-free initial attach may be retried.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from core.sidecar import JsonLineSidecarClient
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient


CHILD = r'''
import json
import os
import sys
import time
from pathlib import Path

pid = None
marker = Path(os.environ["MGT_TEST_MARKER"])
mode = os.environ["MGT_TEST_MODE"]
for line in sys.stdin:
    req = json.loads(line)
    method = req["method"]
    if method == "transport.attach":
        pid = req["params"]["pid"]
        if mode == "blocked_initial_attach" and not marker.exists():
            marker.write_text("blocked", encoding="utf-8")
            # Native attach has happened but its acknowledgment is lost.
            time.sleep(0.5)
        elif mode == "blocked_reattach":
            if marker.exists():
                time.sleep(0.5)
            else:
                marker.write_text("first-attach-ok", encoding="utf-8")
        result = True
    elif method == "hello":
        result = {"protocolVersion": 1, "pythonVersion": "fixture"}
    elif method == "transport.alive":
        result = pid is not None
    elif method == "transport.execute":
        if mode == "blocked_mutation":
            marker.write_text("mutated", encoding="utf-8")
            time.sleep(0.5)
        result = "{}"
    elif method in ("transport.close", "transport.detach"):
        pid = None
        result = True
    else:
        result = True
    state = {"pid": pid, "tainted": False, "lastDuration": 0,
             "lastExpressionDuration": 0, "lastAttachProfile": {}}
    sys.stdout.write(json.dumps({"id": req["id"], "result": result,
                                 "state": state}) + "\n")
    sys.stdout.flush()
'''


def run_case(root, mode):
    root.mkdir()
    child = root / "worker.py"
    child.write_text(CHILD, encoding="utf-8")
    marker = root / "marker"
    launches = []

    def new_sidecar():
        launches.append(True)
        return JsonLineSidecarClient(
            [sys.executable, "-u", str(child)],
            reply_timeout_seconds=0.18,
            env=dict(os.environ, MGT_TEST_MARKER=str(marker), MGT_TEST_MODE=mode),
        )

    with patch.object(_LLDBWorkerClient, "_make_sidecar", side_effect=new_sidecar):
        transport = Hades2LuaTransport()
        try:
            if mode == "blocked_initial_attach":
                try:
                    transport.attach(4242)
                except AdapterError as error:
                    assert error.code == "restart_required", error.code
                else:
                    raise AssertionError("the initial attach did not lose its reply")
                assert marker.exists()
                assert len(launches) == 1
                assert transport.pid is None
                # A later Host automatic opportunity must not silently revive
                # the terminal worker after an unacknowledged native attach.
                try:
                    transport.attach(4242, recover_lost_attach=False)
                except AdapterError as error:
                    assert error.code == "restart_required", error.code
                else:
                    raise AssertionError("automatic reattach escaped terminal safety")
                assert len(launches) == 1, "automatic reattach spawned a new worker"
                # A deliberate user Connect supplies fresh recovery authority.
                transport.attach(4242, recover_lost_attach=True)
                assert len(launches) == 2, "explicit reconnect reused a dead worker"
                assert transport.pid == 4242 and transport.alive()
            elif mode == "blocked_reattach":
                transport.attach(4242)
                assert transport.pid == 4242
                for _ in range(2):
                    try:
                        transport.attach(4242)
                    except AdapterError as error:
                        assert error.code == "restart_required", error.code
                    else:
                        raise AssertionError("known attached PID escaped a lost second attach")
                assert len(launches) == 1, "existing attachment was silently reset"
            else:
                transport.attach(4242)
                try:
                    transport.execute("non-replayable mutation")
                except AdapterError as error:
                    assert error.code == "outcome_unknown", error.code
                else:
                    raise AssertionError("the mutation did not lose its reply")
                assert marker.exists()
                try:
                    transport.attach(4242)
                except AdapterError as error:
                    assert error.code == "outcome_unknown", error.code
                else:
                    raise AssertionError("unsafe mutation loss allowed reattach")
                assert len(launches) == 1, "uncertain mutation silently spawned a worker"
        finally:
            transport.close()


with tempfile.TemporaryDirectory(prefix="mgt-attach-terminal-") as temporary:
    root = Path(temporary)
    run_case(root / "attach", "blocked_initial_attach")
    run_case(root / "reattach", "blocked_reattach")
    run_case(root / "mutation", "blocked_mutation")

print("hades2_attach_terminal_recovery_ok")
