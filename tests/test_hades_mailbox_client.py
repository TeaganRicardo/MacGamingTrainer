"""Portable Hades I mailbox client, transport fallback/routing, and worker non-replay tests."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades.client import HadesRuntimeClient
from games.hades.lldb_worker import HadesLLDBWorker, error_payload
from games.hades.recovery import HadesRecoveryJournal
from games.hades.world import reward_catalog
from games.hades.mailbox import (
    ERROR,
    GENERATION_CHANGED,
    HadesCommandMailbox,
    OK,
    SUCCESS,
)

compiler = shutil.which("cc")
assert compiler, "A C compiler is required to build the portable Hades mailbox ABI library"

with tempfile.TemporaryDirectory(prefix="mgt-hades-mailbox-client-") as temporary:
    tmp = Path(temporary)
    dylib_ext = ".dylib" if sys.platform == "darwin" else ".so"
    shared_lib = tmp / f"libhadesmailbox{dylib_ext}"
    subprocess.run([
        compiler, "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-DMGT_MAILBOX_PORTABLE_TEST=1", "-D_POSIX_C_SOURCE=200809L",
        "-I", str(ROOT / "Backend/games/hades/native"),
        str(ROOT / "Backend/games/hades/native/CommandMailbox.c"),
        "-o", str(shared_lib),
    ], check=True)

    # Also compile a tiny helper exposing mgt_mailbox_claim/complete to simulate the game thread.
    consumer_src = tmp / "consumer.c"
    consumer_lib = tmp / f"libconsumer{dylib_ext}"
    consumer_src.write_text(
        '#define _POSIX_C_SOURCE 200809L\n'
        '#include "MailboxProtocol.h"\n'
        'int test_claim(void *s, uint64_t hi, uint64_t lo, MGTMailboxRequest *r) {\n'
        '  return mgt_mailbox_claim((MGTMailboxSlot *)s, hi, lo, r);\n'
        '}\n'
        'int test_complete(void *s, uint64_t hi, uint64_t lo, uint64_t seq, uint32_t out, int32_t st, const void *b, size_t n) {\n'
        '  return mgt_mailbox_complete((MGTMailboxSlot *)s, hi, lo, seq, out, st, b, n, 1000);\n'
        '}\n',
        encoding="utf-8",
    )
    subprocess.run([
        compiler, "-shared", "-fPIC", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-D_POSIX_C_SOURCE=200809L",
        "-I", str(ROOT / "Backend/games/hades/native"),
        str(consumer_src), "-o", str(consumer_lib),
    ], check=True)

    import ctypes

    c_mod = ctypes.CDLL(str(consumer_lib))

    class Req(ctypes.Structure):
        _fields_ = [("sequence", ctypes.c_uint64), ("source", ctypes.c_void_p), ("length", ctypes.c_size_t)]

    c_mod.test_claim.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.POINTER(Req)]
    c_mod.test_claim.restype = ctypes.c_int
    c_mod.test_complete.argtypes = [
        ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64,
        ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t,
    ]
    c_mod.test_complete.restype = ctypes.c_int

    # 1. Normal execute + acknowledge round-trip
    mb = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
    mb.installed_in_target()

    def run_consumer_once(outcome, status, reply_bytes, target_mailbox=None):
        target_mailbox = mb if target_mailbox is None else target_mailbox

        def worker():
            req = Req()
            for _ in range(5000):
                rc = c_mod.test_claim(target_mailbox.address, target_mailbox.generation_hi, target_mailbox.generation_lo, ctypes.byref(req))
                if rc == OK:
                    buf = ctypes.create_string_buffer(reply_bytes, len(reply_bytes))
                    assert c_mod.test_complete(
                        target_mailbox.address, target_mailbox.generation_hi, target_mailbox.generation_lo,
                        req.sequence, outcome, status, buf, len(reply_bytes),
                    ) == OK
                    return
                time.sleep(0.001)
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return t

    t = run_consumer_once(SUCCESS, 0, b'{"ok":true}')
    assert mb.execute('return "{}"') == '{"ok":true}'
    mb.acknowledge()
    t.join(timeout=2)
    assert not mb.tainted

    # 2. Timeout before claim cancels cleanly without tainting
    try:
        mb.execute('return "{}"', timeout_seconds=0.02, mutating=True)
    except AdapterError as error:
        assert error.code == "runtime_not_ready" and error.presentation == "hades.error.runtimeNotReady"
    else:
        raise AssertionError("unclaimed timeout succeeded")
    assert not mb.tainted

    # 3. GENERATION_CHANGED acks and raises resident_generation_missing without tainting
    t = run_consumer_once(ERROR, GENERATION_CHANGED, b"Lua generation changed")
    try:
        mb.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == "resident_generation_missing"
    else:
        raise AssertionError("GENERATION_CHANGED succeeded")
    t.join(timeout=2)
    assert not mb.tainted and mb._pending_sequence is None

    # 4. Known Lua refusal key leaves mailbox untainted and retryable
    t = run_consumer_once(ERROR, 2, b"runtime.lua:10: hades.error.staleDoor")
    try:
        mb.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == "runtime_not_ready" and error.presentation == "hades.error.staleDoor"
    else:
        raise AssertionError("staleDoor succeeded")
    t.join(timeout=2)
    assert not mb.tainted and mb._pending_sequence is None

    # 5. Unexpected mutating error poisons and refuses replay
    t = run_consumer_once(ERROR, 2, b"boom")
    try:
        mb.execute('return "{}"', mutating=True)
    except AdapterError as error:
        assert error.code == "outcome_unknown" and error.presentation == "hades.error.outcomeUnknown"
    else:
        raise AssertionError("unexpected mutating error was not unknown")
    t.join(timeout=2)
    assert mb.tainted
    mb.close()

    # 6. Transport _execute_mailbox & detach real-PID SIGCONT guard
    fake_lldb = types.SimpleNamespace(
        SBError=lambda: types.SimpleNamespace(Fail=lambda: False, Success=lambda: True),
        eStateStopped=5, eStateRunning=6, eStateExited=10,
    )
    with patch.dict(sys.modules, {"lldb": fake_lldb}), patch("subprocess.check_output", return_value=""):
        from games.hades import transport as t_mod

    transport = t_mod.HadesLuaTransport.__new__(t_mod.HadesLuaTransport)
    transport.mailbox_mode = "mailbox"
    transport.pid = os.getpid()
    transport._real_attached_pid = None
    transport._tainted_pid = None
    transport._unsafe_vm_pid = None
    transport._cleanup_pending = False
    transport._cleanup_failure = None
    transport.focus_original = None
    transport.addresses = {}
    transport.target = types.SimpleNamespace(DeleteAllBreakpoints=lambda: None)
    transport.process = types.SimpleNamespace(
        Detach=lambda: types.SimpleNamespace(Fail=lambda: False),
        GetState=lambda: fake_lldb.eStateStopped,
    )
    transport._drain = lambda: None
    transport.alive = lambda: True
    transport._stop = lambda d: None
    transport._restore_focus = lambda: None

    class FakeMailbox:
        tainted = False
        last_profile = {"roundTripSeconds": 0.001}
        closed = False
        _pending_sequence = 7
        ack_calls = 0

        def execute(self, source, *, mutating=False):
            self._pending_sequence = 7
            return '{"heroId":"h1","ok":1}'

        def acknowledge(self):
            self.ack_calls += 1
            self._pending_sequence = None

        def poison(self):
            self.tainted = True

        def close(self):
            self.closed = True

    transport._mailbox = FakeMailbox()
    assert transport.execute('return "{}"', mutating=True) == {"heroId": "h1", "ok": 1}
    assert transport._mailbox.ack_calls == 0, "transport must defer mailbox ACK until caller validates & persists"
    assert transport.has_pending_acknowledgement and transport.pending_acknowledgement_sequence == 7
    transport.acknowledge_result()
    assert transport._mailbox.ack_calls == 1 and not transport.has_pending_acknowledgement

    # Invalid JSON and non-object JSON (e.g. '[]') poison both mailbox and transport without ACKing
    for bad_receipt in ("not json{", "[]"):
        transport._tainted_pid = None
        transport._mailbox = FakeMailbox()
        transport._mailbox.execute = lambda source, *, mutating=False, raw=bad_receipt: raw
        try:
            transport.execute('return "{}"', mutating=True)
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError(f"corrupt/non-object mailbox JSON {bad_receipt!r} was accepted")
        assert transport.tainted and transport._mailbox.tainted
        assert transport._mailbox.ack_calls == 0, f"{bad_receipt!r} ACKed before validation"

    # Default MGT_HADES_TRANSPORT stays 'lldb' until real-game A/B validation passes
    fake_debugger = types.SimpleNamespace(
        SetAsync=lambda *a: None,
        GetCommandInterpreter=lambda: types.SimpleNamespace(
            HandleCommand=lambda *a: None,
        ),
        GetListener=lambda: None,
    )
    fake_ret = types.SimpleNamespace(Succeeded=lambda: True, GetError=lambda: "")
    fake_lldb_init = types.SimpleNamespace(
        SBDebugger=types.SimpleNamespace(Initialize=lambda: None, Create=lambda: fake_debugger),
        SBCommandReturnObject=lambda: fake_ret,
        SBError=lambda: types.SimpleNamespace(Fail=lambda: False, Success=lambda: True),
        eStateStopped=5, eStateRunning=6, eStateExited=10,
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MGT_HADES_TRANSPORT", None)
        with patch.object(t_mod, "lldb", fake_lldb_init):
            assert t_mod.HadesLuaTransport().mailbox_mode == "lldb"
    with patch.dict(os.environ, {"MGT_HADES_TRANSPORT": "mailbox"}):
        with patch.object(t_mod, "lldb", fake_lldb_init):
            assert t_mod.HadesLuaTransport().mailbox_mode == "mailbox"

    # Detach with _real_attached_pid=None must NOT call os.kill (safe for fake PIDs in unit tests)
    transport._tainted_pid = None
    transport._mailbox = FakeMailbox()
    transport._mailbox._pending_sequence = None
    with patch("os.kill", side_effect=AssertionError("unexpected os.kill")):
        transport.detach()

    # Detach with _real_attached_pid == pid MUST send SIGCONT
    transport.pid = 777777
    transport._real_attached_pid = 777777
    transport.process = types.SimpleNamespace(
        Detach=lambda: types.SimpleNamespace(Fail=lambda: False),
        GetState=lambda: fake_lldb.eStateStopped,
    )
    signals = []
    with patch("os.kill", side_effect=lambda p, s: signals.append((p, s))):
        transport.detach()
    assert len(signals) == 1 and signals[0][0] == 777777

    # 7. Worker routing + generation-reset non-replay
    class MailboxWorkerTransport:
        pid = 42
        mailbox_mode = "mailbox"
        tainted = False

        def __init__(self):
            self.calls = []
            self.fail_gen_next = False

        def alive(self):
            return True

        def _extract_receipt(self, source):
            match = re.search(
                r'\\034id\\034:\\034([0-9a-f]{32})\\034,\\034method\\034:\\034([A-Za-z0-9_]+)\\034',
                source,
            )
            assert match, source[-200:]
            return match.group(1), match.group(2)

        def execute(self, source, *, mutating=False):
            self.calls.append(source)
            if self.fail_gen_next:
                self.fail_gen_next = False
                raise AdapterError("resident_generation_missing", "hades.error.runtimeNotReady", diagnostic="gen reset")
            m = re.search(r'submit_trait_command\("([0-9a-f]{32})"', source)
            if m:
                return {"id": m.group(1), "state": "complete", "mutationStarted": True, "result": {"heroId": "h1"}}
            assert not re.search(r'submit_world_command\("[0-9a-f]{32}"', source), (
                "mailbox mode must execute world commands directly"
            )
            cmd_id, cmd_method = self._extract_receipt(source)
            return {"__mgtReceipt": {"id": cmd_id, "method": cmd_method}, "result": {"heroId": "h1"}}

    reward = next(row["id"] for row in reward_catalog() if row["doorAllowed"])
    mb_transport = MailboxWorkerTransport()
    worker = HadesLLDBWorker(mb_transport)
    assert worker.dispatch("status", {})["heroId"] == "h1"
    worker.dispatch("apply_world_exit", {
        "target": {"heroId": "h1"}, "roomId": "a" * 32 + ":1:room:3",
        "doorToken": "4:5:" + reward + ":nil:6",
        "kind": "reward", "targetID": reward, "requestId": "req-1",
    })
    assert not any(
        re.search(r'submit_world_command\("[0-9a-f]{32}"', c) for c in mb_transport.calls
    )

    # Generation reset on status retries cleanly once and re-bootstraps
    mb_transport.fail_gen_next = True
    assert worker.dispatch("status", {})["heroId"] == "h1"
    assert worker._bootstrapped is not None

    # Generation reset on mutating command NEVER replays!
    calls_before = len(mb_transport.calls)
    mb_transport.fail_gen_next = True
    try:
        worker.dispatch("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
    except AdapterError as error:
        assert error.code == "runtime_not_ready" and error.presentation == "hades.error.staleTarget"
    else:
        raise AssertionError("mutating command replayed after generation reset")
    assert len(mb_transport.calls) == calls_before + 1

    # lldb fallback mode still uses deferred world command
    class FallbackTransport(MailboxWorkerTransport):
        mailbox_mode = "lldb"

        def execute(self, source, *, mutating=False):
            self.calls.append(source)
            m = re.search(r'(?:submit_world_command|submit_trait_command)\("([0-9a-f]{32})"', source)
            if m:
                return {"id": m.group(1), "state": "complete", "mutationStarted": True, "result": {"heroId": "h1"}}
            cmd_id, cmd_method = self._extract_receipt(source)
            return {"__mgtReceipt": {"id": cmd_id, "method": cmd_method}, "result": {"heroId": "h1"}}

    fb_worker = HadesLLDBWorker(FallbackTransport())
    fb_worker.dispatch("apply_world_exit", {
        "target": {"heroId": "h1"}, "roomId": "a" * 32 + ":1:room:3",
        "doorToken": "4:5:" + reward + ":nil:6",
        "kind": "reward", "targetID": reward, "requestId": "req-2",
    })
    assert any(
        re.search(r'submit_world_command\("[0-9a-f]{32}"', c) for c in fb_worker.transport.calls
    )

    # 8. End-to-end receipt confirmation, audit '[]' reproduction, identity mismatch,
    #    confirm-before-ACK ordering, lost ACK preservation, PR #896 parity, and v1/v2/v3 schema.
    class RealMailboxTransport:
        pid = 42
        mailbox_mode = "mailbox"
        _tainted_pid = None

        def __init__(self, mailbox):
            self._mailbox = mailbox

        @property
        def tainted(self):
            return self._tainted_pid is not None or self._mailbox.tainted

        @tainted.setter
        def tainted(self, value):
            self._tainted_pid = self.pid if value else None
            if value:
                self._mailbox.poison()

        @property
        def pending_acknowledgement_sequence(self):
            return getattr(self._mailbox, "_pending_sequence", None)

        @property
        def has_pending_acknowledgement(self):
            return self.pending_acknowledgement_sequence is not None

        def alive(self):
            return True

        def execute(self, source, *, mutating=False):
            text = self._mailbox.execute(source, mutating=mutating)
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError) as error:
                self._mailbox.poison()
                self.tainted = True
                raise AdapterError("outcome_unknown", "hades.error.outcomeUnknown", diagnostic=str(error)) from error
            if not isinstance(parsed, dict):
                self._mailbox.poison()
                self.tainted = True
                raise AdapterError("outcome_unknown", "hades.error.outcomeUnknown", diagnostic="non-object receipt")
            return parsed

        def acknowledge_result(self):
            try:
                self._mailbox.acknowledge()
            except BaseException:
                self.tainted = True
                raise

        def close(self):
            self._mailbox.close()

    class EndToEndWorkerSidecar:
        started = True
        terminal = False

        def __init__(self, worker, *, on_ack=None, fail_ack=None):
            self.worker = worker
            self.calls = []
            self.on_ack = on_ack
            self.fail_ack = fail_ack

        def request(self, method, params, **options):
            self.calls.append((method, params))
            if method == "acknowledge_result":
                if self.on_ack is not None:
                    self.on_ack(params)
                if self.fail_ack is not None:
                    raise self.fail_ack
            try:
                result = self.worker.dispatch(method, params)
                return {"result": result, "state": self.worker.state()}
            except Exception as error:
                return {"error": error_payload(error), "state": self.worker.state()}

        def close(self):
            self.started = False

    # 8a. Audit reproduction: real mailbox returning b"[]" yields outcome_unknown (NEVER debugger_internal)
    #     and preserves the durable recovery record without ACKing.
    with tempfile.TemporaryDirectory(prefix="hades-audit-list-") as recovery_dir:
        mb_bad = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
        mb_bad.installed_in_target()
        t_bad = run_consumer_once(SUCCESS, 0, b"[]", target_mailbox=mb_bad)
        bad_transport = RealMailboxTransport(mb_bad)
        bad_worker = HadesLLDBWorker(bad_transport)
        bad_sidecar = EndToEndWorkerSidecar(bad_worker)
        bad_journal = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        bad_client = HadesRuntimeClient(bad_sidecar, recovery=bad_journal, identity=lambda pid: "birth-A")
        bad_client.pid, bad_client.process_identity, bad_client.connected = 42, "birth-A", True
        try:
            bad_client.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("b'[]' receipt was not rejected as outcome_unknown")
        t_bad.join(timeout=2)
        assert bad_journal.path.is_file(), "b'[]' erased recovery evidence"
        assert mb_bad.tainted and mb_bad._pending_sequence == 1
        assert [m for m, _ in bad_sidecar.calls] == ["set_value"]
        try:
            bad_client.command("set_value", {"field": "money", "value": 600, "target": {"heroId": "h1"}})
        except AdapterError as error:
            assert error.code == "restart_required"
        else:
            raise AssertionError("same-lifetime follow-up ran after b'[]' receipt")
        mb_bad.close()

    # 8b. Client defense-in-depth if worker ever emits debugger_internal directly
    with tempfile.TemporaryDirectory(prefix="hades-client-internal-") as recovery_dir:
        class InternalErrorSidecar:
            started = True
            terminal = False
            calls = []

            def request(self, method, params, **options):
                self.calls.append(method)
                return {"error": {"code": "debugger_internal", "presentation": "hades.error.debuggerCall"}}

            def close(self):
                self.started = False

        journal = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        sidecar = InternalErrorSidecar()
        client = HadesRuntimeClient(sidecar, recovery=journal, identity=lambda pid: "birth-A")
        client.pid, client.process_identity, client.connected = 42, "birth-A", True
        try:
            client.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
        except AdapterError as error:
            assert error.code == "outcome_unknown"
        else:
            raise AssertionError("debugger_internal cleared recovery")
        assert journal.path.is_file() and not sidecar.started
        try:
            HadesRuntimeClient(InternalErrorSidecar(), recovery=journal, identity=lambda pid: "birth-A").connect(
                42, "/fixture/Hades"
            )
        except AdapterError as error:
            assert error.code == "restart_required"
        else:
            raise AssertionError("restarted backend bypassed debugger_internal recovery")

    # 8c. Command identity mismatch in worker: wrong __mgtReceipt.id or wrong __mgtReceipt.method
    for wrong_meta in ({"id": "0" * 32, "method": "set_value"}, {"id": None, "method": "wrong_method"}):
        with tempfile.TemporaryDirectory(prefix="hades-id-mismatch-") as recovery_dir:
            mb_id = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
            mb_id.installed_in_target()

            def wrong_worker_fn():
                req = Req()
                for _ in range(500):
                    rc = c_mod.test_claim(mb_id.address, mb_id.generation_hi, mb_id.generation_lo, ctypes.byref(req))
                    if rc == OK:
                        raw_src = ctypes.string_at(req.source, req.length).decode("utf-8")
                        found = re.search(r'\\034id\\034:\\034([0-9a-f]{32})\\034', raw_src).group(1)
                        meta = dict(wrong_meta)
                        if meta["id"] is None:
                            meta["id"] = found
                        reply = json.dumps({"__mgtReceipt": meta, "result": {"heroId": "h1"}}).encode("utf-8")
                        buf = ctypes.create_string_buffer(reply, len(reply))
                        c_mod.test_complete(
                            mb_id.address, mb_id.generation_hi, mb_id.generation_lo,
                            req.sequence, SUCCESS, 0, buf, len(reply),
                        )
                        return
                    time.sleep(0.001)

            th = threading.Thread(target=wrong_worker_fn, daemon=True)
            th.start()
            worker_id = HadesLLDBWorker(RealMailboxTransport(mb_id))
            journal_id = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
            sidecar_id = EndToEndWorkerSidecar(worker_id)
            client_id = HadesRuntimeClient(sidecar_id, recovery=journal_id, identity=lambda pid: "birth-A")
            client_id.pid, client_id.process_identity, client_id.connected = 42, "birth-A", True
            try:
                client_id.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
            except AdapterError as error:
                assert error.code == "outcome_unknown"
            else:
                raise AssertionError(f"mismatched command identity {wrong_meta!r} succeeded")
            th.join(timeout=2)
            assert journal_id.path.is_file() and mb_id.tainted and mb_id._pending_sequence == 1
            assert [m for m, _ in sidecar_id.calls] == ["set_value"]
            mb_id.close()

    # 8d. Strict confirm -> acknowledge_result -> complete ordering & unACKed command blocking
    with tempfile.TemporaryDirectory(prefix="hades-confirm-before-ack-") as recovery_dir:
        mb_ok = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
        mb_ok.installed_in_target()

        def ok_consumer():
            req = Req()
            for _ in range(500):
                rc = c_mod.test_claim(mb_ok.address, mb_ok.generation_hi, mb_ok.generation_lo, ctypes.byref(req))
                if rc == OK:
                    raw_src = ctypes.string_at(req.source, req.length).decode("utf-8")
                    found = re.search(
                        r'\\034id\\034:\\034([0-9a-f]{32})\\034,\\034method\\034:\\034([A-Za-z0-9_]+)\\034',
                        raw_src,
                    )
                    reply = json.dumps({
                        "__mgtReceipt": {"id": found.group(1), "method": found.group(2)},
                        "result": {"heroId": "h1"},
                    }).encode("utf-8")
                    buf = ctypes.create_string_buffer(reply, len(reply))
                    c_mod.test_complete(
                        mb_ok.address, mb_ok.generation_hi, mb_ok.generation_lo,
                        req.sequence, SUCCESS, 0, buf, len(reply),
                    )
                    return
                time.sleep(0.001)

        th_ok = threading.Thread(target=ok_consumer, daemon=True)
        th_ok.start()
        journal_ok = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        ack_snapshot = []

        def inspect_before_ack(_params):
            assert journal_ok.path.is_file(), "confirmed recovery was not persisted before acknowledge_result"
            ack_snapshot.append(json.loads(journal_ok.path.read_text()))
            # Worker also refuses another command before acknowledge_result finishes
            try:
                worker_ok.dispatch("status", {})
            except AdapterError as blocked:
                assert blocked.code == "restart_required"
            else:
                raise AssertionError("worker allowed another command while ACK was pending")

        worker_ok = HadesLLDBWorker(RealMailboxTransport(mb_ok))
        sidecar_ok = EndToEndWorkerSidecar(worker_ok, on_ack=inspect_before_ack)
        client_ok = HadesRuntimeClient(sidecar_ok, recovery=journal_ok, identity=lambda pid: "birth-A")
        client_ok.pid, client_ok.process_identity, client_ok.connected = 42, "birth-A", True
        out = client_ok.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
        th_ok.join(timeout=2)
        assert out["heroId"] == "h1"
        assert len(ack_snapshot) == 1
        assert ack_snapshot[0]["schemaVersion"] == 2 and ack_snapshot[0]["outcome"] == "confirmed"
        assert ack_snapshot[0]["method"] == "set_value"
        assert not journal_ok.path.exists(), "confirmed recovery record was not retired after ACK"
        assert mb_ok._pending_sequence is None and not mb_ok.tainted
        mb_ok.close()

    # 8e. Lost ACK preserves confirmed record and surfaces commandResultConnectionLost on same lifetime
    with tempfile.TemporaryDirectory(prefix="hades-lost-ack-") as recovery_dir:
        mb_lost = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
        mb_lost.installed_in_target()

        def lost_ack_consumer():
            req = Req()
            for _ in range(500):
                rc = c_mod.test_claim(mb_lost.address, mb_lost.generation_hi, mb_lost.generation_lo, ctypes.byref(req))
                if rc == OK:
                    raw_src = ctypes.string_at(req.source, req.length).decode("utf-8")
                    found = re.search(
                        r'\\034id\\034:\\034([0-9a-f]{32})\\034,\\034method\\034:\\034([A-Za-z0-9_]+)\\034',
                        raw_src,
                    )
                    reply = json.dumps({
                        "__mgtReceipt": {"id": found.group(1), "method": found.group(2)},
                        "result": {"heroId": "h1"},
                    }).encode("utf-8")
                    buf = ctypes.create_string_buffer(reply, len(reply))
                    c_mod.test_complete(
                        mb_lost.address, mb_lost.generation_hi, mb_lost.generation_lo,
                        req.sequence, SUCCESS, 0, buf, len(reply),
                    )
                    return
                time.sleep(0.001)

        th_lost = threading.Thread(target=lost_ack_consumer, daemon=True)
        th_lost.start()
        journal_lost = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        worker_lost = HadesLLDBWorker(RealMailboxTransport(mb_lost))
        sidecar_lost = EndToEndWorkerSidecar(worker_lost, fail_ack=OSError("lost ack IPC"))
        client_lost = HadesRuntimeClient(sidecar_lost, recovery=journal_lost, identity=lambda pid: "birth-A")
        client_lost.pid, client_lost.process_identity, client_lost.connected = 42, "birth-A", True
        try:
            client_lost.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
        except AdapterError as error:
            assert error.code == "restart_required"
            assert error.presentation == "hades.error.commandResultConnectionLost"
        else:
            raise AssertionError("lost ACK was ignored")
        th_lost.join(timeout=2)
        persisted = json.loads(journal_lost.path.read_text())
        assert persisted["schemaVersion"] == 2 and persisted["outcome"] == "confirmed"
        restarted_lost = HadesRuntimeClient(EndToEndWorkerSidecar(worker_lost), recovery=journal_lost, identity=lambda pid: "birth-A")
        try:
            restarted_lost.connect(42, "/fixture/Hades")
        except AdapterError as error:
            assert error.code == "restart_required"
            assert error.presentation == "hades.error.commandResultConnectionLost"
        else:
            raise AssertionError("restarted backend bypassed confirmed recovery record")
        # Retires cleanly on new game lifetime
        assert HadesRuntimeClient(
            types.SimpleNamespace(
                started=True, terminal=False,
                request=lambda m, p, **kw: {"result": {"connected": True, "pid": 42}},
                close=lambda: None,
            ),
            recovery=journal_lost, identity=lambda pid: "birth-B",
        ).connect(42, "/fixture/Hades")["connected"]
        assert not journal_lost.path.exists()
        mb_lost.close()

    # 8f. PR #896 parity: post-execution recovery read failure keeps outcome='unknown' and skips ACK
    with tempfile.TemporaryDirectory(prefix="hades-pr896-") as recovery_dir:
        mb_read = HadesCommandMailbox(shared_lib, os.getpid(), alive=lambda: True)
        mb_read.installed_in_target()

        def pr896_consumer():
            req = Req()
            for _ in range(500):
                rc = c_mod.test_claim(mb_read.address, mb_read.generation_hi, mb_read.generation_lo, ctypes.byref(req))
                if rc == OK:
                    raw_src = ctypes.string_at(req.source, req.length).decode("utf-8")
                    found = re.search(
                        r'\\034id\\034:\\034([0-9a-f]{32})\\034,\\034method\\034:\\034([A-Za-z0-9_]+)\\034',
                        raw_src,
                    )
                    reply = json.dumps({
                        "__mgtReceipt": {"id": found.group(1), "method": found.group(2)},
                        "result": {"heroId": "h1"},
                    }).encode("utf-8")
                    buf = ctypes.create_string_buffer(reply, len(reply))
                    c_mod.test_complete(
                        mb_read.address, mb_read.generation_hi, mb_read.generation_lo,
                        req.sequence, SUCCESS, 0, buf, len(reply),
                    )
                    return
                time.sleep(0.001)

        th_read = threading.Thread(target=pr896_consumer, daemon=True)
        th_read.start()
        journal_read = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        worker_read = HadesLLDBWorker(RealMailboxTransport(mb_read))
        sidecar_read = EndToEndWorkerSidecar(worker_read)
        client_read = HadesRuntimeClient(sidecar_read, recovery=journal_read, identity=lambda pid: "birth-A")
        client_read.pid, client_read.process_identity, client_read.connected = 42, "birth-A", True
        orig_read_text = Path.read_text
        injected = [False]

        def fail_post_exec_read(path, *args, **kwargs):
            if path == journal_read.path and mb_read._pending_sequence is not None and not injected[0]:
                injected[0] = True
                raise OSError("transient read failure after execution")
            return orig_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", fail_post_exec_read):
            try:
                client_read.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
            except AdapterError as error:
                assert error.code == "outcome_unknown"
            else:
                raise AssertionError("post-execution read failure cleared recovery")
        th_read.join(timeout=2)
        assert injected[0] and mb_read._pending_sequence == 1
        assert [m for m, _ in sidecar_read.calls] == ["set_value"]
        assert json.loads(journal_read.path.read_text()) == {"pid": 42, "identity": "birth-A", "method": "set_value"}
        mb_read.close()

    # 8g. Recovery journal v1 -> v2 read compatibility & v3 refusal without overwriting
    with tempfile.TemporaryDirectory(prefix="hades-recovery-schema-") as recovery_dir:
        path_v1 = Path(recovery_dir) / "v1.json"
        path_v1.write_text(json.dumps({"pid": 42, "identity": "birth-A", "method": "set_value"}), encoding="utf-8")
        desc_v1 = HadesRecoveryJournal(path_v1).describe()
        assert desc_v1 == {"method": "set_value", "requestId": None, "outcome": "unknown", "receipt": None, "pid": 42}

        path_v3 = Path(recovery_dir) / "v3.json"
        raw_v3 = json.dumps({
            "schemaVersion": 3, "pid": 42, "identity": "birth-A",
            "method": "set_value", "outcome": "unknown", "receipt": None,
        })
        path_v3.write_text(raw_v3, encoding="utf-8")
        j_v3 = HadesRecoveryJournal(path_v3)
        try:
            j_v3.guard(43, "birth-B")
        except AdapterError as error:
            assert error.code == "recovery_failed"
        else:
            raise AssertionError("newer schemaVersion recovery file was accepted/overwritten")
        assert path_v3.read_text(encoding="utf-8") == raw_v3

    # 8h. _execute_lldb invalid / non-object JSON rejects as outcomeUnknown without double prefix
    lldb_err = types.SimpleNamespace(Fail=lambda: False, Success=lambda: True)

    def make_expr_opts():
        return types.SimpleNamespace(
            SetLanguage=lambda *a: None,
            SetTimeoutInMicroSeconds=lambda *a: None,
            SetIgnoreBreakpoints=lambda *a: None,
            SetUnwindOnError=lambda *a: None,
            SetStopOthers=lambda *a: None,
            SetTryAllThreads=lambda *a: None,
        )

    lldb_stub = types.SimpleNamespace(
        SBError=lambda: lldb_err,
        SBExpressionOptions=make_expr_opts,
        eLanguageTypeC_plus_plus=4,
        ePermissionsReadable=1,
        ePermissionsWritable=2,
        eStateStopped=5,
        eStateRunning=6,
        eStateExited=10,
    )
    for bad_lldb_json in ("not json{", "[]"):
        lldb_transport = t_mod.HadesLuaTransport.__new__(t_mod.HadesLuaTransport)
        lldb_transport.pid = 42
        lldb_transport._tainted_pid = None
        lldb_transport._unsafe_vm_pid = None
        lldb_transport._cleanup_pending = False
        lldb_transport._cleanup_failure = None
        lldb_transport._mailbox = None
        lldb_transport.focus_original = None
        lldb_transport.addresses = {
            name: idx + 100
            for idx, name in enumerate(("lua_gettop", "luaL_loadbufferx", "lua_pcallk", "lua_tolstring", "lua_settop"))
        }
        eval_result = types.SimpleNamespace(GetError=lambda: lldb_err, GetValueAsSigned=lambda: 0)
        frame = types.SimpleNamespace(EvaluateExpression=lambda expr, opts: eval_result)
        thread = types.SimpleNamespace(GetFrameAtIndex=lambda i: frame)
        lldb_transport._boundary = lambda: (thread, 0x1000)
        lldb_transport.alive = lambda: True
        lldb_transport._stop = lambda d: None
        lldb_transport._restore_focus = lambda: None
        lldb_transport._resume = lambda d: None
        lldb_transport.target = types.SimpleNamespace(DeleteAllBreakpoints=lambda: None)
        lldb_transport.process = types.SimpleNamespace(
            AllocateMemory=lambda size, perm, err: 0x2000,
            WriteMemory=lambda addr, data, err: len(data),
            DeallocateMemory=lambda addr: None,
            ReadCStringFromMemory=lambda addr, cap, err, reply=bad_lldb_json: reply,
        )
        with patch.object(t_mod, "lldb", lldb_stub):
            try:
                lldb_transport._execute_lldb('return "{}"', mutating=True)
            except AdapterError as error:
                assert error.code == "outcome_unknown"
                assert error.presentation == "hades.error.outcomeUnknown", error.presentation
            else:
                raise AssertionError(f"bad LLDB JSON {bad_lldb_json!r} was accepted")
        assert lldb_transport.tainted

    # 8i. Client rejects malformed non-dict worker state on error replies and preserves recovery
    with tempfile.TemporaryDirectory(prefix="hades-client-bad-state-") as recovery_dir:
        class BadStateSidecar:
            started = True
            terminal = False

            def request(self, method, params, **options):
                return {
                    "error": {"code": "runtime_not_ready", "presentation": "hades.error.runtimeNotReady"},
                    "state": "malformed",
                }

            def close(self):
                self.started = False

        bad_state_journal = HadesRecoveryJournal(Path(recovery_dir) / "runtime-request.json")
        bad_state_sidecar = BadStateSidecar()
        bad_state_client = HadesRuntimeClient(bad_state_sidecar, recovery=bad_state_journal, identity=lambda pid: "birth-A")
        bad_state_client.pid, bad_state_client.process_identity, bad_state_client.connected = 42, "birth-A", True
        try:
            bad_state_client.command("set_value", {"field": "money", "value": 500, "target": {"heroId": "h1"}})
        except AdapterError as error:
            assert error.code == "debugger_protocol"
        else:
            raise AssertionError("non-dict state on error reply was accepted")
        assert not bad_state_client.connected and not bad_state_sidecar.started and bad_state_journal.path.is_file()

print("hades_mailbox_client_ok")
