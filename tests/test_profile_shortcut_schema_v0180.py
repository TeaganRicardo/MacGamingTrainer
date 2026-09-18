from pathlib import Path
import json
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2.profile_service import PROFILE_SCHEMA_VERSION, Hades2ProfileService, _normalize_shortcuts

DEFAULTS = {
    'godMode': 1,
    'infiniteHealth': 2,
    'infiniteMana': 3,
    'instantCastCooldown': 4,
    'hexAlwaysReady': 5,
    'infiniteAmmo': 6,
    'damageEnabled': 7,
    'autoMiniGames': 8,
    'moneyMultiplierEnabled': 9,
    'disableAll': 0,
}

# Empty/invalid shortcut patches do not reset the user's current local mapping.
assert _normalize_shortcuts(None) == {}
assert _normalize_shortcuts({}) == {}
assert _normalize_shortcuts({'unknown': 1, 'godMode': True, 'disableAll': 11}) == {}

# A valid custom swap remains exactly intact.
swapped = dict(DEFAULTS, godMode=2, infiniteHealth=1)
assert _normalize_shortcuts(swapped) == swapped

# Duplicate imported digits are normalized deterministically using the same
# swap rule as the UI editor.  The resulting profile is always a bijection over
# 0...9 rather than leaving Carbon registration order to decide the winner.
duplicated = {'godMode': 2, 'infiniteHealth': 2, 'disableAll': 9}
normalized = _normalize_shortcuts(duplicated)
assert normalized == {
    'godMode': 1,
    'infiniteHealth': 2,
    'infiniteMana': 3,
    'instantCastCooldown': 4,
    'hexAlwaysReady': 5,
    'infiniteAmmo': 6,
    'damageEnabled': 7,
    'autoMiniGames': 8,
    'moneyMultiplierEnabled': 0,
    'disableAll': 9,
}
assert sorted(normalized.values()) == list(range(10))

# Missing actions in a shortcut-bearing profile are filled from the current
# layout while preserving requested assignments by swapping occupants.
partial = _normalize_shortcuts({'godMode': 0})
assert partial['godMode'] == 0 and partial['disableAll'] == 1
assert sorted(partial.values()) == list(range(10))

base = Path(tempfile.mkdtemp(prefix='mgt-profile-shortcuts-v0180-'))
service = Hades2ProfileService(base/'profiles')
desired = {'godMode': False}
service.save('conflict', desired, duplicated)
path = service.path('conflict')
on_disk = json.loads(path.read_text(encoding='utf-8'))
assert on_disk['shortcuts'] == normalized
assert service.load('conflict')['shortcuts'] == normalized
assert service.list()[0]['shortcuts'] == normalized

# A current profile with no shortcuts key remains an empty shortcut patch.
no_shortcuts_path = service.path('no-shortcuts')
no_shortcuts_path.write_text(json.dumps({
    'schemaVersion': PROFILE_SCHEMA_VERSION, 'name':'no-shortcuts',
    'updatedAt':'2026-09-18T00:00:00+0000', 'desired':desired,
}), encoding='utf-8')
assert service.load('no-shortcuts')['shortcuts'] == {}

print('profile_shortcut_schema_v0180_ok')
