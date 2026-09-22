"""Pure Host-v5 parameter validation for Hades II commands.

Routing and side effects stay in command_router.py / adapter.py. This module
owns only game-local JSON-compatible parameter rules.
"""
import math

from .schema import (
    BOON_RARITY_TARGETS,
    MAX_AMOUNT,
    STAT_RULES,
    VITALS,
    is_known_element,
    is_valid_next_room_reward,
    validate_desired_feature_value,
)

def validate_command_params(command, params):
    params=dict(params or {})

    if command=='connect':
        probe_runtime=params.get('probeRuntime',True)
        if type(probe_runtime) is not bool:
            raise ValueError('probeRuntime 必须为布尔值。')
        return {'probeRuntime':probe_runtime}

    if command=='set_desired':
        feature=params.get('feature')
        value=validate_desired_feature_value(feature,params.get('value'))
        return {'feature':feature,'value':value}

    if command=='set_vital':
        vital=params.get('vital');field=params.get('field');value=params.get('value')
        if vital not in VITALS or field not in ('current','max'):
            raise ValueError('局内数值字段无效。')
        if vital=='armor' and field!='current':
            raise ValueError('护甲仅提供当前值，不存在可编辑上限。')
        if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=MAX_AMOUNT:
            raise ValueError(f'局内数值必须为 0–{MAX_AMOUNT}。')
        if vital=='health' and value<1:
            raise ValueError('生命值必须至少为 1。')

    elif command=='set_counter':
        if params.get('counter')!='spellCharge':
            raise ValueError('未知局内计数器。')
        value=params.get('value')
        if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=MAX_AMOUNT:
            raise ValueError(f'巫咒充能必须为 0–{MAX_AMOUNT}。')

    elif command=='lock_vital':
        vital=params.get('vital');locked=params.get('locked')
        if vital not in VITALS:
            raise ValueError('未知局内数值。')
        if type(locked) is not bool:
            raise ValueError('锁定值必须为布尔值。')

    elif command=='set_stat':
        stat=params.get('stat');locked=params.get('locked');value=params.get('value')
        rule=STAT_RULES.get(stat)
        if rule is None:
            raise ValueError('未知属性。')
        if type(locked) is not bool:
            raise ValueError('锁定值必须为布尔值。')
        if locked:
            if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value):
                raise ValueError('属性值必须为有限数值。')
            if rule.get('integer') and type(value) is not int:
                raise ValueError(rule['error'])
            if not rule['min']<=value<=rule['max']:
                raise ValueError(rule['error'])

    elif command in ('set_element','lock_element'):
        element=params.get('element')
        if not is_known_element(element):
            raise ValueError('未知元素。')
        if command=='set_element':
            amount=params.get('amount')
            if type(amount) is not int or not 0<=amount<=MAX_AMOUNT:
                raise ValueError(f'元素数量必须为 0–{MAX_AMOUNT} 的整数。')
        elif type(params.get('locked')) is not bool:
            raise ValueError('锁定值必须为布尔值。')

    elif command in ('set_resource','set_rerolls'):
        if type(params.get('amount')) is not int or not 0<=params['amount']<=MAX_AMOUNT:
            raise ValueError(f'数量必须是 0–{MAX_AMOUNT} 的整数。')

    if command in ('set_resource','lock_resource'):
        if not isinstance(params.get('resource'),str) or not params['resource']:
            raise ValueError('请选择资源。')

    if command in ('lock_resource','lock_rerolls'):
        if type(params.get('locked')) is not bool:
            raise ValueError('锁定值必须为布尔值。')

    if command=='spawn_reward':
        if not isinstance(params.get('reward'),str) or not params['reward']:
            raise ValueError('请选择掉落物或祝福。')

    if command=='open_special_choice':
        source=params.get('source')
        if not isinstance(source,str) or not source:
            raise ValueError('请选择支持原生三选一的特殊祝福来源。')

    if command=='set_boon_rarity_desired':
        config={
            'target':params.get('target'),
            'multiplier':params.get('multiplier'),
            'forceLegendary':params.get('forceLegendary'),
            'forceDuo':params.get('forceDuo'),
        }
        if config['target'] not in BOON_RARITY_TARGETS:
            raise ValueError('最低稀有度无效。')
        if type(config['multiplier']) not in (int,float) or isinstance(config['multiplier'],bool) or not math.isfinite(config['multiplier']) or not 0<=config['multiplier']<=1000:
            raise ValueError('稀有度倍率必须为 0–1000%。')
        if type(config['forceLegendary']) is not bool or type(config['forceDuo']) is not bool:
            raise ValueError('Legendary / Duo 设置无效。')
        return config

    if command=='set_next_room_reward_desired':
        reward=params.get('reward')
        if not is_valid_next_room_reward(reward):
            raise ValueError('下一房奖励无效。')
        return {'reward':reward}

    return params
