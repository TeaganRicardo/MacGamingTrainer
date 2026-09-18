from pathlib import Path
import json
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService, _normalize_shortcuts

assert PROFILE_SCHEMA_VERSION == 4

def chord(code, modifiers, label):
    return {'keyCode':code, 'modifiers':modifiers, 'keyLabel':label}

# Empty/invalid shortcut patches remain empty and current schema accepts chord
# objects only. Legacy integer digit layouts are deliberately not Profile-compatible.
assert _normalize_shortcuts(None) == {}
assert _normalize_shortcuts({}) == {}
assert _normalize_shortcuts({'godMode': 1, 'disableAll': 0}) == {}
assert _normalize_shortcuts({'unknown': chord(18,6144,'1')}) == {}

valid = {
    'godMode': chord(18,6144,'1'),
    'infiniteHealth': chord(19,6144,'2'),
    'gardenQoL': chord(5,6144,'G'),
}
assert _normalize_shortcuts(valid) == valid
