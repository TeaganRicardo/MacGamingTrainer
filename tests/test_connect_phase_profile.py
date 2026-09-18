from io import StringIO
from pathlib import Path
import json
import logging
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import adapter as adapter_module
from games.hades2 import preparation

base = Path(tempfile.mkdtemp(prefix='mgt-connect-profile-'))
preparation.DATA = base
adapter_module.localize_catalog = lambda payload: payload


class FakeTransport:
    def __init__(self):
        self.pid = None
        self.live = False
        self.last_duration = 0.321
        self.last_attach_profile = {
            'createTarget': 0.010,
            'attachProcess': 0.100,
            'identity': 0.020,
            'symbols': 0.030,
            'resume': 0.040,
            'total': 0.200,
        }

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def execute(self, source):
        return json.dumps({
            'status': 'ready',
            'scene': 'run',
            'capabilities': {},
            'desiredFeatures': {},
            'activeFeatures': {},
            'resources': [],
            'rewards': [],
            'stats': {},
            'elements': [],
        })

    def detach(self):
        self.pid = None
        self.live = False

    def close(self):
        self.detach()


transport = FakeTransport()
adapter = adapter_module.Hades2Adapter(transport=transport)
adapter.preference_initialized = True
adapter.preference_dirty = False

assert adapter._last_status_boundary_duration == 0.0
assert adapter._last_status_json_duration == 0.0
assert adapter._last_status_localize_duration == 0.0


def fake_scan():
    adapter.state['pid'] = 4242
    adapter.state['status'] = 'disconnected'
    return dict(adapter.state)


adapter.scan = fake_scan

stream = StringIO()
handler = logging.StreamHandler(stream)
root_logger = logging.getLogger()
old_level = root_logger.level
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)
try:
    result = adapter.connect()
finally:
    root_logger.removeHandler(handler)
    root_logger.setLevel(old_level)

assert result['status'] == 'ready'
assert result['scene'] == 'run'
assert adapter._last_status_boundary_duration == 0.321
assert adapter._last_status_json_duration >= 0
assert adapter._last_status_localize_duration >= 0

log = stream.getvalue()
assert 'ConnectProfile outcome=ok' in log
for field in (
    'total=', 'scan=', 'attachTotal=', 'createTarget=0.010s',
    'attachProcess=0.100s', 'identity=0.020s', 'symbols=0.030s',
    'resume=0.040s', 'firstStatusTotal=', 'firstLuaBoundary=0.321s',
    'jsonDecode=', 'catalogLocalization=',
):
    assert field in log, field

print('connect_phase_profile_ok')
