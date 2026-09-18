#!/usr/bin/env python3
import ctypes
import ctypes.util
import sys
from pathlib import Path

name = ctypes.util.find_library('lua5.4') or 'liblua5.4.so.0'
lua = ctypes.CDLL(name)
L = ctypes.c_void_p
lua.luaL_newstate.restype = L
lua.luaL_openlibs.argtypes = [L]
lua.luaL_loadfilex.argtypes = [L, ctypes.c_char_p, ctypes.c_char_p]
lua.luaL_loadfilex.restype = ctypes.c_int
lua.lua_pcallk.argtypes = [L, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
lua.lua_pcallk.restype = ctypes.c_int
lua.lua_tolstring.argtypes = [L, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
lua.lua_tolstring.restype = ctypes.c_char_p
lua.lua_close.argtypes = [L]

def error_text(state):
    size = ctypes.c_size_t()
    value = lua.lua_tolstring(state, -1, ctypes.byref(size))
    return ctypes.string_at(value, size.value).decode('utf-8', errors='replace') if value else 'unknown Lua error'

if len(sys.argv) != 2:
    raise SystemExit('usage: run_lua_mock.py <file.lua>')
path = Path(sys.argv[1]).resolve()
state = lua.luaL_newstate()
if not state:
    raise SystemExit('luaL_newstate failed')
try:
    lua.luaL_openlibs(state)
    rc = lua.luaL_loadfilex(state, str(path).encode(), None)
    if rc:
        raise SystemExit(error_text(state))
    rc = lua.lua_pcallk(state, 0, -1, 0, 0, None)
    if rc:
        raise SystemExit(error_text(state))
finally:
    lua.lua_close(state)
