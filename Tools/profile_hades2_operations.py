#!/usr/bin/env python3
"""Opt-in offline Hades profiling; launches temporary helpers, never the game.

The transport fixture runs the production LLDB boundary with fake Lua functions.
The resident fixture runs production Lua 5.2 against explicit native stubs. Their
measurements are separate, not an estimate of end-to-end game/UI latency.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests")]


def summarize(samples):
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "median_ms": statistics.median(samples) * 1000,
        "p95_ms": ordered[math.ceil(len(samples) * .95) - 1] * 1000,
        "samples_seconds": samples,
    }


class TimedProxy:
    def __init__(self, owner, methods, times):
        self.owner, self.methods, self.times = owner, methods, times

    def __iter__(self):
        return iter(self.owner)

    def __getattr__(self, name):
        method = getattr(self.owner, name)
        if name not in self.methods:
            return method
        return timed(method, name, self.times)


def timed(method, name, times):
    def measured(*args, **kwargs):
        started = time.perf_counter()
        try:
            return method(*args, **kwargs)
        finally:
            times[name] += time.perf_counter() - started
    return measured


def profile_transport(samples, tick_interval_us):
    from hades2_lldb_fixture import HELPER_SOURCE, attach_helper, cleanup, lldb

    timings = collections.defaultdict(list)
    with tempfile.TemporaryDirectory(prefix="mgt-profile-lldb-") as temporary:
        source = Path(temporary) / "helper.c"
        executable = Path(temporary) / "helper"
        source.write_text(HELPER_SOURCE, encoding="utf-8")
        subprocess.run(
            ["/usr/bin/clang", "-g", "-O0", "-pthread", str(source), "-o", str(executable)],
            check=True, capture_output=True, text=True,
        )
        # Fresh helper attachments include LLDB fixture setup and symbol lookup;
        # they do not exercise production game identity validation.
        for attachment in range(3):
            started = time.perf_counter()
            child, debugger, transport, addresses = attach_helper(
                executable, 0, tick_interval_us=tick_interval_us,
            )
            timings["fixture_attachment"].append(time.perf_counter() - started)
            try:
                times = collections.defaultdict(float)
                transport.process = TimedProxy(transport.process, {
                    "Stop", "Continue", "ReadMemory", "WriteMemory", "ReadPointerFromMemory",
                    "AllocateMemory", "DeallocateMemory", "ReadCStringFromMemory",
                }, times)
                transport.target = TimedProxy(transport.target, {
                    "BreakpointCreateByAddress", "BreakpointDelete",
                }, times)
                for name in ("boundary", "stop", "resume", "drain", "restore_focus"):
                    setattr(transport, name, timed(getattr(transport, name), name, times))

                iterations = samples + 3 if attachment == 0 else 1
                for index in range(iterations):
                    times.clear()
                    started = time.perf_counter()
                    result = transport.execute("return true")
                    elapsed = time.perf_counter() - started
                    assert result == "{}", result
                    assert transport.target.GetNumBreakpoints() == 0, "leaked breakpoint"
                    assert transport.focus_original is None, "focus flag not restored"
                    assert not transport.tainted, "successful call closed trust"
                    if index == 0:
                        timings["cold_execute"].append(elapsed)
                    if attachment == 0 and index >= 3:
                        for name, duration in {
                            **times, "execute": elapsed, "expression": transport.last_expression_duration,
                        }.items():
                            timings[name].append(duration)

                # Verify actual target memory after the timed section. These
                # assertions and the extra stop/resume are not timing samples.
                transport.stop(time.monotonic() + 3)
                error = lldb.SBError()
                focus = transport.process.ReadMemory(
                    addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error,
                )
                assert error.Success() and focus == b"\x01", (str(error), focus)
                transport.resume(time.monotonic() + 3)
            finally:
                cleanup(child, debugger, transport)
    return {
        "workload": "production LLDB execute, fake Lua result {}, 3 warmups; 3 fresh helper attachments",
        "tick_interval_us": tick_interval_us,
        "clock": "perf_counter wall time; nested measurements overlap",
        "python": sys.version,
        "lldb": lldb.SBDebugger.GetVersionString(),
        "metrics": {name: summarize(values) for name, values in timings.items()},
    }


def profile_resident(samples):
    from lua_runtime_support import require_lua52

    lua = require_lua52("offline Hades operation profiling")
    fixture = ROOT / "Tools/fixtures/hades2_operation_profile.lua"
    runtime = ROOT / "Backend/games/hades2/runtime/hades.lua"
    completed = subprocess.run(
        [lua, str(fixture), str(runtime), str(samples)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    timings = collections.defaultdict(list)
    features = None
    for line in completed.stdout.splitlines():
        name, value = line.split("\t", 1)
        if name == "features":
            features = json.loads(value)
        else:
            timings[name].append(float(value))
    if features is None:
        raise RuntimeError("resident fixture did not report its verified active features")
    return {
        "workload": "production Lua 5.2 with explicit native stubs; empty trait inventory; no game engine",
        "clock": "os.clock CPU time; frame samples average 100 UpdateTimers calls",
        "lua": subprocess.check_output([lua, "-v"], stderr=subprocess.STDOUT, text=True).strip(),
        "active_features": features,
        "metrics": {name: summarize(values) for name, values in timings.items()},
    }


def positive_integer(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def run_transport_worker(command, environment, timeout):
    # The worker creates a native target. If the worker times out or is
    # interrupted, its Python finally cannot own that target's cleanup. Keep
    # the whole temporary process group inside this launcher's lifetime.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=environment, start_new_session=True) as worker:
        try:
            stdout, stderr = worker.communicate(timeout=timeout)
            if worker.returncode:
                raise subprocess.CalledProcessError(worker.returncode, command, stdout, stderr)
            return stdout
        finally:
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            worker.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "transport", "resident"), default="all")
    parser.add_argument("--samples", type=positive_integer, default=30)
    parser.add_argument("--tick-microseconds", type=int, default=16667,
                        help="temporary helper update cadence; not a game frame rate measurement")
    parser.add_argument("--output", type=Path, help="write full JSON evidence; otherwise print it")
    args = parser.parse_args()
    if args.tick_microseconds < 0:
        parser.error("--tick-microseconds must be non-negative (0 means a busy loop)")

    report = {
        "sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_changes": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        ).splitlines(),
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("Backend/games/hades2/transport.py", "Backend/games/hades2/runtime/hades.lua")
        },
    }
    if args.mode in ("all", "transport"):
        if sys.platform != "darwin":
            parser.error("transport profiling needs macOS, Xcode Python and LLDB; use --mode resident on Linux")
        if os.environ.get("MGT_PROFILE_LLDB_EMBEDDED") == "1":
            # Internal child emits only the transport result. No nested debugger
            # interpreter; Xcode Python imports its ABI-matched LLDB extension.
            print(json.dumps(profile_transport(args.samples, args.tick_microseconds)))
            return
        environment = dict(os.environ, MGT_PROFILE_LLDB_EMBEDDED="1")
        raw = run_transport_worker(
            ["/usr/bin/xcrun", "python3", str(Path(__file__).resolve()),
             "--mode", "transport", "--samples", str(args.samples),
             "--tick-microseconds", str(args.tick_microseconds)],
            environment, 30 + (args.samples + 6) * 4,
        )
        report["transport"] = json.loads(raw)
    if args.mode in ("all", "resident"):
        report["resident"] = profile_resident(args.samples)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
        print(str(args.output.resolve()))
    else:
        print(encoded, end="")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.stderr.write((error.stdout or "") + (error.stderr or ""))
        raise SystemExit(error.returncode) from error
