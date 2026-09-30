from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
adapter = (ROOT / "Backend/games/hades2/adapter.py").read_text(encoding="utf-8")

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

# The module boundary must translate that bootstrap marker into the existing
# stable restart_required machine state plus Hades-owned presentation, rather
# than leaking a raw Lua exception as canonical UI.
assert "def _resident_cleanup_failed(" in adapter
assert "hades2.error.residentCleanupFailed" in adapter
assert "restart_required" in adapter

print("hades2_resident_replacement_cleanup_ok")
