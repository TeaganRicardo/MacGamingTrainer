"""Hades room/reward identities and explicit one-shot payload validation."""
import hashlib
import json
from pathlib import Path

from core.adapter import AdapterError
from .schema import RESOURCE_IDS, WORLD_COMMANDS, invalid_value, number


_DATA = json.loads(Path(__file__).with_name('world_catalog.json').read_text())
REWARDS = _DATA['rewards']
GENERIC_ROUTES = frozenset(('combat', 'story', 'shop', 'reprieve', 'miniboss'))
OCCURRENCE_TARGETS = frozenset((
    'npc:Sisyphus', 'npc:Eurydice', 'npc:Patroclus', 'npc:Thanatos', 'shop:Charon',
))
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
    if command in ('apply_world_exit', 'cancel_world_exit'):
        door_token = params.get('doorToken')
        if not isinstance(door_token, str) or not door_token:
            raise AdapterError('stale_door', 'hades.error.staleDoor')
        request_id = params.get('requestId')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise invalid_value()
        result['doorToken'] = door_token
        result['requestId'] = request_id
    if command in ('apply_world_occurrence', 'cancel_world_occurrence'):
        request_id = params.get('requestId')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise invalid_value()
        result['requestId'] = request_id
    if command == 'spawn_reward':
        reward = params.get('reward')
        if not isinstance(reward, str) or reward not in REWARDS:
            raise invalid_value()
        result['reward'] = reward
    if command == 'apply_world_exit':
        kind = params.get('kind')
        target_id = params.get('targetID')
        if kind == 'reward':
            if (not isinstance(target_id, str) or target_id not in REWARDS
                    or not REWARDS[target_id]['doorAllowed']):
                raise invalid_value()
        elif kind == 'roomCategory':
            if target_id not in GENERIC_ROUTES:
                raise invalid_value()
        else:
            raise invalid_value()
        result['kind'] = kind
        result['targetID'] = target_id
    if command == 'cancel_world_exit':
        lease_token = params.get('leaseToken')
        if not isinstance(lease_token, str) or not 1 <= len(lease_token) <= 384:
            raise AdapterError('stale_door', 'hades.error.staleDoor')
        result['leaseToken'] = lease_token
    if command == 'apply_world_occurrence':
        target_id = params.get('targetID')
        if target_id not in OCCURRENCE_TARGETS:
            raise invalid_value()
        result['targetID'] = target_id
    if command == 'cancel_world_occurrence':
        lease_token = params.get('leaseToken')
        if not isinstance(lease_token, str) or not 1 <= len(lease_token) <= 384:
            raise AdapterError('stale_target', 'hades.error.staleTarget')
        result['leaseToken'] = lease_token
    if command == 'generate_chamber_object':
        kind = params.get('object')
        if not isinstance(kind, str) or kind not in ('trove', 'well', 'purge'):
            raise invalid_value()
        result['object'] = kind
    return result
