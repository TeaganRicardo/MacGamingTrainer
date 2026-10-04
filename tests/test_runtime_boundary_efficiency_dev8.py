import json
import sys
import tempfile
from pathlib import Path

from runtime_revision_support import runtime_revision

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core.adapter import AdapterError
from games.hades2 import adapter as adapter_module
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.config import LUA_TRANSPORT_RESULT_LIMIT_BYTES, LUA_TRANSPORT_SOURCE_LIMIT_BYTES

base = Path(tempfile.mkdtemp(prefix='mgt-runtime-boundary-dev8-'))
preparation.DATA = base
adapter_module.localize_catalog = lambda payload: payload


class FakeTransport:
    def __init__(self):
        self.pid = 4242
        self.last_duration = 0.001
        self.sources = []
        self.trait_tray_open = False

    def alive(self): return True
    def attach(self, pid): self.pid = pid
    def detach(self): pass
    def close(self): pass

    def execute(self, source):
        self.sources.append(source)
        if self.trait_tray_open and 'MGT_TRAIT_TRAY_ACTIVE' in source:
            raise AdapterError('lua_error', 'MGT_TRAIT_TRAY_ACTIVE')
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
        if self.trait_tray_open and '__trainerTraitTrayActive' in source:
            payload['__trainerTraitTrayActive'] = True
        return json.dumps(payload)


transport = FakeTransport()
adapter = Hades2Adapter(transport=transport)

first = adapter.execute('status', {})
assert adapter._runtime_bootstrapped is True
assert adapter._catalog_initialized is True
assert first['rewards'][0]['id'] == 'RoomMoneyDrop'
assert len(transport.sources) == 1
first_source_bytes = len(transport.sources[0].encode('utf-8'))
assert first_source_bytes > 100_000
assert first_source_bytes <= LUA_TRANSPORT_SOURCE_LIMIT_BYTES, (
    f'fresh resident bootstrap exceeds transport source cap: {first_source_bytes}'
)
assert LUA_TRANSPORT_RESULT_LIMIT_BYTES == 262_144
revision = runtime_revision(adapter.bootstrap)
assert f'revision = {revision}' in transport.sources[0]
assert '["includeCatalogs"]=true' in transport.sources[0]

second = adapter.execute('status', {})
assert len(transport.sources) == 2
assert len(transport.sources[1].encode('utf-8')) < 2_000
assert f'revision = {revision}' not in transport.sources[1]
assert '["includeCatalogs"]=false' in transport.sources[1]
# The Lua patch omits static catalogs after the first boundary, but the adapter
# retains them in its authoritative merged state, so Host/UI responses lose no data.
assert second['rewards'][0]['id'] == 'RoomMoneyDrop'
assert second['boons'][0]['id'] == 'ZeusUpgrade'

# A player-opened Trait Tray owns UI/script input and can enter wait/yield paths.
# Mutations injected through the synchronous LLDB lua_pcall boundary must refuse
# to dispatch before touching resident state, while read-only status remains
# available so Host observation/recovery still works.
assert 'MGT_TRAIT_TRAY_ACTIVE' not in transport.sources[1]
assert '__trainerTraitTrayActive' in transport.sources[1]
adapter.execute('set_vital', {'vital': 'health', 'field': 'current', 'value': 100})
assert len(transport.sources) == 3
mutation_source = transport.sources[2]
trait_tray_guard = 'ActiveScreens.TraitTrayScreen'
assert trait_tray_guard in mutation_source
assert mutation_source.index(trait_tray_guard) < mutation_source.index('__MacGamingTrainerV1.dispatch')
assert 'MGT_TRAIT_TRAY_ACTIVE' in mutation_source

transport.trait_tray_open = True
try:
    adapter.execute('set_vital', {'vital': 'health', 'field': 'current', 'value': 90})
except AdapterError as error:
    assert error.code == 'invalid_request'
    assert str(error) == '当前祝福菜单打开时无法执行修改，请先关闭菜单。'
else:
    raise AssertionError('Trait Tray mutation guard did not fail closed')

# Disable All is still a user-triggered mutation, not a recovery-only transport
# primitive. It must be rejected by the same guard rather than being a special
# case that can still touch game state while Trait Tray owns UI/input.
try:
    adapter.execute('disable_all', {})
except AdapterError as error:
    assert error.code == 'invalid_request'
    assert str(error) == '当前祝福菜单打开时无法执行修改，请先关闭菜单。'
else:
    raise AssertionError('Trait Tray guard allowed disable_all mutation')

# Read-only status stays available while the screen is open. If desired state is
# dirty, the observation must not fall through into the automatic replay batch.
adapter.preference_dirty = True
status_source_count = len(transport.sources)
status_while_open = adapter.execute('status', {})
assert status_while_open['status'] == 'ready'
assert len(transport.sources) == status_source_count + 1
assert adapter.preference_dirty is True
assert 'MGT_TRAIT_TRAY_ACTIVE' not in transport.sources[-1]
transport.trait_tray_open = False
adapter.preference_dirty = False

# Explicit replay batches carry the same pre-dispatch guard as direct mutations.
adapter.execute(
    'replay_preferences', {}, replay=True,
    batch=[('set_feature', {'feature': 'invincibility', 'value': False})],
)
batch_source = transport.sources[-1]
assert 'MGT_TRAIT_TRAY_ACTIVE' in batch_source
assert batch_source.index(trait_tray_guard) < batch_source.index('__MacGamingTrainerV1.dispatch')

# World::Update boundary contract: the live transport must break on the one
# engine frame boundary we actually need, not on every Lua pcall and then
# filter callers after repeatedly stopping the game.
transport_source = (ROOT / 'Backend/games/hades2/transport.py').read_text()
symbols = json.loads((ROOT / 'Backend/games/hades2/symbols.json').read_text())['symbols']
world_symbol = '_ZN3sgg5World6UpdateEf'
assert world_symbol in symbols
boundary = transport_source[
    transport_source.index('    def boundary('):
    transport_source.index('    def execute(', transport_source.index('    def boundary('))
]
assert "BreakpointCreateByAddress(self.address('_ZN3sgg5World6UpdateEf'))" in boundary
assert "BreakpointCreateByAddress(self.address('lua_pcallk'))" not in boundary
assert "caller=='sgg::World::Update(float)'" not in boundary

print('runtime_boundary_efficiency_dev8_ok')
