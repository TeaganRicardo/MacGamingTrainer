"""User-facing Hades II runtime error presentation.

The resident runtime and transport keep technical error detail for diagnostics.
Known player-action failures resolve through the Hades-owned declarative registry
so Core remains game-agnostic and this boundary carries no second mapping table.
"""
import logging
import re

from core.adapter import AdapterError

from .error_presentation import Hades2PresentationError, runtime_presentation_for

_LUA_SOURCE_PREFIX = re.compile(r'^\[string "[^"]*"\]:\d+:\s*')


def present_runtime_error(command, error):
    if not isinstance(error, AdapterError) or error.code != 'lua_error':
        return error

    raw = str(error)
    detail = _LUA_SOURCE_PREFIX.sub('', raw).strip()
    diagnostic = error.diagnostic if isinstance(error.diagnostic, str) and error.diagnostic else raw
    key, arguments = runtime_presentation_for(command, detail)
    logging.warning('Hades Lua error command=%s raw=%s', command, raw)
    return Hades2PresentationError(error.code, key, arguments, diagnostic=diagnostic)
