TOGGLES = (
    'godMode','infiniteHealth','infiniteMana','damageEnabled','instantCastCooldown',
    'hexAlwaysReady','infiniteAmmo','autoMiniGames','gardenQoL','boonRarityEnabled',
    'moneyMultiplierEnabled','resourceMultiplierEnabled',
)

MULTIPLIERS = ('damageMultiplier','moneyMultiplier','resourceMultiplier','gameSpeed')

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
