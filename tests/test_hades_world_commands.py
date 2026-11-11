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
apply_exit = {
    'roomId': 'runtime:run:room',
    'doorToken': 'door:room:reward',
    'requestId': 'apply-exit-1',
    'kind': 'reward',
    'targetID': 'AthenaUpgrade',
}
assert mutation_params('apply_world_exit', apply_exit) == apply_exit
apply_route = {**apply_exit, 'kind': 'roomCategory', 'targetID': 'story'}
assert mutation_params('apply_world_exit', apply_route) == apply_route
cancel_exit = {
    'roomId': 'runtime:run:room',
    'doorToken': 'door:room:reward',
    'requestId': 'cancel-exit-1',
    'leaseToken': 'exit:apply-exit-1',
}
assert mutation_params('cancel_world_exit', cancel_exit) == cancel_exit
apply_occurrence = {
    'roomId': 'runtime:run:room',
    'requestId': 'apply-occurrence-1',
    'targetID': 'npc:Sisyphus',
}
assert mutation_params('apply_world_occurrence', apply_occurrence) == apply_occurrence
cancel_occurrence = {
    'roomId': 'runtime:run:room',
    'requestId': 'cancel-occurrence-1',
    'leaseToken': 'occurrence:apply-occurrence-1',
}
assert mutation_params('cancel_world_occurrence', cancel_occurrence) == cancel_occurrence
for command, payload, expected in (
    ('set_door_reward', {**valid, 'roomId': ''}, 'stale_room'),
    ('set_door_reward', {**valid, 'doorId': ''}, 'stale_door'),
    ('set_door_reward', {**valid, 'reward': 'TrialUpgrade'}, 'invalid_value'),
    ('spawn_reward', {**valid, 'reward': 'ArbitraryLua'}, 'invalid_value'),
    ('set_door_route', {**valid, 'route': 'arbitraryMap'}, 'invalid_value'),
    ('apply_world_exit', {**apply_exit, 'doorToken': ''}, 'stale_door'),
    ('apply_world_exit', {**apply_exit, 'requestId': ''}, 'invalid_value'),
    ('apply_world_exit', {**apply_exit, 'kind': 'roomCategory', 'targetID': 'thanatos'}, 'invalid_value'),
    ('apply_world_exit', {**apply_exit, 'kind': 'reward', 'targetID': 'TrialUpgrade'}, 'invalid_value'),
    ('cancel_world_exit', {**cancel_exit, 'leaseToken': ''}, 'stale_door'),
    ('apply_world_occurrence', {**apply_occurrence, 'targetID': 'npc:Hades'}, 'invalid_value'),
    ('apply_world_occurrence', {**apply_occurrence, 'requestId': ''}, 'invalid_value'),
    ('cancel_world_occurrence', {**cancel_occurrence, 'leaseToken': ''}, 'stale_target'),
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
