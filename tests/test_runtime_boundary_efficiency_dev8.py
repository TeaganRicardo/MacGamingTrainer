from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades2 import adapter as adapter_module
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter

base = Path(tempfile.mkdtemp(prefix='mgt-runtime-boundary-dev8-'))
preparation.DATA = base
adapter_module.localize_catalog = lambda payload: payload


class FakeTransport:
    def __init__(self):
        self.pid = 4242
        self.last_duration = 0.001
        self.sources = []

    def alive(self): return True
    def attach(self, pid): self.pid = pid
    def detach(self): pass
    def close(self): pass

    def execute(self, source):
        self.sources.append(source)
        include_catalogs = '["includeCatalogs"]=true' in source
        payload = {
            'status': 'ready',
            'scene': 'run',
            'capabilities': {},
            'desiredFeatures': {},
            'activeFeatures': {},
            'dormantFeatures': {},
            'featureSupport': {},
            'featureErrors': {},
            'boonRarity': {
                'target': 'Epic', 'multiplier': 100.0,
                'forceLegendary': False, 'forceDuo': False,
            },
            'resources': [], 'elements': [], 'stats': {},
        }
        if include_catalogs:
            payload['boons'] = [{'id': 'ZeusUpgrade', 'name': 'Zeus'}]
            payload['rewards'] = [{'id': 'RoomMoneyDrop', 'name': 'Gold'}]
        return json.dumps(payload)


transport = FakeTransport()
adapter = Hades2Adapter(transport=transport)

first = adapter.execute('status', {})
assert adapter._runtime_bootstrapped is True
assert adapter._catalog_initialized is True
assert first['rewards'][0]['id'] == 'RoomMoneyDrop'
assert len(transport.sources) == 1
assert len(transport.sources[0].encode('utf-8')) > 100_000
assert 'revision = 26' in transport.sources[0]
assert '["includeCatalogs"]=true' in transport.sources[0]

second = adapter.execute('status', {})
assert len(transport.sources) == 2
assert len(transport.sources[1].encode('utf-8')) < 2_000
assert 'revision = 26' not in transport.sources[1]
assert '["includeCatalogs"]=false' in transport.sources[1]
# The Lua patch omits static catalogs after the first boundary, but the adapter
# retains them in its authoritative merged state, so Host/UI responses lose no data.
assert second['rewards'][0]['id'] == 'RoomMoneyDrop'
assert second['boons'][0]['id'] == 'ZeusUpgrade'

print('runtime_boundary_efficiency_dev8_ok')
