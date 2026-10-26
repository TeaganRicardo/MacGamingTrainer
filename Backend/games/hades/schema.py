import math

from core.adapter import AdapterError


DEFAULT_FEATURES = {
    'invincibility': False,
    'moneyNoDecrease': False,
    'rerollsNoDecrease': False,
    'fullGodGauge': False,
    'boonRarityEnabled': False,
    'damageMultiplier': 1,
    'moveSpeedMultiplier': 1,
    'attackSpeedMultiplier': 1,
    'dashBonus': 0,
}
# Process Time Warp is a separate Core-owned native helper. It is a durable
# module preference, but it must never enter the Lua resident feature document.
DEFAULT_PREFERENCES = {**DEFAULT_FEATURES, 'gameSpeed': 1.0}
RESOURCE_IDS = frozenset(('MetaPoints', 'Gems', 'SuperGems', 'LockKeys',
                          'SuperLockKeys', 'GiftPoints', 'SuperGiftPoints'))
ONE_SHOT_COMMANDS = frozenset(('set_value', 'heal', 'set_resource', 'add_trait',
                               'update_trait', 'remove_trait'))
MUTATING_COMMANDS = ONE_SHOT_COMMANDS | {'set_feature', 'set_invincibility',
                                       'configure', 'disable_all'}


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


def preference_value(name, value):
    if name == 'gameSpeed':
        return number(value, 0, 10)
    return feature_value(name, value)


def preference_document(values):
    if not isinstance(values, dict) or set(values) != set(DEFAULT_PREFERENCES):
        raise invalid_value()
    return {name: preference_value(name, value) for name, value in values.items()}
