import math


TOGGLES = (
    'godMode','infiniteHealth','infiniteMana','damageEnabled','instantCastCooldown',
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
