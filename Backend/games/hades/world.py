"""Hades room/reward identities and explicit one-shot payload validation."""
import hashlib
import json
from pathlib import Path

from core.adapter import AdapterError
from .schema import RESOURCE_IDS, WORLD_COMMANDS, invalid_value, number


_DATA = json.loads(Path(__file__).with_name('world_catalog.json').read_text())
REWARDS = _DATA['rewards']
ROUTES = frozenset(('combat', 'story', 'shop', 'reprieve', 'miniboss', 'thanatos'))
# Names and Generate-row grouping are presentation only; the resident never
# reads them, so they stay outside its definitions identity.
_PRESENTATION_FIELDS = frozenset(('names', 'group', 'section', 'sectionNames'))


def reward_catalog():
    return list(REWARDS.values())


def world_terms():
    return _DATA['terms']


def runtime_definitions():
    return {identifier: {key: value for key, value in row.items() if key not in _PRESENTATION_FIELDS}
            for identifier, row in REWARDS.items()}


def runtime_definitions_identity(definitions):
    canonical = json.dumps(definitions, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def mutation_params(command, params):
    if command == 'gain_resource':
        resource = params.get('resource')
        if not isinstance(resource, str) or resource not in RESOURCE_IDS | {'Money'}:
            raise invalid_value()
        return {'resource': resource, 'amount': number(params.get('amount'), 1, 1_000_000, integer=True)}
    room_id = params.get('roomId')
    if not isinstance(room_id, str) or not room_id:
        raise AdapterError('stale_room', 'hades.error.staleRoom')
    result = {'roomId': room_id}
    if command in ('set_door_reward', 'set_door_route', 'restore_door'):
        door_id = params.get('doorId')
        if not isinstance(door_id, str) or not door_id:
            raise AdapterError('stale_door', 'hades.error.staleDoor')
        result['doorId'] = door_id
    if command in ('spawn_reward', 'set_door_reward'):
        reward = params.get('reward')
        if not isinstance(reward, str) or reward not in REWARDS:
            raise invalid_value()
        if command == 'set_door_reward' and not REWARDS[reward]['doorAllowed']:
            raise invalid_value()
        result['reward'] = reward
    if command == 'generate_chamber_object':
        kind = params.get('object')
        if not isinstance(kind, str) or kind not in ('trove', 'well', 'purge'):
            raise invalid_value()
        result['object'] = kind
    if command == 'set_door_route':
        route = params.get('route')
        if not isinstance(route, str) or route not in ROUTES:
            raise invalid_value()
        result['route'] = route
    return result
