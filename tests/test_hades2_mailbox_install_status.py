"""Pin native mailbox installer status values to Python recovery semantics."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2.native_mailbox import (
    INSTALL_FAILURE,
    INSTALL_RESTART_REQUIRED,
    INSTALL_SUCCESS,
    _check_install_status,
    _raise_install_unreturned,
)

compiler = shutil.which("cc")
assert compiler, "A C compiler is required for the native mailbox ABI contract"

with tempfile.TemporaryDirectory(prefix="mgt-mailbox-install-status-") as temporary:
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
        "-I", str(ROOT / "Backend/games/hades2/native"), str(source), "-o", str(executable),
    ], check=True)
    native_values = tuple(map(int, subprocess.check_output([str(executable)], text=True).split()))
    assert native_values == (INSTALL_SUCCESS, INSTALL_FAILURE, INSTALL_RESTART_REQUIRED), native_values


class Mailbox:
    def __init__(self):
        self.poison_calls = 0

    def poison(self):
        self.poison_calls += 1


class Transport:
    tainted = False


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

unknown_mailbox = Mailbox()
unknown_transport = Transport()
try:
    _raise_install_unreturned("expression timeout", unknown_mailbox, unknown_transport)
except AdapterError as error:
    assert error.code == "restart_required"
    assert "expression timeout" in error.diagnostic
else:
    raise AssertionError("an installer expression without a result was accepted")
assert unknown_mailbox.poison_calls == 1 and unknown_transport.tainted

print("hades2_mailbox_install_status_contract_ok")
