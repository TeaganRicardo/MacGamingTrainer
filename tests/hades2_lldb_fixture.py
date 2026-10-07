"""Temporary native target for Hades transport tests and opt-in profiling.

Fake Lua functions isolate debugger cost; this fixture never attaches to a game.
Import only under the Xcode Python ABI.
"""
import subprocess
import time

from games.hades2 import transport as transport_module
from games.hades2.transport import Hades2LuaTransport, TransportError

lldb = transport_module.lldb

HELPER_SOURCE = r"""
#include <mach/mach_time.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <unistd.h>

volatile unsigned char require_focus = 1;
void *lua_interface = (void *)0x1234;
volatile int delay_ms = 0;
volatile int tick_interval_us = 0;
static const char result_text[] = "{}";

__attribute__((noinline)) int tick(int value) {
  return value + 1;
}

static void spin_ms(int milliseconds) {
  mach_timebase_info_data_t info;
  mach_timebase_info(&info);
  uint64_t start = mach_absolute_time();
  uint64_t target_ns = (uint64_t)milliseconds * 1000000ULL;
  for (;;) {
    uint64_t elapsed = mach_absolute_time() - start;
    uint64_t elapsed_ns = elapsed * info.numer / info.denom;
    if (elapsed_ns >= target_ns) return;
  }
}

int fake_lua_gettop(void *state) {
  (void)state;
  return 0;
}

int fake_luaL_loadbufferx(
    void *state,
    const char *source,
    unsigned long length,
    const char *name,
    const char *mode) {
  (void)state;
  (void)source;
  (void)length;
  (void)name;
  (void)mode;
  return 0;
}

int fake_lua_pcallk(
    void *state,
    int nargs,
    int nresults,
    int error_function,
    int context,
    void *continuation) {
  (void)state;
  (void)nargs;
  (void)nresults;
  (void)error_function;
  (void)context;
  (void)continuation;
  spin_ms(delay_ms);
  return 0;
}

const char *fake_lua_tolstring(void *state, int index, unsigned long *length) {
  (void)state;
  (void)index;
  *length = 2;
  return result_text;
}

void fake_lua_settop(void *state, int index) {
  (void)state;
  (void)index;
}

int main(int argc, char **argv) {
  pthread_setname_np("MainThread");
  delay_ms = argc > 1 ? atoi(argv[1]) : 0;
  tick_interval_us = argc > 2 ? atoi(argv[2]) : 0;
  volatile int value = 0;
  for (;;) {
    value = tick(value);
    if (value > 1000000) value = 0;
    if (tick_interval_us > 0) usleep(tick_interval_us);
  }
}
"""

SYMBOLS = {
    "_ZN3sgg13ConfigOptions20RequireFocusToUpdateE": "require_focus",
    "_ZN3sgg5World6UpdateEf": "tick",
    "_ZN3sgg13ScriptManager12LuaInterfaceE": "lua_interface",
    "lua_gettop": "fake_lua_gettop",
    "luaL_loadbufferx": "fake_luaL_loadbufferx",
    "lua_pcallk": "fake_lua_pcallk",
    "lua_tolstring": "fake_lua_tolstring",
    "lua_settop": "fake_lua_settop",
}


def symbol_address(module, target, name):
    matches = module.FindSymbols(name, lldb.eSymbolTypeAny)
    addresses = set()
    for index in range(matches.GetSize()):
        symbol = matches.GetContextAtIndex(index).GetSymbol()
        address = symbol.GetStartAddress().GetLoadAddress(target)
        if symbol.IsValid() and address not in (0, lldb.LLDB_INVALID_ADDRESS):
            addresses.add(address)
    assert len(addresses) == 1, (name, addresses)
    return addresses.pop()


def attach_helper(executable, delay, *, tick_interval_us=0):
    child = subprocess.Popen([str(executable), str(delay), str(tick_interval_us)])
    debugger = None
    transport = Hades2LuaTransport.__new__(Hades2LuaTransport)
    transport.process = None
    try:
        time.sleep(0.05)
        lldb.SBDebugger.Initialize()
        debugger = lldb.SBDebugger.Create()
        debugger.SetAsync(True)
        listener = debugger.GetListener()
        target = debugger.CreateTarget("")
        error = lldb.SBError()
        process = target.AttachToProcessWithID(listener, child.pid, error)
        assert error.Success(), str(error)

        module = target.GetModuleAtIndex(0)
        addresses = {
            expected: symbol_address(module, target, actual)
            for expected, actual in SYMBOLS.items()
        }

        transport.debugger = debugger
        transport.listener = listener
        transport.target = target
        transport.process = process
        transport.pid = child.pid
        transport.addresses = {}
        transport.last_duration = 0
        transport.last_expression_duration = 0
        transport.last_attach_profile = {}
        transport.focus_original = None
        transport.tainted = False
        transport.address = lambda name: addresses[name]
        return child, debugger, transport, addresses
    except BaseException:
        cleanup(child, debugger, transport)
        raise


def cleanup(child, debugger, transport):
    try:
        process = getattr(transport, "process", None)
        if process is not None and process.IsValid():
            state = process.GetState()
            if state not in (lldb.eStateExited, lldb.eStateDetached, lldb.eStateInvalid):
                process.Kill()
    finally:
        try:
            if debugger is not None:
                lldb.SBDebugger.Destroy(debugger)
        finally:
            try:
                child.kill()
            except ProcessLookupError:
                pass
            child.wait(timeout=5)
