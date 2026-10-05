import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# GitHub's macOS runner Python is not ABI-matched to Xcode's private _lldb
# extension. Execute the actual regression inside LLDB's embedded Python, which
# is also the environment that owns the SB API. Keep an outer hard timeout so a
# debugger regression cannot stall the whole macOS lane.
if os.environ.get("MGT_LLDB_EMBEDDED_TEST") != "1":
    path = str(Path(__file__).resolve())
    embedded = (
        "script import os,runpy; "
        "os.environ['MGT_LLDB_EMBEDDED_TEST']='1'; "
        f"runpy.run_path({path!r}, run_name='__main__')"
    )
    try:
        completed = subprocess.run(
            ["/usr/bin/xcrun", "lldb", "-b", "-o", embedded, "-o", "quit"],
            text=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError("LLDB breakpoint-lifetime regression exceeded 30 seconds") from error
    if completed.returncode != 0 or "hades2_lldb_breakpoint_lifetime_ok" not in completed.stdout:
        raise AssertionError(
            "embedded LLDB regression failed:\n"
            + completed.stdout
            + completed.stderr
        )
    print("hades2_lldb_breakpoint_lifetime_ok")
    raise SystemExit(0)

sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import transport as transport_module
from games.hades2.transport import Hades2LuaTransport, TransportError

lldb = transport_module.lldb

HELPER_SOURCE = r"""
#include <mach/mach_time.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>

volatile unsigned char require_focus = 1;
void *lua_interface = (void *)0x1234;
volatile int delay_ms = 0;
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
  volatile int value = 0;
  for (;;) {
    value = tick(value);
    if (value > 1000000) value = 0;
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


def attach_helper(executable, delay):
    child = subprocess.Popen([str(executable), str(delay)])
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

    transport = Hades2LuaTransport.__new__(Hades2LuaTransport)
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


def cleanup(child, debugger, transport):
    try:
        process = getattr(transport, "process", None)
        if process is not None and process.IsValid():
            state = process.GetState()
            if state not in (lldb.eStateExited, lldb.eStateDetached, lldb.eStateInvalid):
                process.Kill()
    finally:
        try:
            lldb.SBDebugger.Destroy(debugger)
        finally:
            try:
                child.kill()
            except ProcessLookupError:
                pass


with tempfile.TemporaryDirectory(prefix="mgt-lldb-breakpoint-lifetime-") as temporary:
    temporary = Path(temporary)
    source = temporary / "helper.c"
    executable = temporary / "helper"
    source.write_text(HELPER_SOURCE, encoding="utf-8")
    subprocess.run(
        ["/usr/bin/clang", "-g", "-O0", "-pthread", str(source), "-o", str(executable)],
        check=True,
        capture_output=True,
        text=True,
    )

    child, debugger, transport, addresses = attach_helper(executable, 0)
    try:
        assert transport.execute("return true", expression_timeout_seconds=1.0) == "{}"
        assert transport.target.GetNumBreakpoints() == 0, "successful expression leaked a breakpoint"
        transport.stop(time.monotonic() + 2)
        error = lldb.SBError()
        focus = transport.process.ReadMemory(
            addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error
        )
        assert error.Success() and focus == b"\x01", (str(error), focus)
        transport.resume(time.monotonic() + 2)
    finally:
        cleanup(child, debugger, transport)

    # Before the transport fix, this production execute() path failed with
    # "breakpoint N which has been deleted": boundary() deleted the stop reason
    # before EvaluateExpression. A slow fake pcall remains a genuine unknown
    # outcome, but its breakpoint identity must survive LLDB unwind.
    child, debugger, transport, _ = attach_helper(executable, 500)
    try:
        try:
            transport.execute("return true", expression_timeout_seconds=0.1)
        except TransportError as error:
            assert error.code == "outcome_unknown", error.code
            message = str(error).lower()
            assert "deleted" not in message, message
        else:
            raise AssertionError("slow expression unexpectedly completed inside its timeout budget")
        assert transport.tainted is True
        assert transport.target.GetNumBreakpoints() == 0, "timeout path leaked a breakpoint"
    finally:
        cleanup(child, debugger, transport)

print("hades2_lldb_breakpoint_lifetime_ok")
