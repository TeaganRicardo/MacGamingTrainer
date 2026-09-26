"""Hades II module-protocol routing.

Pure JSON-compatible parameter rules live in command_validation.py. This router
owns command selection and delegates side effects to the adapter/game services.
"""
import subprocess

from core.adapter import AdapterError

from . import preparation
from .command_validation import validate_command_params
from .config import STEAM_SPEC
from .diagnostics import build_diagnostics, export_diagnostics
from .runtime_error_presentation import present_runtime_error

_RUNTIME_COMMANDS = frozenset((
    'status','disable_all','set_desired','set_vital','set_counter','lock_vital',
    'set_stat','set_element','lock_element','set_resource','lock_resource',
    'set_rerolls','lock_rerolls','spawn_reward','open_sell_traits',
    'open_special_choice',
))


_REQUEST_ID_COMMANDS = frozenset((
    'set_resource','set_rerolls','spawn_reward','open_sell_traits',
    'open_special_choice','lock_resource','lock_rerolls',
))


class Hades2CommandRouter:
    def __init__(self, adapter):
        self.adapter = adapter

    def dispatch(self, command, params, request_id):
        try:
            return self._dispatch(command, params, request_id)
        except AdapterError as error:
            presented=present_runtime_error(command,error)
            if presented is error:
                raise
            raise presented from error

    def _dispatch(self, command, params, request_id):
        adapter=self.adapter
        rid=request_id
        if command=='scan':
            result=adapter.scan()
        elif command=='connect':
            validated=validate_command_params(command,params)
            result=adapter.connect(probe_runtime=validated['probeRuntime'])
        elif command=='disconnect':
            result=adapter.disconnect()
        elif command=='runtime_reset':
            result=adapter.runtime_reset()
        elif command=='reset_desired':result=adapter.reset_desired()
        elif command in _RUNTIME_COMMANDS:
            params=validate_command_params(command,params)
            if command in _REQUEST_ID_COMMANDS:
                params=dict(params,requestId=rid)
            if command=='set_desired':
                result=adapter.set_desired(params['feature'],params['value'])
            else:
                result=adapter.execute(command,params)
        elif command=='set_boon_rarity_desired':
            config=validate_command_params(command,params)
            result=adapter.set_boon_rarity_desired(config)
        elif command=='set_next_room_reward_desired':
            validated=validate_command_params(command,params)
            result=adapter.set_next_room_reward_desired(validated['reward'])
        elif command=='list_profiles':
            result={'profiles':adapter.list_profiles()}
        elif command=='save_profile':
            result=adapter.save_profile(params.get('name'),params.get('shortcuts'))
        elif command=='load_profile':
            result=adapter.load_profile(params.get('name'))
        elif command=='delete_profile':
            result=adapter.delete_profile(params.get('name'))
        elif command=='diagnostics':
            result=build_diagnostics(adapter)
        elif command=='export_diagnostics':
            result=export_diagnostics(adapter)
            subprocess.run(['/usr/bin/open','-R',result['diagnosticBundle']],check=True,timeout=10, shell=False)
        elif command=='launch':
            subprocess.run(['/usr/bin/open',STEAM_SPEC.launch_url],check=True,timeout=10,shell=False)
            result=adapter.scan()
        elif command in ('prepare','restore'):
            if adapter.transport.alive():
                raise ValueError('请断开连接并退出游戏后操作。')
            info={'prepare':preparation.prepare,'restore':preparation.restore}[command]()
            result=dict(adapter.scan(),operation=info)
        else:
            raise ValueError('未知命令。')
        return result
