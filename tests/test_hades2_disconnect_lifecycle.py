"""Disconnect outcomes cross the real worker, facade and adapter interfaces."""
import io
import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.config import PROCESS_NAME
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController, hades2_adapter_context


class NativeTransport:
    pid = None
    tainted = False
    cleanup_pending = False
    pending_resume_pid = None

    def __init__(self, outcome):
        self.outcome = outcome
        self.native_entries = 0
        self.detach_calls = 0
        self.detach_failures = 0

    def alive(self):
        return self.pid is not None

    def attach(self, pid):
        self.pid = pid
        if self.outcome == "attach_release_failed":
            self.pid = None
            self.cleanup_pending = True
            self.pending_resume_pid = pid
            raise AdapterError("resume_failed", "hades2.error.resumeFailed",
                               diagnostic="OS resume denied", arguments=["OS resume denied"])
        if self.outcome == "attach_rollback_lldb_failed":
            self.cleanup_pending = True
            raise AdapterError("incompatible", "hades2.error.unsupportedBuild",
                               diagnostic="rollback lldb_detach failed")

    def detach(self):
        self.detach_calls += 1
        if self.detach_failures:
            self.detach_failures -= 1
            self.cleanup_pending = True
            raise AdapterError("detach_failed", "synthetic detach failure")
        if self.pid is None and not self.cleanup_pending:
            return
        if self.outcome == "restore_failed":
            raise AdapterError("restore_failed", "hades2.error.focusNotRestored")
        if self.outcome == "attach_rollback_lldb_failed":
            raise AdapterError("detach_failed", "synthetic detach error")
        self.pid = None
        if self.outcome in ("resume_failed", "attach_release_failed"):
            raise AdapterError("resume_failed", "hades2.error.resumeFailed",
                               diagnostic="OS resume denied", arguments=["OS resume denied"])
        self.cleanup_pending = False
        self.pending_resume_pid = None

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
            with patch.object(
                _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
            ), patch.object(preparation, "compatibility", return_value={
                "version": "1.143476", "steam_build": "fixture", "warnings": [],
            }), patch("games.hades2.adapter.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout="4343\n" if operation == "scan_replacement" else "4242\n", stderr="",
            )):
                transport = Hades2LuaTransport()
                adapter = Hades2Adapter(context=hades2_adapter_context(Path(temporary) / operation / outcome), transport=transport)
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
                        # Connect's failed initial status performs its own safe detach.
                        assert native.pid is None and transport.pid is None
                        assert transport.tainted
                        assert adapter.state["connected"] is False
                        assert sidecar.calls.count("transport.detach") == 1
                        try:
                            transport.execute("another native mutation")
                        except AdapterError as error:
                            assert error.code == "outcome_unknown"
                        else:
                            raise AssertionError("terminal connection allowed another mutation")
                        assert native.native_entries == 1, "unknown native call was replayed"
                    elif outcome == "restore_failed":
                        assert native.pid == transport.pid == 4242
                        assert adapter.state["connected"] is True, "failed pre-detach recovery lost its attachment"
                        assert adapter.state["pid"] == 4242, "failed cleanup relabeled the old attachment"
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

with tempfile.TemporaryDirectory(prefix="mgt-replacement-observation-") as temporary:
    for transition in ("attached_replacement", "detached_replacement", "exit_then_replacement"):
        visible_pid = 4141

        def query_target(command, **kwargs):
            assert command == ["/usr/bin/pgrep", "-x", PROCESS_NAME]
            return SimpleNamespace(returncode=int(visible_pid is None),
                                   stdout=f"{visible_pid}\n" if visible_pid else "", stderr="")

        def initial_probe(session, request):
            if session.pid == 5151:
                assert request["command"] == "status"
                return AdapterError("waiting", "synthetic replacement is still loading")

        resident = FakeResidentSession({
            "status": "ready", "scene": "run", "health": 812, "maxHealth": 900,
            "money": 75, "rerolls": 6, "biomeTime": 23, "runCount": 17,
            "currentRunTraits": [{"instanceId": "previous-trait"}],
            "gardenScopeToken": "previous-garden",
            "chaosGateTarget": {"scopeToken": "previous-chaos"},
            "facilityOptions": [{"id": "previous-facility"}],
            "statAvailable": {"dodge": True},
            "stats": {"dodge": {"value": 80, "locked": False}},
            "resources": [
                {"id": "Ore", "name": "Ore", "count": 91, "locked": False},
                {"id": "Ash", "name": "Ash", "count": 90, "locked": True},
            ],
            "elements": [{"id": "Fire", "name": "Fire", "count": 7, "locked": False}],
            "rewards": [{"id": "StaticReward"}],
            "boons": [{"id": "StaticBoon"}],
            "nativeRarityOrder": ["Common", "Rare"],
            "occurrenceTargets": [{"id": "StaticOccurrence"}],
            "lastAction": {"requestId": "previous-action", "outcome": "completed"},
            "runtimeDiagnostics": {"revision": 7, "heroObjectId": 812},
        }, handler=initial_probe, pid=4141)
        with patch.object(
            preparation, "compatibility", return_value={
                "version": "1.143476", "steam_build": "fixture", "warnings": [],
            },
        ), patch("games.hades2.adapter.subprocess.run", side_effect=query_target):
            adapter = Hades2Adapter(
                context=hades2_adapter_context(Path(temporary) / transition),
                resident_session=resident,
                time_warp_controller=FakeTimeWarpController(),
            )
            adapter.preferences["gameSpeed"] = 1.5
            adapter.save_profile("Unlocked")
            unlocked_desired = deepcopy(adapter.preferences)
            adapter.preferences.update(
                vitalLocks={"health": {"current": 60, "max": 100}}, rerollsLock=9,
                resourceLocks={"Money": 33, "Ash": 24}, elementLocks={"Fire": 55}, statLocks={"grasp": 30},
            )
            desired = deepcopy(adapter.preferences)
            old = adapter.observe_runtime()
            assert old["pid"] == 4141 and old["health"] == 812
            if transition == "detached_replacement":
                assert adapter.disconnect()["connected"] is False
                same_target = adapter.dispatch("scan", {}, "same-target")
                assert same_target["pid"] == 4141 and same_target["health"] == 812
                assert same_target["currentRunTraits"] == [{"instanceId": "previous-trait"}]
                assert same_target["resources"][0]["count"] == 91

            def assert_observations_retired(state, locked=True):
                assert state["health"] is None and state["maxHealth"] is None, (
                    transition, state["pid"], state["health"], state["maxHealth"],
                )
                assert state["money"] == (33 if locked else None), (transition, locked, state["money"])
                assert state["biomeTime"] is None and state["runCount"] is None
                assert state["currentRunTraits"] == [] and state["gardenScopeToken"] is None
                assert state["chaosGateTarget"] is None and state["facilityOptions"] == []
                assert state["lastAction"] is None and state["runtimeDiagnostics"] is None
                assert state["statAvailable"] == {} and "dodge" not in state["stats"]
                assert state["resources"] == [
                    {"id": "Ore", "name": "Ore", "count": None, "locked": False},
                    {"id": "Ash", "name": "Ash", "count": 24 if locked else None, "locked": locked},
                ]
                assert state["elements"] == [
                    {"id": "Fire", "name": "Fire", "count": 55 if locked else None, "locked": locked},
                ]
                assert all(state[key] is locked for key in ("healthLocked", "moneyLocked", "rerollsLocked"))
                assert state["rerolls"] == (9 if locked else None)
                stat_value = 30 if locked else None
                assert state["stats"]["grasp"] == {"locked": locked, "target": stat_value, "value": stat_value}
                assert state["rewards"] == [{"id": "StaticReward"}] and state["boons"] == [{"id": "StaticBoon"}]
                assert state["nativeRarityOrder"] == ["Common", "Rare"]
                assert state["occurrenceTargets"] == [{"id": "StaticOccurrence"}]
                assert state["gameSpeed"] == 1.5
                assert adapter.preferences == (desired if locked else unlocked_desired)

            if transition == "exit_then_replacement":
                visible_pid = None
                exited = adapter.dispatch("scan", {}, "target-exited")
                assert exited["pid"] is None and exited["status"] == "not_running"
                assert_observations_retired(exited)

            visible_pid = 5151
            found = adapter.dispatch("scan", {}, "find-replacement")
            assert found["pid"] == 5151 and found["connected"] is False
            assert_observations_retired(found)

            unlocked = adapter.dispatch("load_profile", {"name": "Unlocked"}, "load-profile")
            assert unlocked["pid"] == 5151 and unlocked["connected"] is False
            assert unlocked["loadedProfile"] == "Unlocked"
            assert_observations_retired(unlocked, locked=False)

            waiting = adapter.dispatch("connect", {"probeRuntime": True}, "connect-replacement")
            assert waiting["pid"] == 5151 and waiting["connected"] is True and waiting["status"] == "waiting"
            assert_observations_retired(waiting, locked=False)

            resident.handler = None
            resident.payload = {
                "status": "ready", "scene": "run", "health": 63, "maxHealth": 120,
                "money": 12, "rerolls": 2,
                "currentRunTraits": [{"instanceId": "replacement-trait"}],
                "resources": [{"id": "Ore", "name": "Ore", "count": 3, "locked": False}],
                "elements": [{"id": "Fire", "name": "Fire", "count": 8, "locked": False}],
                "stats": {"grasp": {"value": 13, "target": None, "locked": False}},
            }
            fresh = adapter.observe_runtime()
            assert fresh["pid"] == 5151 and fresh["status"] == "ready" and fresh["health"] == 63
            assert fresh["currentRunTraits"] == [{"instanceId": "replacement-trait"}]
            assert fresh["resources"][0]["count"] == 3 and adapter.preferences == unlocked_desired
            adapter.disconnect()
            detached = adapter.dispatch("load_profile", {"name": "Unlocked"}, "load-after-observation")
            assert detached["pid"] == 5151 and detached["connected"] is False
            assert detached["money"] == 12 and detached["rerolls"] == 2
            assert detached["resources"][0]["count"] == 3 and detached["elements"][0]["count"] == 8
            assert detached["stats"]["grasp"]["value"] == 13
            assert [call["kind"] for call in resident.calls] == ["observe", "status", "observe"]
            adapter.close()

with tempfile.TemporaryDirectory(prefix="mgt-quarantine-recovery-") as temporary:
    for scenario in ("lldb_still_attached", "os_resume_pending"):
        native = NativeTransport(
            "attach_rollback_lldb_failed" if scenario == "lldb_still_attached" else "attach_release_failed",
        )
        sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
        with patch.object(
            _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
        ), patch.object(preparation, "compatibility", return_value={
            "version": "1.143476", "steam_build": "fixture", "warnings": [],
        }), patch("games.hades2.adapter.subprocess.run", return_value=SimpleNamespace(
            returncode=0, stdout="4242\n", stderr="",
        )):
            transport = Hades2LuaTransport()
            adapter = Hades2Adapter(context=hades2_adapter_context(Path(temporary) / scenario), transport=transport)
            try:
                adapter.connect()
            except AdapterError as error:
                expected_code = "incompatible" if scenario == "lldb_still_attached" else "resume_failed"
                assert error.code == expected_code, (scenario, error.code)
            else:
                raise AssertionError(f"{scenario} attach failure was suppressed")
            assert transport.cleanup_pending is True
            if scenario == "lldb_still_attached":
                assert native.pid == transport.pid == 4242
                assert adapter.runtime.cleanup_pending is True
            else:
                assert native.pid is None and transport.pid is None
                assert transport.pending_resume_pid == 4242
                assert adapter.runtime.cleanup_pending is True
            # Once the transient cleanup blocker clears, adapter.disconnect() must finish recovery.
            native.outcome = "success"
            result = adapter.disconnect()
            assert result["connected"] is False
            assert native.pid is None and transport.pid is None
            assert transport.cleanup_pending is False
            assert transport.pending_resume_pid is None
            assert "transport.detach" in sidecar.calls
            transport.close()
            native.close()

# A persistent native close failure must remain visible through the worker and
# facade, and the live sidecar must remain available for a later retry.
for outcome, expected_code in (
    ("attach_rollback_lldb_failed", "detach_failed"),
    ("attach_release_failed", "resume_failed"),
):
    native = NativeTransport(outcome)
    sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
    with patch.object(_LLDBWorkerClient, "_make_sidecar", return_value=sidecar):
        transport = Hades2LuaTransport()
        try:
            transport.attach(4242)
        except AdapterError:
            pass
        else:
            raise AssertionError("cleanup fixture did not fail attach")
        assert transport.cleanup_pending
        try:
            transport.close()
        except AdapterError as error:
            assert error.code == expected_code, (outcome, error.code)
        else:
            raise AssertionError(f"{outcome} cleanup failure was lost during close")
        assert sidecar.started and transport.cleanup_pending
        assert transport._worker.started and not transport._worker.terminal
        if outcome == "attach_rollback_lldb_failed":
            assert transport.pid == native.pid == 4242
        else:
            assert transport.pid is None and transport.pending_resume_pid == 4242
        # The same worker must be able to finish once the blocker clears.
        native.outcome = "success"
        transport.close()
        assert not sidecar.started
        assert transport.pid is None and not transport.cleanup_pending
        assert transport.pending_resume_pid is None
        assert sidecar.calls.count("transport.close") == 2

# An established session can be explicitly disconnected after a semantic terminal error.
with tempfile.TemporaryDirectory(prefix="mgt-semantic-terminal-disconnect-") as temporary:
    native = NativeTransport("success")
    sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
    with patch.object(
        _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
    ):
        transport = Hades2LuaTransport()
        adapter = Hades2Adapter(context=hades2_adapter_context(temporary), transport=transport)
        transport.attach(4242)
        adapter.state.update(connected=True, pid=4242, status="ready", scene="run")
        try:
            transport.execute("uncertain native mutation")
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("native outcome uncertainty was swallowed")
        assert transport.pid == native.pid == 4242
        disconnected = adapter.disconnect()
        assert disconnected["connected"] is False
        assert native.detach_calls == 1
        assert native.pid is None and transport.pid is None
        assert sidecar.calls.count("transport.detach") == 1
        transport.close()

# Semantic outcome-unknown permits only native cleanup on a trusted live sidecar.
with tempfile.TemporaryDirectory(prefix="mgt-semantic-terminal-close-") as temporary:
    native = NativeTransport("success")
    native.detach_failures = 1
    sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
    with patch.object(
        _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
    ):
        transport = Hades2LuaTransport()
        transport.attach(4242)
        try:
            transport.execute("uncertain native mutation")
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("native outcome uncertainty was swallowed")
        assert transport.tainted and transport.pid == 4242
        try:
            transport.close()
        except AdapterError as error:
            assert error.code == "detach_failed"
        else:
            raise AssertionError("persistent detach failure was swallowed")
        assert sidecar.started and transport.pid == native.pid == 4242
        assert transport.cleanup_pending and transport._worker.terminal
        assert sidecar.calls.count("transport.close") == 1
        # Once the detach blocker clears, close retries through the same trusted worker.
        transport.close()
        assert sidecar.calls.count("transport.close") == 2
        assert not sidecar.started and transport.pid is None
        assert not transport.cleanup_pending and not transport._worker.terminal

# A dead/untrusted sidecar cannot acknowledge release; retain the PID and report it.
with tempfile.TemporaryDirectory(prefix="mgt-lost-terminal-sidecar-") as temporary:
    native = NativeTransport("success")
    sidecar = LoopbackSidecar(Hades2LLDBWorker(transport=native))
    with patch.object(
        _LLDBWorkerClient, "_make_sidecar", return_value=sidecar,
    ):
        transport = Hades2LuaTransport()
        transport.attach(4242)
        try:
            transport.execute("uncertain native mutation")
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("native outcome uncertainty was swallowed")
        sidecar.started = False
        sidecar.terminal = True
        try:
            transport.detach()
        except AdapterError as error:
            assert error.code == "detach_failed"
        else:
            raise AssertionError("dead sidecar falsely acknowledged detach")
        try:
            transport.close()
        except AdapterError as error:
            assert error.code == "detach_failed"
        else:
            raise AssertionError("dead sidecar falsely acknowledged close")
        assert transport.pid == native.pid == 4242
        assert "transport.detach" not in sidecar.calls
        assert "transport.close" not in sidecar.calls

print("hades2_disconnect_lifecycle_ok")
