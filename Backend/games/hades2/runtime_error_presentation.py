"""User-facing Hades II runtime error presentation.

The resident runtime and transport keep technical error detail for diagnostics.
This module translates known player-action failures at the Hades boundary so
Core can remain game-agnostic and the UI never depends on Lua source locations.
"""
import logging
import re

from core.adapter import AdapterError


_LUA_SOURCE_PREFIX = re.compile(r'^\[string "[^"]*"\]:\d+:\s*')

_RUNTIME_MESSAGES = {
    'open_sell_traits': {
        'Cannot open boon sell screen while another screen is active':
            '已有游戏界面打开，请先关闭当前界面后再打开出售祝福界面。',
        'Boon selling requires an active run room':
            '出售祝福仅可在局内房间使用。',
        'Native boon sell screen data is unavailable':
            '当前游戏状态无法打开出售祝福界面。',
    },
    'open_special_choice': {
        'Cannot open special blessing choice while another screen is active':
            '已有游戏界面打开，请先关闭当前界面后再打开特殊祝福选择。',
        'Cannot open special blessing choice during a transition':
            '场景切换中，暂时无法打开特殊祝福选择。',
        'Special blessing choice requires an active run room':
            '特殊祝福选择仅可在局内房间使用。',
        'Special blessing source has no audited native choice flow':
            '该特殊祝福来源暂不支持原生选择界面。',
        'Special blessing source data is unavailable':
            '当前游戏状态无法读取该特殊祝福来源。',
        'Special blessing choice data is unavailable':
            '当前游戏状态无法读取该特殊祝福选择。',
        'No eligible special blessings are available':
            '当前没有可供选择的特殊祝福。',
    },
}


def present_runtime_error(command, error):
    if not isinstance(error, AdapterError) or error.code != 'lua_error':
        return error

    raw = str(error)
    detail = _LUA_SOURCE_PREFIX.sub('', raw).strip()
    message = _RUNTIME_MESSAGES.get(command, {}).get(
        detail,
        '游戏内操作失败，请查看日志。',
    )
    logging.warning('Hades Lua error command=%s raw=%s', command, raw)
    return AdapterError(error.code, message)
