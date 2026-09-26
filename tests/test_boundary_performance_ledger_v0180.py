import json
import logging
import sys
import tempfile
from io import StringIO
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from core.adapter import AdapterError
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter


class FakeTransport:
    def __init__(self):
        self.pid = 4242
        self.last_duration = 0.125
        self.fail = None
        self.raw_result = None
        self.is_alive = True
        self.calls = 0

    def alive(self):
        return self.is_alive

    def execute(self, source):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        if self.raw_result is not None:
            return self.raw_result
        return json.dumps({
            'status': 'ready',
            'scene': 'run',
            'capabilities': {},
            'desiredFeatures': {},
            'activeFeatures': {},
        })

    def detach(self):
        self.is_alive = False

    def close(self):
        self.is_alive = False


base = Path(tempfile.mkdtemp(prefix='mgt-boundary-ledger-v0180-'))
preparation.DATA = base
transport = FakeTransport()
adapter = Hades2Adapter(transport=transport)
adapter.preference_initialized = True
adapter.preference_dirty = False

stream = StringIO()
handler = logging.StreamHandler(stream)
root_logger = logging.getLogger()
old_level = root_logger.level
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)
try:
    adapter.execute('status', {})
    log = stream.getvalue()
    assert 'LuaBoundary command=status' in log
    assert 'duration=0.125s' in log
    assert 'outcome=ok' in log
    assert 'crossed_transport=yes' in log
    assert 'replay=False' in log

    stream.seek(0)
    stream.truncate(0)
    transport.fail = AdapterError('waiting', 'simulated wait')
    try:
        adapter.execute('status', {}, replay=True)
    except AdapterError as error:
        assert error.code == 'waiting'
    else:
        raise AssertionError('transport failure was unexpectedly swallowed')
    log = stream.getvalue()
    assert 'LuaBoundary command=status' in log
    assert 'duration=0.125s' in log
    assert 'outcome=waiting' in log
    assert 'crossed_transport=yes' in log
    assert 'replay=True' in log

    # A boundary call that returns but violates the host JSON contract records
    # the decode failure rather than claiming the request outcome was successful.
    stream.seek(0)
    stream.truncate(0)
    transport.fail = None
    transport.raw_result = '{broken'
    try:
        adapter.execute('status', {})
    except AdapterError as error:
        assert error.code == 'outcome_unknown'
    else:
        raise AssertionError('malformed Lua JSON unexpectedly decoded')
    log = stream.getvalue()
    assert 'LuaBoundary command=status' in log
    assert 'outcome=outcome_unknown' in log
    assert 'crossed_transport=yes' in log

    # Pre-boundary failures must not be mislabeled as debugger/Lua crossings.
    stream.seek(0)
    stream.truncate(0)
    transport.fail = None
    transport.raw_result = None
    transport.is_alive = False
    before = transport.calls
    try:
        adapter.execute('status', {})
    except AdapterError as error:
        assert error.code == 'disconnected'
    else:
        raise AssertionError('disconnected execute unexpectedly succeeded')
    assert transport.calls == before
    assert 'LuaBoundary' not in stream.getvalue()
finally:
    root_logger.removeHandler(handler)
    root_logger.setLevel(old_level)

print('boundary_performance_ledger_v0180_ok')
