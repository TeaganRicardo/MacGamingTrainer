"""Damage has one durable intent: the multiplier, never the retired toggle.

`damageEnabled` survives only as a derived projection for older Profiles, the
resident feature list and the public status payload. A write to either half of
the pair must reach the resident as one multiplier write, and the stored
projection must never veto an explicit multiplier write.
"""

import json
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'Backend'))
sys.path.insert(0, str(root / 'tests'))

from games.hades2 import preparation as prep
from games.hades2.adapter import Hades2Adapter
from games.hades2.preferences import DESIRED_STATE_SCHEMA_VERSION

base = Path(tempfile.mkdtemp(prefix='mgt-hades2-damage-intent-'))
prep.DATA = base
prep.GAME = base / 'Hades II.app'
prep.SAVES = base / 'Saves'
prep.official_display_names = lambda ids, language='zh-CN': {}


class FakeTransport:
    def __init__(self):
        self.pid = None
        self.live = False
        self.last_duration = 0

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.pid = None
        self.live = False

    def close(self):
        self.live = False


adapter = Hades2Adapter(transport=FakeTransport())
adapter.runtime.attach(4242)
adapter.state['capabilities'] = {'setFeature': True}

calls = []


def recording_execute(command, params):
    calls.append((command, dict(params)))
    return {'status': 'ready', 'capabilities': {'setFeature': True}, 'desiredFeatures': {}}


adapter.execute = recording_execute


def write(feature, value):
    calls.clear()
    adapter.set_desired(feature, value)
    assert len(calls) == 1, calls
    command, params = calls[0]
    assert command == 'set_feature', calls
    # One durable intent: the resident only ever receives the multiplier.
    assert params['feature'] == 'damageMultiplier', calls
    return params['value']


def assert_pair(multiplier):
    assert adapter.preferences['damageMultiplier'] == multiplier
    assert adapter.preferences['damageEnabled'] is (multiplier != 1)


assert adapter.preferences['damageMultiplier'] == 1.0

# A legacy toggle write is translated into the authoritative multiplier; 1x is
# defined as normal damage, so enabling restores the historical 2x default.
assert write('damageEnabled', True) == 2.0
assert_pair(2.0)
assert write('damageEnabled', False) == 1.0
assert_pair(1.0)

# The derived projection must not veto an explicit multiplier write: after the
# toggle above left `damageEnabled` false, a 3x write still means 3x.
assert write('damageMultiplier', 3.0) == 3.0
assert_pair(3.0)
assert write('damageMultiplier', 1.0) == 1.0
assert_pair(1.0)

# The durable document is written from the same canonical pair.
document = json.loads(Path(adapter.preference_store.path).read_text(encoding='utf-8'))
assert document['schemaVersion'] == DESIRED_STATE_SCHEMA_VERSION
assert document['damageMultiplier'] == 1.0
assert document['damageEnabled'] is False

write('damageMultiplier', 5.0)
document = json.loads(Path(adapter.preference_store.path).read_text(encoding='utf-8'))
assert document['damageMultiplier'] == 5.0
assert document['damageEnabled'] is True

print('hades2_damage_intent_boundary_ok')
