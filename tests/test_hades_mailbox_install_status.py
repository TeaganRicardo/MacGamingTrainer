"""Pin Hades I native installer statuses, Mach-O Fat slice UUID parsing, and VM interrupt handling."""
import shutil
import struct
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades.native_mailbox import (
    CPU_TYPE_ARM64,
    CPU_TYPE_X86_64,
    CommandMailboxLibrary,
    FAT_MAGIC,
    INSTALL_FAILURE,
    INSTALL_RESTART_REQUIRED,
    INSTALL_SUCCESS,
    LC_UUID,
    MH_DYLIB,
    MH_MAGIC_64,
    _check_install_status,
    _raise_install_unreturned,
    install_command_mailbox,
    slice_uuid,
)

compiler = shutil.which("cc")
assert compiler, "A C compiler is required for the Hades native mailbox ABI contract"

with tempfile.TemporaryDirectory(prefix="mgt-hades-mailbox-install-") as temporary:
    source = Path(temporary) / "install_status.c"
    executable = Path(temporary) / "install_status"
    source.write_text(
        '#include <stdio.h>\n'
        '#include "MailboxProtocol.h"\n'
        'int main(void) {\n'
        '  printf("%d %d %d\\n", MGT_MAILBOX_INSTALL_SUCCESS, '
        'MGT_MAILBOX_INSTALL_FAILURE, MGT_MAILBOX_INSTALL_RESTART_REQUIRED);\n'
        '  return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-D_POSIX_C_SOURCE=200809L",
        "-I", str(ROOT / "Backend/games/hades/native"), str(source), "-o", str(executable),
    ], check=True)
    native_values = tuple(map(int, subprocess.check_output([str(executable)], text=True).split()))
    assert native_values == (INSTALL_SUCCESS, INSTALL_FAILURE, INSTALL_RESTART_REQUIRED), native_values


def synthetic_dylib(cputype, uuid_bytes, filetype=MH_DYLIB):
    lc_uuid = struct.pack("<II16s", LC_UUID, 24, uuid_bytes)
    header = struct.pack("<8I", MH_MAGIC_64, cputype, 0, filetype, 1, len(lc_uuid), 0, 0)
    return header + lc_uuid


arm_uuid = bytes.fromhex("11" * 16)
x86_uuid = bytes.fromhex("22" * 16)
with tempfile.TemporaryDirectory(prefix="mgt-hades-macho-") as temporary:
    tmp = Path(temporary)
    thin = tmp / "thin.dylib"
    thin.write_bytes(synthetic_dylib(CPU_TYPE_X86_64, x86_uuid))
    assert slice_uuid(thin, target_cputype=CPU_TYPE_X86_64) == "22" * 16

    arm_slice = synthetic_dylib(CPU_TYPE_ARM64, arm_uuid)
    x86_slice = synthetic_dylib(CPU_TYPE_X86_64, x86_uuid)
    fat_header = struct.pack(">II", FAT_MAGIC, 2)
    off1 = 8 + 40
    off2 = off1 + len(arm_slice)
    fat = fat_header + struct.pack(">5I", CPU_TYPE_ARM64, 0, off1, len(arm_slice), 0) + struct.pack(
        ">5I", CPU_TYPE_X86_64, 0, off2, len(x86_slice), 0
    ) + arm_slice + x86_slice
    universal = tmp / "universal.dylib"
    universal.write_bytes(fat)
    assert slice_uuid(universal, target_cputype=CPU_TYPE_X86_64) == "22" * 16
    assert slice_uuid(universal, target_cputype=CPU_TYPE_ARM64) == "11" * 16

    wrong_type = tmp / "exec.macho"
    wrong_type.write_bytes(synthetic_dylib(CPU_TYPE_X86_64, x86_uuid, filetype=2))
    for bad in (wrong_type, tmp / "only_arm.dylib"):
        if not bad.exists():
            bad.write_bytes(arm_slice)
        try:
            slice_uuid(bad, target_cputype=CPU_TYPE_X86_64)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe Mach-O accepted: {bad}")


class Mailbox:
    def __init__(self):
        self.poison_calls = 0
        self.installed = False

    def poison(self):
        self.poison_calls += 1

    def installed_in_target(self):
        self.installed = True


class Transport:
    pid = 99
    tainted = False
    _unsafe_vm_pid = None


success_mailbox = Mailbox()
success_transport = Transport()
assert _check_install_status(INSTALL_SUCCESS, "", success_mailbox, success_transport) is None
assert success_mailbox.poison_calls == 0 and not success_transport.tainted

for status, code, should_poison in (
    (INSTALL_RESTART_REQUIRED, "restart_required", True),
    (INSTALL_FAILURE, "incompatible", False),
):
    mailbox = Mailbox()
    transport = Transport()
    try:
        _check_install_status(status, "fixture diagnostic", mailbox, transport)
    except AdapterError as error:
        assert error.code == code, (status, error.code)
        assert "fixture diagnostic" in error.diagnostic
    else:
        raise AssertionError(f"installer status {status} was accepted")
    assert mailbox.poison_calls == int(should_poison), (status, mailbox.poison_calls)
    assert transport.tainted is should_poison, (status, transport.tainted)

for phase_bytes, read_failed, expected_code, expected_pres, expect_unsafe in (
    (b"\x01", False, "outcome_unknown", "hades.error.luaInterrupted", True),
    (b"\x00", True, "outcome_unknown", "hades.error.luaInterrupted", True),
    (b"\x00", False, "restart_required", "hades.error.restartRequired", False),
    (b"\x02", False, "restart_required", "hades.error.restartRequired", False),
):
    mailbox = Mailbox()
    transport = Transport()
    try:
        _raise_install_unreturned(
            "expression timeout", mailbox, transport,
            phase_bytes=phase_bytes, phase_read_failed=read_failed,
        )
    except AdapterError as error:
        assert error.code == expected_code and error.presentation == expected_pres
    else:
        raise AssertionError("unreturned installer expression was accepted")
    assert mailbox.poison_calls == 1 and transport.tainted
    assert (transport._unsafe_vm_pid == transport.pid) is expect_unsafe


class FakeError:
    def __init__(self, failed=False, message=""):
        self._failed = failed
        self._message = message

    def Fail(self):
        return self._failed

    def __str__(self):
        return self._message


class Options:
    def __getattr__(self, name):
        return lambda *args: None


fake_lldb = types.SimpleNamespace(
    SBError=lambda: FakeError(False),
    SBExpressionOptions=Options,
    eLanguageTypeC_plus_plus=4,
    ePermissionsReadable=1,
    ePermissionsWritable=2,
)


def make_installer_transport(*, eval_fails=False, phase_byte=b"\x01"):
    events = []
    alive_flag = [True]

    class FakeTransport:
        pid = 4242
        tainted = False
        cleanup_pending = False
        _unsafe_vm_pid = None
        _boundary_initial_stop_pending = False

        @property
        def vm_interrupted(self):
            return self._unsafe_vm_pid == self.pid

        def alive(self):
            return alive_flag[0]

        def _boundary(self, *, entry_address=None, touch_focus=True):
            events.append(("boundary", entry_address, touch_focus))
            frame = types.SimpleNamespace(
                EvaluateExpression=lambda *args: types.SimpleNamespace(
                    GetError=lambda: FakeError(eval_fails, "interrupted" if eval_fails else ""),
                    GetValueAsSigned=lambda: INSTALL_SUCCESS,
                )
            )
            return types.SimpleNamespace(GetFrameAtIndex=lambda i: frame), 0xBEEF

        def _stop(self, deadline):
            events.append("stop")

        def _restore_focus(self):
            events.append("restore_focus")

        def _resume(self, deadline):
            events.append("resume")

        def _terminate_interrupted_process(self):
            events.append("kill")
            alive_flag[0] = False

    t = FakeTransport()
    t.target = types.SimpleNamespace(DeleteAllBreakpoints=lambda: events.append("delete_bp"))
    t.process = types.SimpleNamespace(
        AllocateMemory=lambda size, perms, err: 0x10000,
        WriteMemory=lambda addr, data, err: len(data),
        ReadMemory=lambda addr, n, err: phase_byte,
        ReadCStringFromMemory=lambda addr, cap, err: "",
        DeallocateMemory=lambda addr: events.append("free"),
    )
    return t, events


lib = CommandMailboxLibrary(Path("/tmp/libMGTHadesCommandMailbox.dylib"), 0x200000, 0x300000, 0x2c4b91)

t_ok, ev_ok = make_installer_transport(eval_fails=False)
mb_ok = types.SimpleNamespace(path=Path("/tmp/slot"), generation_hi=1, generation_lo=2,
                              poison=lambda: None, installed_in_target=lambda: ev_ok.append("installed"))
install_command_mailbox(t_ok, fake_lldb, mb_ok, lib)
assert ev_ok == [
    ("boundary", 0x2c4b91, False),
    "installed",
    "stop",
    "delete_bp",
    "restore_focus",
    "free",
    "resume",
], ev_ok

t_int, ev_int = make_installer_transport(eval_fails=True, phase_byte=b"\x01")
mb_int = types.SimpleNamespace(path=Path("/tmp/slot"), generation_hi=1, generation_lo=2,
                               poison=lambda: ev_int.append("poison"), installed_in_target=lambda: None)
try:
    install_command_mailbox(t_int, fake_lldb, mb_int, lib)
except AdapterError as error:
    assert error.code == "outcome_unknown" and error.presentation == "hades.error.luaInterrupted"
else:
    raise AssertionError("interrupted install with phase=1 succeeded")
assert t_int.vm_interrupted and ev_int == [("boundary", 0x2c4b91, False), "poison", "kill"], ev_int

print("hades_mailbox_install_status_contract_ok")
