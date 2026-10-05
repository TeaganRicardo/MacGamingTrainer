import math

TOGGLES = (
    'invincibility','infiniteHealth','infiniteMana','damageEnabled','instantCastCooldown',
    'hexAlwaysReady','infiniteAmmo','autoMiniGames','gardenQoL','boonRarityEnabled',
    'moneyMultiplierEnabled','resourceMultiplierEnabled',
)

MULTIPLIER_RULES = {
    'damageMultiplier': {'default':2.0,'min':1.0,'max':100.0},
    'moneyMultiplier': {'default':2.0,'min':1.0,'max':100.0},
    'resourceMultiplier': {'default':2.0,'min':1.0,'max':100.0},
    'gameSpeed': {'default':1.0,'min':0.0,'max':10.0},
}
MULTIPLIERS = tuple(MULTIPLIER_RULES)


def desired_feature_defaults():
    values={key:False for key in TOGGLES}
    values.update({key:rule['default'] for key,rule in MULTIPLIER_RULES.items()})
    return values


def normalize_desired_feature_value(feature,value):
    if not isinstance(feature,str):
        return None
    if feature in TOGGLES:
        return value if type(value) is bool else None
    rule=MULTIPLIER_RULES.get(feature)
    if rule is None:
        return None
    if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value):
        return None
    if not rule['min']<=value<=rule['max']:
        return None
    return float(value)


def validate_desired_feature_value(feature,value):
    if not isinstance(feature,str):
        raise ValueError('未知功能。')
    if feature not in TOGGLES and feature not in MULTIPLIER_RULES:
        raise ValueError('未知功能。')
    if feature in TOGGLES:
        if type(value) is not bool:
            raise ValueError('开关值必须为布尔值。')
        return value
    if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value):
        raise ValueError('倍率必须为有限数值。')
    rule=MULTIPLIER_RULES[feature]
    if not rule['min']<=value<=rule['max']:
        if feature=='gameSpeed':
            raise ValueError('游戏速度范围为 0–10。')
        raise ValueError('倍率范围为 1–100。')
    return value


VITALS = ('health','mana','armor')
ELEMENT_IDS = frozenset(('Fire','Water','Earth','Air','Aether'))


def is_known_element(value):
    return isinstance(value,str) and value in ELEMENT_IDS


MAX_AMOUNT = 999999
BOON_RARITY_TARGETS = ('Common','Rare','Epic','Heroic')
NEXT_ROOM_REWARD_MAX_LENGTH = 128

# Wire identities only. Native generation/collection strategy is Lua-owned.
GATHERING_FAMILIES = frozenset(('flora','mining','digging','shades','fishing'))


def normalize_gathering_probabilities(raw):
    if not isinstance(raw,dict):return {}
    return {
        family:float(value) for family,value in raw.items()
        if family in GATHERING_FAMILIES and type(value) in (int,float)
        and 0<=value<=100 and math.isfinite(value)
    }


def validate_gathering_desired(family,probability):
    if not isinstance(family,str) or family not in GATHERING_FAMILIES:
        raise ValueError('请选择采集类型。')
    if probability is not None and (
        type(probability) not in (int,float) or not 0<=probability<=100
        or not math.isfinite(probability)
    ):
        raise ValueError('概率必须为 0–100。')
    return probability


def is_valid_next_room_reward(value):
    return value is None or (isinstance(value,str) and len(value)<=NEXT_ROOM_REWARD_MAX_LENGTH)


def default_boon_rarity():
    return {
        'target':'Epic',
        'multiplier':100.0,
        'forceLegendary':False,
        'forceDuo':False,
    }


STAT_RULES = {
    'grasp': {'min':0,'max':999,'integer':True,'error':'悟性上限必须是 0–999 的整数。'},
    'dodge': {'min':0,'max':100,'error':'概率必须为 0–100。'},
    'crit': {'min':0,'max':100,'error':'概率必须为 0–100。'},
    'chargeSpeed': {'min':10,'max':1000,'error':'速度倍率必须为 10–1000%。'},
    'moveSpeed': {'min':10,'max':1000,'error':'速度倍率必须为 10–1000%。'},
    'sprintSpeed': {'min':10,'max':1000,'error':'速度倍率必须为 10–1000%。'},
    'dashSpeed': {'min':10,'max':1000,'error':'速度倍率必须为 10–1000%。'},
    'attackSpeed': {'min':10,'max':1000,'error':'速度倍率必须为 10–1000%。'},
    'manaRegen': {'min':0,'max':1000,'error':'额外魔力恢复必须为 0–1000/秒。'},
    'enemyDamage': {'min':0,'max':1000,'error':'敌人伤害倍率必须为 0–1000%。'},
    'enemyHealth': {'min':10,'max':1000,'error':'敌人生命倍率必须为 10–1000%。'},
}


def disconnected_capabilities():
    return {
        'setFeature':False,'setVitals':False,'setResource':False,
        'spawnReward':False,'setStats':False,'setElements':False,
        'hotBackup':True,'hotRestore':False,'diagnostics':True,
    }


# Current-run trait/buff management capabilities. These values describe
# operations the Hades-owned runtime can prove for one observed live target;
# they are not acquisition eligibility and never authorize a raw generic edit.
TRAIT_LEVEL_INCREASE_ONE = 'increaseOne'
TRAIT_LEVEL_NONE = 'none'
TRAIT_LEVEL_CAPABILITIES = (TRAIT_LEVEL_INCREASE_ONE, TRAIT_LEVEL_NONE)

TRAIT_RARITY_SET_EXACT = 'setExact'
TRAIT_RARITY_NONE = 'none'
TRAIT_RARITY_CAPABILITIES = (TRAIT_RARITY_SET_EXACT, TRAIT_RARITY_NONE)

# Native SellTraits is name-level/all-matching. #227 also admits one bounded
# direct-trait strategy whose lifecycle has been audited for object-level
# teardown; every other owner-specific lifecycle remains deferred.
TRAIT_REMOVAL_NAME_LEVEL = 'nameLevelAllMatching'
TRAIT_REMOVAL_SINGLE_INSTANCE_FORCE = 'singleInstanceForce'
TRAIT_REMOVAL_NONE = 'none'
TRAIT_REMOVAL_CAPABILITIES = (
    TRAIT_REMOVAL_NAME_LEVEL,
    TRAIT_REMOVAL_SINGLE_INSTANCE_FORCE,
    TRAIT_REMOVAL_NONE,
)

# The identity scope is current-run only. D00 proved `trait.Id` is assigned by
# GetTraitUniqueId and is NOT stable across run reload, restart or save
# round-trip, so it must never be persisted or presented as durable.
TRAIT_IDENTITY_SCOPE = 'currentRunInstance'
