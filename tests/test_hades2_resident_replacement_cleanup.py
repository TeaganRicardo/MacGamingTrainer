import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2.resident_session import Hades2ResidentSession

lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
prefix = lua[:lua.index("if __MacGamingTrainerV1 == nil then")]

# Replacing a resident is a transaction over hook ownership. If old cleanup
# throws, the only ownership reference must survive and the new revision must
# not be installed over indeterminate hooks.
assert 'pcall(previousModule.dispatch, "cleanup")' in prefix, (
    "previous resident cleanup is still an unguarded call"
)
assert "local cleanupOk" in prefix and "if not cleanupOk then" in prefix
failure_at = prefix.index("if not cleanupOk then")
clear_at = prefix.index("__MacGamingTrainerV1 = nil")
assert failure_at < clear_at, "old ownership is cleared before cleanup failure is rejected"
assert "MGT_RESIDENT_RESTART_REQUIRED" in prefix, (
    "cleanup failure has no stable restart-required marker"
)


# The resident-session boundary owns translation of the bootstrap marker into
# the stable restart_required machine state. Callers do not know the marker or
# the private translation helper.
class CleanupFailureTransport:
    pid = 4242
    last_duration = 0.001
    last_expression_duration = 0.0
    tainted = False

    def alive(self):
        return True

    def execute(self, source):
        raise AdapterError(
            "lua_error",
            "MGT_RESIDENT_RESTART_REQUIRED: previous resident cleanup failed",
        )


session = Hades2ResidentSession(CleanupFailureTransport(), bootstrap="")
try:
    session.status()
except AdapterError as error:
    assert error.code == "restart_required"
    assert error.presentation == "hades2.error.residentCleanupFailed"
    assert "MGT_RESIDENT_RESTART_REQUIRED" in (error.diagnostic or "")
else:
    raise AssertionError("resident replacement cleanup failure was not translated")

print("hades2_resident_replacement_cleanup_ok")
