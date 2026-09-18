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


# A connect attempt that fails before attach/status must not report metrics from
# the previous successful attempt.
adapter._last_status_boundary_duration = 9.0
adapter._last_status_json_duration = 9.0
adapter._last_status_localize_duration = 9.0

def failing_scan():
    raise RuntimeError('simulated scan failure')

adapter.scan = failing_scan
failed_scan_stream = StringIO()
failed_scan_handler = logging.StreamHandler(failed_scan_stream)
root_logger.addHandler(failed_scan_handler)
root_logger.setLevel(logging.INFO)
try:
    try:
        adapter.connect()
    except RuntimeError as error:
        assert 'simulated scan failure' in str(error)
    else:
        raise AssertionError('scan failure unexpectedly succeeded')
finally:
    root_logger.removeHandler(failed_scan_handler)
    root_logger.setLevel(old_level)

assert adapter._last_status_boundary_duration == 0.0
assert adapter._last_status_json_duration == 0.0
assert adapter._last_status_localize_duration == 0.0
failed_log = failed_scan_stream.getvalue()
assert 'ConnectProfile outcome=RuntimeError' in failed_log
assert 'firstLuaBoundary=0.000s' in failed_log
assert 'jsonDecode=0.000s' in failed_log
assert 'catalogLocalization=0.000s' in failed_log

transport_source = (ROOT / 'Backend/games/hades2/transport.py').read_text()
assert "self.last_attach_profile={'reused':True,'total':0.0}" in transport_source

print('connect_phase_profile_failure_paths_ok')


# A status that reaches the LLDB/Lua boundary but returns "waiting" still spent
# real debugger time. ConnectProfile must preserve that boundary duration so a
# manual #4 sample does not report a misleading 0.000s firstLuaBoundary.
class WaitingTransport(FakeTransport):
    def execute(self, source):
        self.last_duration = 2.750
        raise adapter_module.TransportError('waiting', 'simulated waiting')


waiting_transport = WaitingTransport()
waiting_adapter = adapter_module.Hades2Adapter(transport=waiting_transport)
waiting_adapter.preference_initialized = True
waiting_adapter.preference_dirty = False


def waiting_scan():
    waiting_adapter.state['pid'] = 4343
    waiting_adapter.state['status'] = 'disconnected'
    return dict(waiting_adapter.state)


waiting_adapter.scan = waiting_scan
waiting_stream = StringIO()
waiting_handler = logging.StreamHandler(waiting_stream)
root_logger.addHandler(waiting_handler)
root_logger.setLevel(logging.INFO)
try:
    waiting_result = waiting_adapter.connect()
finally:
    root_logger.removeHandler(waiting_handler)
    root_logger.setLevel(old_level)

assert waiting_result['status'] == 'waiting'
assert waiting_adapter._last_status_boundary_duration == 2.750
waiting_log = waiting_stream.getvalue()
assert 'ConnectProfile outcome=waiting' in waiting_log
assert 'firstLuaBoundary=2.750s' in waiting_log

print('connect_phase_profile_waiting_ok')


# Background launch attach can reach World::Update before Hades has finished
# publishing its Lua game globals. During the initial connect only, that exact
# bootstrap-not-ready condition is waiting, not an incompatible/disconnect.
class EarlyRuntimeTransport(FakeTransport):
    def execute(self, source):
        self.last_duration = 0.050
        raise adapter_module.TransportError(
            'lua_error',
            '[string "MacGamingTrainer"]:7: Unsupported game runtime: missing table SessionState',
        )


early_transport = EarlyRuntimeTransport()
early_adapter = adapter_module.Hades2Adapter(transport=early_transport)
early_adapter.preference_initialized = True
early_adapter.preference_dirty = False


def early_scan():
    early_adapter.state['pid'] = 4444
    early_adapter.state['status'] = 'disconnected'
    return dict(early_adapter.state)


early_adapter.scan = early_scan
early_result = early_adapter.connect()
assert early_result['status'] == 'waiting'
assert early_result['connected'] is True
assert early_transport.alive() is True
assert early_adapter._last_status_boundary_duration == 0.050

print('connect_phase_profile_early_runtime_ok')
