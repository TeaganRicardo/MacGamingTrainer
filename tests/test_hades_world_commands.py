"""World payload validation stays outside profiles and rejects stale room intent."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.adapter import AdapterError
from games.hades.adapter import HadesAdapter
from games.hades.schema import DEFAULT_PREFERENCES, ONE_SHOT_COMMANDS
from games.hades.world import WORLD_COMMANDS, mutation_params, reward_catalog, runtime_definitions

assert WORLD_COMMANDS <= ONE_SHOT_COMMANDS
assert WORLD_COMMANDS.isdisjoint(DEFAULT_PREFERENCES)
for row in reward_catalog():
    assert row['names']['zh-CN'] and row['names']['en']
    assert runtime_definitions()[row['id']]['kind'] in ('loot', 'consumable')
valid = {'roomId': 'runtime:run:room', 'doorId': 'door:room', 'reward': 'AthenaUpgrade'}
assert HadesAdapter._mutation_params('set_door_reward', valid) == valid
assert mutation_params('gain_resource', {'resource': 'Gems', 'amount': 20}) == {'resource': 'Gems', 'amount': 20}
for command, payload, expected in (
    ('set_door_reward', {**valid, 'roomId': ''}, 'stale_room'),
    ('set_door_reward', {**valid, 'doorId': ''}, 'stale_door'),
    ('set_door_reward', {**valid, 'reward': 'TrialUpgrade'}, 'invalid_value'),
    ('spawn_reward', {**valid, 'reward': 'ArbitraryLua'}, 'invalid_value'),
    ('set_door_route', {**valid, 'route': 'arbitraryMap'}, 'invalid_value'),
    ('generate_chamber_object', {**valid, 'object': 'arbitraryObject'}, 'invalid_value'),
    ('gain_resource', {'resource': 'Gems', 'amount': True}, 'invalid_value'),
    ('gain_resource', {'resource': 'Gems', 'amount': 1.5}, 'invalid_value'),
    ('gain_resource', {'resource': 'Gems', 'amount': -1}, 'invalid_value'),
):
    try:
        HadesAdapter._mutation_params(command, payload)
    except AdapterError as error:
        assert error.code == expected, (command, error.code)
    else:
        raise AssertionError((command, payload))
print('hades_world_commands_ok')
