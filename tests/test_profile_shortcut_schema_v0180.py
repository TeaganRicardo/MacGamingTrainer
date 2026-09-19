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
future = {'futureFeature': chord(18,6144,'1')}
assert _normalize_shortcuts(future) == future
assert _normalize_shortcuts({'bad action': chord(18,6144,'1')}) == {}
assert _normalize_shortcuts({'../escape': chord(18,6144,'1')}) == {}

valid = {
    'godMode': chord(18,6144,'1'),
    'infiniteHealth': chord(19,6144,'2'),
    'gardenQoL': chord(5,6144,'G'),
}
assert _normalize_shortcuts(valid) == valid


# Duplicate chords are deterministic even for forward-compatible action IDs.
duplicated = {
    'godMode': chord(18, 6144, '1'),
    'infiniteHealth': chord(18, 6144, '1'),
    'disableAll': chord(29, 6144, '0'),
}
assert _normalize_shortcuts(duplicated) == {
    'godMode': chord(18, 6144, '1'),
    'disableAll': chord(29, 6144, '0'),
}

# Chord envelope is deliberately strict. Legacy integers, unknown modifier
# bits, booleans masquerading as ints, control characters and out-of-range
# values are not persisted.
invalid = {
    'godMode': {'keyCode': True, 'modifiers': 6144, 'keyLabel': '1'},
    'infiniteHealth': {'keyCode': 19, 'modifiers': -1, 'keyLabel': '2'},
    'forceDuo': {'keyCode': 8, 'modifiers': 1, 'keyLabel': 'C'},
    'infiniteMana': {'keyCode': 20, 'modifiers': 6144, 'keyLabel': '\n'},
    'instantCastCooldown': {'keyCode': 70000, 'modifiers': 6144, 'keyLabel': '4'},
    'hexAlwaysReady': {'keyCode': 23, 'modifiers': 6144, 'keyLabel': '5', 'extra': 1},
}
assert _normalize_shortcuts(invalid) == {}

base = Path(tempfile.mkdtemp(prefix='mgt-profile-shortcuts-v4-'))
service = Hades2ProfileService(base/'profiles')
desired = {'godMode': False}
service.save('chords', desired, valid)
on_disk = json.loads(service.path('chords').read_text(encoding='utf-8'))
assert on_disk['schemaVersion'] == 4
assert on_disk['shortcuts'] == valid
assert service.load('chords')['shortcuts'] == valid
assert service.list() == [{'name':'chords','updatedAt':on_disk['updatedAt'],'shortcuts':valid}]

# Current Profiles may omit shortcuts entirely; loading such a profile is an
# empty shortcut patch and must not reset the user's local layout.
path = service.path('no-shortcuts')
path.write_text(json.dumps({
    'schemaVersion': 4,
    'name': 'no-shortcuts',
    'updatedAt': '2026-09-18T00:00:00+0000',
    'desired': desired,
}), encoding='utf-8')
assert service.load('no-shortcuts')['shortcuts'] == {}

print('profile_shortcut_schema_v0180_ok')

# Backend persistence must not mirror Swift's action enum; future shortcut actions
# should not require a second manual allowlist update.
assert '_SHORTCUT_ACTIONS = (' not in (root/'Backend/games/hades2/profile_service.py').read_text()
