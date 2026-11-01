#!/usr/bin/env python3
"""Bounded, synthetic-only trace of the unchanged Hades I LLDB transport.

This is an unvalidated diagnostic candidate, not a regression test or a claimed
reproducer. Run on the Mac with a fresh output directory, for example:
  python3 probe_565_rosetta.py --repo /path/to/MacGamingTrainer \
    --output /tmp/mgt-565-normal-01 --iterations 8

The optional expression-timeout scenario deliberately stalls a fake Lua call;
it must produce outcome_unknown and never retries that request. No game process,
save, user preference, production symbol gate, or debugger executable is edited.
The outer process owns its worker group and uses PID-version audit tokens to
clean only default debugservers whose parent unique ID is this worker's ID.
Logs and synthetic source/binary are retained in --output on every outcome.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


TARGET_SOURCE = r'''
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/sysctl.h>
#include <unistd.h>

volatile unsigned char require_focus = 1;
void *lua_interface = (void *)0x1234;
volatile int stall_call = 0;
volatile unsigned int pcall_entries = 0;
__attribute__((noinline)) int tick(int value) { return value + 1; }
int fake_lua_gettop(void *state) { (void)state; return 0; }
int fake_luaL_loadbufferx(void *s, const char *p, unsigned long n,
                         const char *name, const char *mode) {
  (void)s; (void)p; (void)n; (void)name; (void)mode; return 0;
}
int fake_lua_pcallk(void *s, int a, int b, int c, int d, void *e) {
  (void)s; (void)a; (void)b; (void)c; (void)d; (void)e;
  ++pcall_entries;
  while (stall_call) { __asm__ volatile("" ::: "memory"); }
  return 0;
}
const char *fake_lua_tolstring(void *s, int i, unsigned long *n) {
  (void)s; (void)i; *n = 2; return "{}";
}
void fake_lua_settop(void *s, int i) { (void)s; (void)i; }
int main(void) {
  int translated = 0;
  size_t size = sizeof(translated);
  int status = sysctlbyname("sysctl.proc_translated", &translated, &size, NULL, 0);
  pthread_setname_np("MainThread");
  alarm(60);
  printf("{\"pid\":%d,\"translated\":%d,\"sysctl_status\":%d}\n",
         getpid(), translated, status);
  fflush(stdout);
  volatile int value = 0;
  for (;;) {
    value = tick(value);
    if (value > 1000000) value = 0;
    usleep(1000);
  }
}
'''

SYMBOLS = {
    "_ZN3sgg13ConfigOptions20RequireFocusToUpdateE": "require_focus",
    "_ZN3sgg3App6UpdateEf": "tick",
    "_ZN3sgg13ScriptManager13LUA_INTERFACEE": "lua_interface",
    "lua_gettop": "fake_lua_gettop",
    "luaL_loadbufferx": "fake_luaL_loadbufferx",
    "lua_pcallk": "fake_lua_pcallk",
    "lua_tolstring": "fake_lua_tolstring",
    "lua_settop": "fake_lua_settop",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=30,
                        help="Whole worker budget, including attach and cleanup (10–60 s)")
    parser.add_argument("--scenario", choices=("normal", "expression-timeout"), default="normal")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100 or not 10 <= args.timeout <= 60:
        parser.error("iterations must be 1–100 and timeout 10–60 seconds")
    args.repo = args.repo.resolve(strict=True)
    args.output = args.output.resolve()
    return args


def worker(args):
    # The parent has captured our kernel unique ID before allowing LLDB launch.
    while not (args.output / "worker-go").exists():
        time.sleep(.01)
    sys.path.insert(0, str(args.repo / "Backend"))
    from games.hades import transport as module
    lldb = module.lldb
    trace = (args.output / "operations.jsonl").open("w", buffering=1)
    started = time.monotonic()
    raw_process = None
    child = None
    transport = None
    request_index = 0

    def event(name, **details):
        state = None
        stop_id = None
        if raw_process is not None and raw_process.IsValid():
            state = lldb.SBDebugger.StateAsCString(raw_process.GetState())
            stop_id = raw_process.GetStopID()
        trace.write(json.dumps(dict(event=name, request=request_index,
                                    elapsed=round(time.monotonic() - started, 6),
                                    state=state, stop_id=stop_id, **details)) + "\n")

    def observed(name, operation, *values):
        event(name + ".begin")
        try:
            result = operation(*values)
        except BaseException as error:
            event(name + ".failed", error=repr(error))
            raise
        detail = str(result.GetError()) if hasattr(result, "GetError") else str(result)
        event(name + ".end", result=detail)
        return result

    class Proxy:
        def __init__(self, native, kind):
            self.native, self.kind = native, kind

        def __getattr__(self, name):
            method = getattr(self.native, name)
            if name in {"SendAsyncInterrupt", "Continue", "WriteMemory", "AllocateMemory",
                        "DeallocateMemory", "Detach", "DeleteAllBreakpoints", "SetEnabled",
                        "EvaluateExpression"}:
                return lambda *values: observed(self.kind + "." + name, method, *values)
            if name == "BreakpointCreateByAddress":
                return lambda *values: Proxy(observed("target." + name, method, *values), "breakpoint")
            if name == "GetFrameAtIndex":
                return lambda *values: Proxy(method(*values), "frame")
            return method

        def __iter__(self):
            return (Proxy(thread, "thread") for thread in self.native)

    try:
        target_path = args.output / "synthetic-target"
        child = subprocess.Popen([str(target_path)], stdout=subprocess.PIPE, text=True)
        ready = json.loads(child.stdout.readline())
        child.stdout.close()
        event("fixture.ready", **ready)
        assert ready["pid"] == child.pid and ready["translated"] == 1, ready
        transport = module.HadesLuaTransport()
        interpreter = transport.debugger.GetCommandInterpreter()
        for channel, categories, filename in (
            ("gdb-remote", "packets process", "gdb-remote.log"),
            ("lldb", "process state", "lldb-process.log"),
        ):
            result = lldb.SBCommandReturnObject()
            log_path = json.dumps(str(args.output / filename))
            interpreter.HandleCommand(f"log enable -f {log_path} {channel} {categories}", result)
            assert result.Succeeded(), result.GetError()
        event("target.create.begin")
        target = transport.debugger.CreateTarget("")
        error = lldb.SBError()
        event("target.attach.begin", pid=child.pid)
        raw_process = target.AttachToProcessWithID(transport.listener, child.pid, error)
        event("target.attach.end", error=str(error))
        assert error.Success(), str(error)
        image = target.GetModuleAtIndex(0)
        assert Path(str(image.GetFileSpec())).resolve() == target_path, str(image.GetFileSpec())
        assert target.GetTriple().startswith("x86_64-"), target.GetTriple()

        def address(name):
            matches = image.FindSymbols(name, lldb.eSymbolTypeAny)
            values = set()
            for index in range(matches.GetSize()):
                symbol = matches.GetContextAtIndex(index).GetSymbol()
                value = symbol.GetStartAddress().GetLoadAddress(target)
                if symbol.IsValid() and value not in (0, lldb.LLDB_INVALID_ADDRESS):
                    values.add(value)
            assert len(values) == 1, (name, values)
            return values.pop()

        # Fixture-only attach populates the same seam used by the existing
        # native Hades II fixture; production exact-image validation is untouched.
        transport.target = Proxy(target, "target")
        transport.process = Proxy(raw_process, "process")
        transport.pid = child.pid
        transport.addresses = {key: address(name) for key, name in SYMBOLS.items()}
        event("fixture.attached", uuid=image.GetUUIDString(), triple=target.GetTriple())
        (args.output / "attached").write_text(str(child.pid))
        # Do not exercise the target unless the outer owner captured the actual
        # default server's audit identity. Timeout still exits through cleanup.
        ownership_deadline = time.monotonic() + 2
        while not (args.output / "server-owned").exists():
            if time.monotonic() > ownership_deadline:
                raise RuntimeError("Default debugserver was not bound to this worker's unique ID")
            time.sleep(.01)
        transport.resume(time.monotonic() + 3)
        for request_index in range(1, args.iterations + 1):
            event("execute.begin")
            result = transport.execute('return "{}"', mutating=True)
            assert result == {}, result
            event("execute.end", result=result)
        if args.scenario == "expression-timeout":
            request_index += 1
            transport.stop(time.monotonic() + 3)
            error = lldb.SBError()
            assert transport.process.WriteMemory(address("stall_call"), b"\x01\x00\x00\x00", error) == 4
            assert error.Success(), str(error)
            transport.resume(time.monotonic() + 3)
            event("expected_timeout.begin")
            try:
                transport.execute('return "{}"', mutating=True)
            except module.AdapterError as error:
                event("expected_timeout.result", code=error.code, diagnostic=error.diagnostic)
                assert error.code == "outcome_unknown" and transport.tainted, str(error)
            else:
                raise AssertionError("Synthetic stalled expression unexpectedly completed")
            # No retry after unknown native outcome.
        event("probe.sequence_completed", scenario=args.scenario)
        return 0
    finally:
        try:
            if transport is not None:
                event("transport.close.begin")
                transport.close()
                event("transport.close.end")
        finally:
            if child is not None:
                try:
                    child.kill()
                except ProcessLookupError:
                    pass
                child.wait(timeout=2)
            trace.close()


def parent(args):
    if sys.platform != "darwin":
        raise RuntimeError("This diagnostic requires an Apple Silicon Mac with Rosetta installed")
    if os.environ.get("LLDB_DEBUGSERVER_PATH"):
        raise RuntimeError("Unset LLDB_DEBUGSERVER_PATH for this diagnostic; preserve default server selection")
    args.output.mkdir(parents=True, exist_ok=False)
    home = args.output / "temporary-home"
    home.mkdir()
    temporary = args.output / "tmp"
    temporary.mkdir()
    environment = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home), TMPDIR=str(temporary))
    source = args.output / "synthetic-target.c"
    source.write_text(TARGET_SOURCE)
    subprocess.run(["/usr/bin/xcrun", "clang", "-arch", "x86_64", "-g", "-O0", str(source),
                    "-o", str(args.output / "synthetic-target")], check=True, timeout=15, env=environment)
    lldb_python = subprocess.check_output(["/usr/bin/xcrun", "lldb", "-P"], text=True,
                                          timeout=5, env=environment).strip()
    environment["PYTHONPATH"] = lldb_python
    sys.path.insert(0, str(args.repo / "tests"))
    from hades2_debugserver_owner import DarwinProcesses, _ProcessIdentity
    processes = DarwinProcesses()

    def identity(pid):
        value = _ProcessIdentity()
        amount = processes.library.proc_pidinfo(pid, 17, 0, ctypes.byref(value), ctypes.sizeof(value))
        if amount != ctypes.sizeof(value):
            raise RuntimeError("Cannot bind process unique identity: " + str(pid))
        return value

    paths = {Path("/Library/Apple/usr/libexec/oah/debugserver"),
             Path(lldb_python).parent / "debugserver"}
    paths = {path.resolve() for path in paths if path.is_file()}
    assert paths, "No default debugserver candidate found"
    baseline = {(str(path), int(token[5]), int(token[7]))
                for path in paths for token in processes.matching(path)}
    metadata = {"scenario": args.scenario, "iterations": args.iterations,
                "worker_timeout_seconds": args.timeout, "lldb_python": lldb_python,
                "transport_sha256": digest(args.repo / "Backend/games/hades/transport.py"),
                "probe_sha256": digest(__file__), "target_sha256": digest(args.output / "synthetic-target"),
                "server_candidates": {str(path): digest(path) for path in paths}}
    for key, command in (
        ("source_head", ["git", "-C", str(args.repo), "rev-parse", "HEAD"]),
        ("source_index_tree", ["git", "-C", str(args.repo), "write-tree"]),
        ("source_worktree_status", ["git", "-C", str(args.repo), "status", "--porcelain"]),
        ("macos", ["/usr/bin/sw_vers"]), ("xcode", ["/usr/bin/xcodebuild", "-version"]),
        ("lldb", ["/usr/bin/xcrun", "lldb", "--version"]),
    ):
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, env=environment)
        metadata[key] = dict(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
    write_json(args.output / "environment.json", metadata)
    command = ["/usr/bin/xcrun", "python3", str(Path(__file__).resolve()), "--worker",
               "--repo", str(args.repo), "--output", str(args.output),
               "--iterations", str(args.iterations), "--timeout", str(args.timeout),
               "--scenario", args.scenario]
    owned = {}
    timeout_hit = False
    cleanup_errors = []
    with (args.output / "worker.stdout").open("w") as stdout, \
            (args.output / "worker.stderr").open("w") as stderr:
        # Popen.__exit__ performs an unbounded wait. Own this worker explicitly
        # so a failed reap cannot bypass the escaped-server cleanup below.
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=environment,
                                   start_new_session=True)
        worker_identity = None

        def capture_owned():
            if worker_identity is None:
                return
            for path in paths:
                for token in processes.matching(path):
                    key = (str(path), int(token[5]), int(token[7]))
                    if key in baseline or key in owned:
                        continue
                    candidate = identity(token[5])
                    if candidate.parent_unique_id != worker_identity.unique_id:
                        continue
                    # Recheck token-bound path after reading identity: a recycled
                    # PID is never signalled or accepted as ownership evidence.
                    if processes.path(token) == path:
                        owned[key] = (path, token)
                        (args.output / "server-owned").write_text(json.dumps(key))
                        write_json(args.output / "owned-servers.json", [
                            dict(path=p, pid=pid, pid_version=version, sha256=digest(p),
                                 parent_unique_id=worker_identity.unique_id)
                            for p, pid, version in owned])

        deadline = time.monotonic() + args.timeout
        try:
            worker_identity = identity(process.pid)
            (args.output / "worker-go").write_text(str(worker_identity.unique_id))
            while process.poll() is None:
                capture_owned()
                if time.monotonic() >= deadline:
                    timeout_hit = True
                    break
                time.sleep(.02)
        finally:
            try:
                capture_owned()
            except Exception as error:
                cleanup_errors.append("final inventory: " + repr(error))
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as error:
                cleanup_errors.append("worker group cleanup: " + repr(error))
            try:
                process.wait(timeout=2)
            except Exception as error:
                cleanup_errors.append("worker reap: " + repr(error))
            for path, token in owned.values():
                try:
                    if processes.path(token) == path:
                        processes.kill(token)
                except Exception as error:
                    cleanup_errors.append("owned server cleanup: " + repr(error))
            cleanup_deadline = time.monotonic() + 2
            pending = list(owned.values())
            while pending:
                remaining = []
                for path, token in pending:
                    try:
                        if processes.path(token) == path:
                            remaining.append((path, token))
                    except Exception as error:
                        cleanup_errors.append("cleanup verification: " + repr(error))
                if not remaining:
                    break
                if time.monotonic() >= cleanup_deadline:
                    for path, token in remaining:
                        cleanup_errors.append("owned server remains: " + str(int(token[5])))
                    break
                pending = remaining
                time.sleep(.01)
            if process.returncode is None:
                try:
                    process.wait(timeout=2)
                except Exception as error:
                    cleanup_errors.append("final worker reap: " + repr(error))
            # The observation itself may be propagating an exception, which
            # skips the normal summary below. Keep cleanup evidence in that case.
            print(json.dumps({"event": "probe.parent.cleanup", "cleanup_errors": cleanup_errors,
                              "worker_returncode": process.returncode,
                              "owned_server_count": len(owned)}), flush=True)
        returncode = process.returncode
    text = "\n".join(path.read_text(errors="replace") for path in (
        args.output / "worker.stdout", args.output / "worker.stderr"))
    summary = dict(worker_returncode=returncode, timeout=timeout_hit,
                   owned_server_count=len(owned), cleanup_errors=cleanup_errors,
                   assertion_signature_in_captured_streams=("gTaskSuspended" in text and "remove_translation" in text),
                   interpretation="Synthetic observation only; absence does not resolve issue 565")
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    print("Retained diagnostic artifacts: " + str(args.output), flush=True)
    return 0 if returncode == 0 and not timeout_hit and owned and not cleanup_errors else 1


if __name__ == "__main__":
    options = arguments()
    raise SystemExit(worker(options) if options.worker else parent(options))
