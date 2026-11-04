import math

from core.adapter import AdapterError


DEFAULT_FEATURES = {
    'invincibility': False,
    'moneyNoDecrease': False,
    'rerollsNoDecrease': False,
    'fullGodGauge': False,
    'fullHealth': False,
    'infiniteAmmo': False,
    'forceRerolls': False,
    'boonRarityEnabled': False,
    'damageMultiplier': 1,
    'incomingDamageMultiplier': 1,
    'moveSpeedMultiplier': 1,
    'attackSpeedMultiplier': 1,
    'dashBonus': 0,
}
# Process Time Warp is a separate Core-owned native helper. It is a durable
# module preference, but it must never enter the Lua resident feature document.
DEFAULT_PREFERENCES = {
    **DEFAULT_FEATURES,
    'boonRarityTarget': 'Heroic',
    'gameSpeed': 1.0,
    'healthLock': None,
    'moneyLock': None,
    'rerollsLock': None,
}
RESOURCE_IDS = frozenset(('MetaPoints', 'Gems', 'SuperGems', 'LockKeys',
                          'SuperLockKeys', 'GiftPoints', 'SuperGiftPoints'))
WORLD_COMMANDS = frozenset(('gain_resource', 'spawn_reward', 'generate_fishing',
                            'generate_chaos_gate', 'generate_chamber_object', 'set_door_reward', 'set_door_route', 'restore_door'))
ONE_SHOT_COMMANDS = WORLD_COMMANDS | frozenset(('set_value', 'set_resource', 'add_trait',
                                               'update_trait', 'remove_trait', 'add_chaos_pair',
                                               'set_trait_uses', 'expire_trait', 'refresh_trait'))
MUTATING_COMMANDS = ONE_SHOT_COMMANDS | {
    'set_feature', 'set_boon_rarity', 'set_invincibility', 'configure',
    'configure_locks', 'lock_vital', 'lock_resource', 'lock_rerolls', 'disable_all',
}


def invalid_value():
    return AdapterError('invalid_value', 'hades.error.invalidValue')


def number(value, minimum=0, maximum=1_000_000_000, *, integer=False):
    if (type(value) not in (int, float) or not minimum <= value <= maximum
            or not math.isfinite(value) or (integer and value != int(value))):
        raise invalid_value()
    return int(value) if integer else value


def feature_value(name, value):
    if not isinstance(name, str) or name not in DEFAULT_FEATURES:
        raise invalid_value()
    if type(DEFAULT_FEATURES[name]) is bool:
        if type(value) is not bool:
            raise invalid_value()
        return value
    if name == 'dashBonus':
        return number(value, 0, 20, integer=True)
    return number(value, 0.1, 100)


def feature_document(values):
    if not isinstance(values, dict) or set(values) != set(DEFAULT_FEATURES):
        raise invalid_value()
    return {name: feature_value(name, value) for name, value in values.items()}


def boon_rarity_target(value):
    if value not in ('Common', 'Rare', 'Epic', 'Heroic'):
        raise invalid_value()
    return value


def preference_value(name, value):
    if name == 'boonRarityTarget':
        return boon_rarity_target(value)
    if name == 'gameSpeed':
        return number(value, 0, 10)
    if name == 'healthLock':
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {'current', 'max'}:
            raise invalid_value()
        current = number(value.get('current'), 1, 1_000_000_000, integer=True)
        maximum = number(value.get('max'), 1, 1_000_000_000, integer=True)
        if current > maximum:
            raise invalid_value()
        return {'current': current, 'max': maximum}
    if name in ('moneyLock', 'rerollsLock'):
        if value is None:
            return None
        return number(value, 0, 1_000_000_000, integer=True)
    return feature_value(name, value)


def preference_document(values):
    if not isinstance(values, dict) or set(values) != set(DEFAULT_PREFERENCES):
        raise invalid_value()
    normalized = {name: preference_value(name, value) for name, value in values.items()}
    if normalized['moneyNoDecrease'] and normalized['moneyLock'] is not None:
        raise invalid_value()
    if normalized['rerollsNoDecrease'] and normalized['rerollsLock'] is not None:
        raise invalid_value()
    return normalized


def migrate_preference_document(values):
    """Accept only exact shipped schema-1 feature sets, filling new neutral defaults."""
    if not isinstance(values, dict):
        raise invalid_value()
    original = {'invincibility', 'moneyNoDecrease', 'rerollsNoDecrease',
                'fullGodGauge', 'damageMultiplier', 'moveSpeedMultiplier',
                'attackSpeedMultiplier', 'dashBonus'}
    current_before_locks = set(DEFAULT_PREFERENCES) - {'healthLock', 'moneyLock', 'rerollsLock'}
    previous_before_rarity_target = current_before_locks - {'boonRarityTarget'}
    shipped = (
        original,
        original | {'boonRarityEnabled'},
        original | {'boonRarityEnabled', 'gameSpeed'},
        previous_before_rarity_target,
        current_before_locks,
    )
    if set(values) in shipped:
        values = {**DEFAULT_PREFERENCES, **values}
    return preference_document(values)
