import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()

# Connect must allow the empirically slow LLDB attach/bootstrap path. A prior
# 12 s watchdog killed healthy connections and left the UI in detached/deferred
# state (green desired switches, no live catalog).
assert re.search(r'case \.connect(?:\(_\))?:\s*(?:.|\n)*?return 90\.0', api)
assert re.search(r'case \.scan:\s*(?:.|\n)*?return 15\.0', api)
assert re.search(r'case \.status:\s*(?:.|\n)*?return 15\.0', api)
assert re.search(r'case \.disconnect:\s*(?:.|\n)*?return 12\.0', api)

# Guard against re-introducing the coupled 12 s connect/disconnect case.
assert 'case .connect, .disconnect' not in api

print('hades2_timeout_policy_v0177_ok')
