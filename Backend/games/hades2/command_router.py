"""Hades II command validation and routing.

The adapter owns runtime/transport lifecycle; this router owns module protocol v5
command validation and delegates to game-local services.
"""
import math
import subprocess

from . import preparation
from .config import STEAM_SPEC
from .diagnostics import build_diagnostics, export_diagnostics
from .schema import TOGGLES, MULTIPLIERS, STAT_RULES


class Hades2CommandRouter:
    def __init__(self, adapter):
        self.adapter = adapter

    def dispatch(self, command, params, request_id):
        adapter = self.adapter
        rid = request_id
        if command=='scan':result=adapter.scan()
        elif command=='connect':result=adapter.connect()
        elif command=='disconnect':result=adapter.disconnect()
        elif command=='reset_desired':result=adapter.reset_desired()
        elif command in ('status','disable_all','set_desired','set_vital','set_counter','lock_vital','set_stat','set_element','lock_element','set_resource','lock_resource','set_rerolls','lock_rerolls','spawn_reward','open_sell_traits','open_special_choice'):
            if command=='set_desired':
                feature=params.get('feature');value=params.get('value')
                if feature not in TOGGLES+MULTIPLIERS:raise ValueError('未知功能。')
                if feature in MULTIPLIERS:
                    if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value):raise ValueError('倍率必须为有限数值。')
                    if feature=='gameSpeed':
                        if not 0<=value<=10:raise ValueError('游戏速度范围为 0–10。')
                    elif not 1<=value<=100:raise ValueError('倍率范围为 1–100。')
                elif not isinstance(value,bool):raise ValueError('开关值必须为布尔值。')
            if command=='set_vital':
                vital=params.get('vital');field=params.get('field');value=params.get('value')
                if vital not in ('health','mana','armor') or field not in ('current','max'):raise ValueError('局内数值字段无效。')
                if vital=='armor' and field!='current':raise ValueError('护甲仅提供当前值，不存在可编辑上限。')
                if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=999999:raise ValueError('局内数值必须为 0–999999。')
                if vital=='health' and value<1:raise ValueError('生命值必须至少为 1。')
            if command=='set_counter':
                if params.get('counter')!='spellCharge':raise ValueError('未知局内计数器。')
                value=params.get('value')
                if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=999999:raise ValueError('巫咒充能必须为 0–999999。')
            if command=='lock_vital':
                vital=params.get('vital');locked=params.get('locked')
                if vital not in ('health','mana','armor'):raise ValueError('未知局内数值。')
                if type(locked) is not bool:raise ValueError('锁定值必须为布尔值。')
            if command=='set_stat':
                stat=params.get('stat');locked=params.get('locked');value=params.get('value')
                rule=STAT_RULES.get(stat)
                if rule is None:raise ValueError('未知属性。')
                if type(locked) is not bool:raise ValueError('锁定值必须为布尔值。')
                if locked:
                    if type(value) not in (int,float) or isinstance(value,bool) or not math.isfinite(value):raise ValueError('属性值必须为有限数值。')
                    if rule.get('integer') and type(value) is not int:raise ValueError(rule['error'])
                    if not rule['min']<=value<=rule['max']:raise ValueError(rule['error'])
            if command in ('set_element','lock_element'):
                element=params.get('element')
                if element not in ('Fire','Water','Earth','Air','Aether'):raise ValueError('未知元素。')
                if command=='set_element':
                    amount=params.get('amount')
                    if type(amount) is not int or not 0<=amount<=999999:raise ValueError('元素数量必须为 0–999999 的整数。')
                elif type(params.get('locked')) is not bool:raise ValueError('锁定值必须为布尔值。')
            if command in ('set_resource','set_rerolls'):
                if type(params.get('amount')) is not int or not 0<=params['amount']<=999999:raise ValueError('数量必须是 0–999999 的整数。')
            if command in ('set_resource','lock_resource'):
                if not isinstance(params.get('resource'),str) or not params['resource']:raise ValueError('请选择资源。')
            if command in ('lock_resource','lock_rerolls'):
                if type(params.get('locked')) is not bool:raise ValueError('锁定值必须为布尔值。')
            if command=='spawn_reward':
                if not isinstance(params.get('reward'),str) or not params['reward']:raise ValueError('请选择掉落物或祝福。')
            if command=='open_special_choice':
                source=params.get('source')
                if not isinstance(source,str) or not source:raise ValueError('请选择支持原生三选一的特殊祝福来源。')
            if command in ('set_resource','set_rerolls','spawn_reward','open_sell_traits','open_special_choice','lock_resource','lock_rerolls'):
                params=dict(params,requestId=rid)
            result=adapter.set_desired(feature,value) if command=='set_desired' else adapter.execute(command,params)
        elif command=='set_boon_rarity_desired':
            config={'target':params.get('target'),'multiplier':params.get('multiplier'),'forceLegendary':params.get('forceLegendary'),'forceDuo':params.get('forceDuo')}
            if config['target'] not in ('Common','Rare','Epic','Heroic'):raise ValueError('最低稀有度无效。')
            if type(config['multiplier']) not in (int,float) or isinstance(config['multiplier'],bool) or not math.isfinite(config['multiplier']) or not 0<=config['multiplier']<=1000:raise ValueError('稀有度倍率必须为 0–1000%。')
            if type(config['forceLegendary']) is not bool or type(config['forceDuo']) is not bool:raise ValueError('Legendary / Duo 设置无效。')
            result=adapter.set_boon_rarity_desired(config)
        elif command=='set_next_room_reward_desired':
            reward=params.get('reward')
            if reward is not None and (not isinstance(reward,str) or len(reward)>128):raise ValueError('下一房奖励无效。')
            result=adapter.set_next_room_reward_desired(reward)
        elif command=='list_profiles':result={'profiles':adapter.list_profiles()}
        elif command=='save_profile':result=adapter.save_profile(params.get('name'),params.get('shortcuts'))
        elif command=='load_profile':result=adapter.load_profile(params.get('name'))
        elif command=='delete_profile':result=adapter.delete_profile(params.get('name'))
        elif command=='diagnostics':
            result=build_diagnostics(adapter)
        elif command=='export_diagnostics':
            result=export_diagnostics(adapter)
            subprocess.run(['/usr/bin/open','-R',result['diagnosticBundle']],check=True,timeout=10)
        elif command=='launch':
            subprocess.run(['open',STEAM_SPEC.launch_url],check=True,timeout=10);result=adapter.scan()
        elif command in ('prepare','restore'):
            if adapter.transport.alive():raise ValueError('请断开连接并退出游戏后操作。')
            info={'prepare':preparation.prepare,'restore':preparation.restore}[command]()
            result=dict(adapter.scan(),operation=info)
        else:raise ValueError('未知命令。')
        return result
