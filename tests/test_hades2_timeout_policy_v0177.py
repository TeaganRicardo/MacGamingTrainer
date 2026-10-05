import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.command_contract import command_metadata

timeouts = {
    row["name"]: float(row["timeoutSeconds"])
    for row in command_metadata()
}

# Connect must allow the empirically slow LLDB attach/bootstrap path. A prior
# 12 s watchdog killed healthy connections and left the UI detached/deferred.
assert timeouts["connect"] == 90.0
assert timeouts["scan"] == 15.0
assert timeouts["status"] == 15.0
assert timeouts["disconnect"] == 12.0
assert timeouts["connect"] != timeouts["disconnect"]

print("hades2_timeout_policy_v0177_ok")
