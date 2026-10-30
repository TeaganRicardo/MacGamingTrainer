#!/usr/bin/env python3
"""Opt-in offline Hades profiling; launches temporary helpers, never the game.

The transport fixture runs the production LLDB boundary with fake Lua functions.
The resident fixture runs production Lua 5.2 against explicit native stubs. Their
end-to-end harness also runs the real Host/Core/Hades protocol with temporary
storage and synthetic natives. None of these workloads estimates game FPS.
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
import statistics
import subprocess
import sys
import tempfile
import tarfile
import io
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("MGT_PROFILE_SOURCE_ROOT", ROOT))
sys.path[:0] = [str(SOURCE_ROOT / "Backend"), str(ROOT / "tests")]

from hades2_lldb_worker_support import phase, run_lldb_worker


def summarize(samples):
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "median_ms": statistics.median(samples) * 1000,
        "p95_ms": ordered[math.ceil(len(samples) * .95) - 1] * 1000,
        "p99_ms": ordered[math.ceil(len(samples) * .99) - 1] * 1000,
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
                entries = transport.process.ReadUnsignedFromMemory(
                    addresses["fixture_pcall_entries"], 4, error,
                )
                assert error.Success() and entries == iterations, (str(error), entries, iterations)
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


def profile_first_touch_worker(variant):
    from hades2_lldb_fixture import HELPER_SOURCE, SYMBOLS, cleanup, lldb, symbol_address
    from games.hades2.transport import Hades2LuaTransport

    framework_source = r'''
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <stdio.h>
__attribute__((constructor)) static void load_frameworks(void) {
  const char *frameworks[] = {
    "/System/Library/Frameworks/Foundation.framework/Foundation",
    "/System/Library/Frameworks/AppKit.framework/AppKit",
    "/System/Library/Frameworks/SwiftUI.framework/SwiftUI",
    "/System/Library/Frameworks/Metal.framework/Metal"
  };
  printf("initial %u\n", _dyld_image_count());
  for (unsigned int i = 0; i < 4; ++i) {
    if (!dlopen(frameworks[i], RTLD_NOW | RTLD_LOCAL)) {
      fprintf(stderr, "%s\n", dlerror());
      exit(2);
    }
    printf("%s %u\n", frameworks[i], _dyld_image_count());
  }
  printf("READY %u\n", _dyld_image_count());
  fflush(stdout);
}
'''
    with tempfile.TemporaryDirectory(prefix="mgt-first-touch-") as temporary:
        temporary = Path(temporary)
        source, executable = temporary / "helper.c", temporary / "helper"
        source.write_text(HELPER_SOURCE + framework_source, encoding="utf-8")
        subprocess.run(
            ["/usr/bin/clang", "-g", "-O0", "-pthread", str(source), "-o", str(executable)],
            check=True, capture_output=True, text=True,
        )
        cache = temporary / "index-cache"
        cache.mkdir()
        transport = Hades2LuaTransport()
        debugger = transport.debugger
        child = subprocess.Popen([str(executable), "0", "1000"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            scale = []
            with phase("fixture.frameworks"):
                for line in child.stdout:
                    name, count = line.strip().rsplit(" ", 1)
                    scale.append({"image": name, "count": int(count)})
                    if name == "READY":
                        break
                else:
                    raise RuntimeError("helper did not become ready: " + child.stderr.read())
            changes = [("symbols.enable-lldb-index-cache", "false"),
                       ("symbols.lldb-index-cache-path", '"' + str(cache) + '"')]
            if variant == "baseline":
                changes.append(("target.preload-symbols", "false"))
            for name, value in changes:
                result = lldb.SBCommandReturnObject()
                debugger.GetCommandInterpreter().HandleCommand("settings set " + name + " " + value, result)
                assert result.Succeeded(), result.GetError()
            transport.target = target = debugger.CreateTarget("")
            settings = {}
            for name in ("symbols.enable-external-lookup", "target.preload-symbols",
                         "target.load-script-from-symbol-file", "symbols.load-on-demand",
                         "target.parallel-module-load", "symbols.enable-lldb-index-cache",
                         "symbols.lldb-index-cache-path", "symbols.shared-cache-binary-loading"):
                result = lldb.SBCommandReturnObject()
                debugger.GetCommandInterpreter().HandleCommand("settings show " + name, result)
                assert result.Succeeded(), result.GetError()
                settings[name] = result.GetOutput().strip()
            assert not list(cache.iterdir()), "worker did not start with an empty private cache"
            error = lldb.SBError()
            with phase("target.firstAttach"):
                started = time.perf_counter()
                transport.process = target.AttachToProcessWithID(transport.listener, child.pid, error)
                attach_seconds = time.perf_counter() - started
            assert error.Success(), str(error)
            transport.pid = child.pid
            stats = lldb.SBCommandReturnObject()
            debugger.GetCommandInterpreter().HandleCommand("statistics dump", stats)
            assert stats.Succeeded(), stats.GetError()
            statistics_dump = json.loads(stats.GetOutput())
            assert statistics_dump["totalSymbolTablesLoadedFromCache"] == 0
            assert statistics_dump["totalSymbolTablesSavedToCache"] == 0
            addresses = {name: symbol_address(target.GetModuleAtIndex(0), target, symbol)
                         for name, symbol in SYMBOLS.items()}
            transport.address = addresses.__getitem__
            transport.mailbox_mode = "lldb"
            expressions = []
            for index in range(3):
                with phase("expression." + str(index)):
                    started = time.perf_counter()
                    result = transport.execute("return true")
                    expressions.append({"total_seconds": time.perf_counter() - started,
                                        "evaluate_seconds": transport.last_expression_duration, "result": result})
                assert result == "{}" and not transport.tainted and transport.focus_original is None
                assert target.GetNumBreakpoints() == 0, "expression leaked a breakpoint"
            transport.stop(time.monotonic() + 3)
            focus = transport.process.ReadMemory(
                addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error,
            )
            assert error.Success() and focus == b"\x01", (str(error), focus)
            entries = transport.process.ReadUnsignedFromMemory(addresses["fixture_pcall_entries"], 4, error)
            assert error.Success() and entries == 3, (str(error), entries)
            row = {"variant": variant, "worker_pid": os.getpid(), "helper_pid": child.pid,
                   "attach_seconds": attach_seconds, "settings": settings, "helper_images": scale,
                   "target_modules": target.GetNumModules(), "statistics": statistics_dump,
                   "expressions": expressions, "native_entries": entries, "focus_restored": True,
                   "python": sys.version, "lldb": lldb.SBDebugger.GetVersionString()}
        finally:
            cleanup(child, debugger, transport)
        assert not list(cache.iterdir()), "disabled private cache acquired files"
        row["private_cache_empty_before_and_after"] = True
        return row


def profile_first_touch():
    environment = dict(os.environ)
    lldb_path = subprocess.check_output(["/usr/bin/xcrun", "lldb", "-P"], text=True).strip()
    environment["PYTHONPATH"] = lldb_path + os.pathsep + environment.get("PYTHONPATH", "")
    trials = []
    for _ in range(5):
        for variant in ("baseline", "production"):
            raw = run_lldb_worker(
                ["/usr/bin/xcrun", "python3", str(Path(__file__).resolve()), "--mode", "first-touch",
                 "--first-touch-worker", variant], environment, timeout=30,
            )
            row = json.loads(raw.splitlines()[-1])
            row["phases"] = [json.loads(line.removeprefix("lldb_phase "))
                             for line in raw.splitlines() if line.startswith("lldb_phase ")]
            trials.append(row)
    return {
        "workload": "5 alternating fresh LLDB workers per variant; Foundation/AppKit/SwiftUI/Metal helper; no game",
        "baseline": "production constructor with only target.preload-symbols overridden to false",
        "cache": "per-worker private empty index-cache directory, cache disabled; OS file caches not purged",
        "trials": trials,
        "metrics": {variant + ".first_attach": summarize([
            row["attach_seconds"] for row in trials if row["variant"] == variant
        ]) for variant in ("baseline", "production")},
    }


def profile_resident(samples, trait_count=32, catalog_trait_count=96, resource_count=32):
    from lua_runtime_support import require_lua52

    lua = require_lua52("offline Hades operation profiling")
    fixture = ROOT / "Tools/fixtures/hades2_operation_profile.lua"
    runtime = SOURCE_ROOT / "Backend/games/hades2/runtime/hades.lua"
    completed = subprocess.run(
        [lua, str(fixture), str(runtime), str(samples), str(trait_count), str(catalog_trait_count), str(resource_count)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    timings = collections.defaultdict(list)
    features = None
    fixture_info = None
    maintenance = []
    for line in completed.stdout.splitlines():
        name, value = line.split("\t", 1)
        if name == "features":
            features = json.loads(value)
        elif name == "fixture":
            fixture_info = json.loads(value)
        elif name == "maintenance":
            maintenance.append(json.loads(value))
        else:
            timings[name].append(float(value))
    if features is None or fixture_info is None:
        raise RuntimeError("resident fixture did not report its verified features and inventory")
    return {
        "workload": "production Lua 5.2 with explicit native stubs and synthetic ordinary God traits; no game engine",
        "clock": "os.clock CPU time; frame samples average 100 UpdateTimers calls",
        "lua": subprocess.check_output([lua, "-v"], stderr=subprocess.STDOUT, text=True).strip(),
        "active_features": features,
        "fixture": fixture_info,
        "maintenance": maintenance,
        "maintenance_boundary": "unmodified frame controls versus instrumented overlapping CPU phases; UI stubs report calls only; owner-transition includes synthetic owner construction",
        "metrics": {name: summarize(values) for name, values in timings.items()},
    }


def positive_integer(value):
    result = int(value)
    if not 1 <= result <= 1000:
        raise argparse.ArgumentTypeError("must be between 1 and 1000")
    return result


def non_negative_integer(value):
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return result


def tool_version(command):
    try:
        return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as error:
        return "unobserved: " + type(error).__name__


def human_summary(report):
    lines = ["Source " + report["source_sha"] + "; harness " + report["harness_sha"],
             "Synthetic/offline evidence; nested phases overlap; engine/render/FPS unobserved. Clean exact HEAD: " + str(report["exact_head_evidence"])]
    for index, trial in enumerate(report.get("end_to_end", []), 1):
        if not trial["observed"]:
            lines.append("Host: " + trial["reason"]); continue
        lines.append("Trial %d sidecar calls %s; bytes %s" % (index, trial["sidecar_calls"], trial["bytes"]))
        for name in ("host.request_queue", "host.payload_decode", "host.payload_apply", "harness.host_round_trip",
                     "backend.routing", "backend.public_projection", "backend.reply_serialize", "backend.reply_ready",
                     "backend.cache_serialize", "backend.cache_materialize", "backend.stdout_serialize",
                     "sidecar.rpc", "resident.materialize_dispatch", "resident.json_serialize", "resident.localization"):
            metric = trial["paths"]["warm"]["phases"].get(name)
            if metric: lines.append("  %s median/p95 %.3f/%.3f ms (%d)" % (name, metric["median_ms"], metric["p95_ms"], metric["count"]))
    for section in ("resident", "save_query", "time_warp", "transport", "first_touch"):
        for name, metric in report.get(section, {}).get("metrics", {}).items():
            lines.append("%s.%s median/p95 %.6f/%.6f ms (%d)" % (section, name, metric["median_ms"], metric["p95_ms"], metric["count"]))
    if "baseline" in report:
        lines.append("Baseline source " + report["baseline"]["source_sha"] + "; pre-probe phases remain unobserved where absent.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("all", "offline", "transport", "first-touch", "resident", "end-to-end", "save", "time-warp"), default="all")
    parser.add_argument("--first-touch-worker", choices=("baseline", "production"), help=argparse.SUPPRESS)
    parser.add_argument("--samples", type=positive_integer, default=30)
    parser.add_argument("--resident-traits", type=non_negative_integer, default=32,
                        help="synthetic mounted ordinary God traits; resident mode only")
    parser.add_argument("--resident-catalog-traits", type=non_negative_integer, default=96,
                        help="synthetic exact-acquisition catalog entries; resident mode only")
    parser.add_argument("--resident-resources", type=positive_integer, default=32)
    parser.add_argument("--save-scenes", type=positive_integer, default=1000)
    parser.add_argument("--trials", type=positive_integer, default=3, help="independent offline Host processes")
    parser.add_argument("--probe-control", action="store_true", help="also run matched end-to-end processes with opt-in probes disabled")
    parser.add_argument("--baseline-ref", help="also measure an immutable git archive of this commit using this harness")
    parser.add_argument("--tick-microseconds", type=int, default=16667,
                        help="temporary helper update cadence; not a game frame rate measurement")
    parser.add_argument("--output", type=Path, help="write full JSON evidence; otherwise print it")
    args = parser.parse_args()
    if args.resident_resources < 2 or args.resident_traits > 512 or args.resident_catalog_traits > 1000 or args.trials > 10:
        parser.error("resources >= 2, traits <= 512, catalog <= 1000 and trials <= 10 are required")
    if args.tick_microseconds < 0:
        parser.error("--tick-microseconds must be non-negative (0 means a busy loop)")
    if args.first_touch_worker:
        print(json.dumps(profile_first_touch_worker(args.first_touch_worker)))
        return

    harness_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    selected_sha = os.environ.get("MGT_PROFILE_SOURCE_SHA", harness_sha)
    from hades2_profile_workloads import profile_end_to_end, profile_save_queries, profile_time_warp
    report = {
        "schema_version": 1,
        "source_sha": selected_sha,
        "harness_sha": harness_sha,
        "source_origin": "git archive" if SOURCE_ROOT != ROOT else "checkout",
        "evidence_thresholds": {
            "low_blast_materiality": "repeated owning-phase sum >= 1 ms and >= 10% of queue-excluded warm operation in every trial; duplicated counts alone remain non-actionable latency evidence",
            "comparison": "same environment/fixtures; at least 3 independent processes and 30 warm samples; baseline/candidate/baseline",
            "cold": "at least 5 fresh processes before a cold-only promotion",
            "interactive_materiality": "phase p95 >= 5 ms and >= 10% of queue-excluded total in all trials; or saving >= 2 ms and >= 10% repeatably",
            "serialization": "canonical serialization changes also require reference-fixture neutrality; bytes/count findings alone motivate investigation, not a speedup claim",
            "steady_state": "measured CPU delta >= 0.1 ms/frame and >= 10% with real target frame/native-call frequency; synthetic CPU alone cannot pass this gate",
            "tail": "p99 is exploratory below 100 samples; timer-floor values do not justify work",
            "safety": "preserve disconnect/outcome-unknown/replay/Save semantics; exact-head behavior checks and independent review",
        },
        "environment": {"python": sys.version, "executable": sys.executable, "machine": platform.machine(), "processor": platform.processor(),
                        "swift": tool_version(["swiftc", "--version"]), "cc": tool_version(["cc", "--version"]),
                        "developer_dir": os.environ.get("DEVELOPER_DIR"),
                        "xcode": tool_version(["/usr/bin/xcodebuild", "-version"]) if sys.platform == "darwin" else None},
        "sha": selected_sha,
        "harness_working_tree_changes": subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        ).splitlines(),
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "source_sha256": {
            name: hashlib.sha256((SOURCE_ROOT / name).read_bytes()).hexdigest()
            for name in ("Backend/core/protocol.py", "Backend/core/server.py", "Backend/core/sidecar.py",
                         "Backend/games/hades2/transport.py", "Backend/games/hades2/runtime/hades.lua",
                         "Backend/games/hades2/resident_session.py", "Backend/games/hades2/save_investigation.py",
                         "Sources/Core/Runtime/BackendClient.swift", "Sources/Core/Runtime/BackendProcess.swift",
                         "Sources/Core/Runtime/TrainerBackendSession.swift", "Native/ProcessTimeWarp/ProcessTimeWarp.c")
        },
    }
    json_decoder = SOURCE_ROOT / "Sources/Core/Runtime/TrainerJSON.swift"
    if json_decoder.exists():
        report["source_sha256"]["Sources/Core/Runtime/TrainerJSON.swift"] = hashlib.sha256(json_decoder.read_bytes()).hexdigest()
    if args.mode in ("all", "transport"):
        if sys.platform != "darwin":
            parser.error("transport profiling needs macOS, Xcode Python and LLDB; use --mode resident on Linux")
        if os.environ.get("MGT_PROFILE_LLDB_EMBEDDED") == "1":
            # Internal child emits only the transport result. No nested debugger
            # interpreter; Xcode Python imports its ABI-matched LLDB extension.
            print(json.dumps(profile_transport(args.samples, args.tick_microseconds)))
            return
        environment = dict(os.environ, MGT_PROFILE_LLDB_EMBEDDED="1")
        raw = run_lldb_worker(
            ["/usr/bin/xcrun", "python3", str(Path(__file__).resolve()),
             "--mode", "transport", "--samples", str(args.samples),
             "--tick-microseconds", str(args.tick_microseconds)],
            environment, 30 + (args.samples + 6) * 4,
        )
        report["transport"] = json.loads(raw)
    if args.mode == "first-touch":
        if sys.platform != "darwin":
            parser.error("first-touch profiling needs macOS, Xcode Python and LLDB")
        report["first_touch"] = profile_first_touch()
    report["working_tree_changes"] = report["harness_working_tree_changes"] if SOURCE_ROOT == ROOT else []
    report["source_clean"] = not report["working_tree_changes"]
    report["exact_head_evidence"] = report["source_clean"] and not report["harness_working_tree_changes"]
    report["harness_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("Tools/profile_hades2_operations.py", "Tools/hades2_profile_workloads.py",
                     "Tools/fixtures/hades2_operation_profile.lua", "Tools/fixtures/hades2_profile_backend.py",
                     "Tools/fixtures/hades2_profile_host.swift", "Tools/fixtures/hades2_time_warp_profile.c",
                     "Backend/core/operation_profile.py", "tests/test_process_time_warp_install_contract.py",
                     "tests/hades2_lldb_fixture.py", "tests/hades2_lldb_worker_support.py",
                     "tests/hades2_resident_session_fakes.py", "tests/lua_runtime_support.py")}
    if args.mode in ("all", "offline", "resident"):
        report["resident"] = profile_resident(args.samples, args.resident_traits, args.resident_catalog_traits, args.resident_resources)
    if args.mode in ("all", "offline", "end-to-end"):
        report["end_to_end"] = [profile_end_to_end(args.samples, args.resident_traits, args.resident_catalog_traits,
            args.resident_resources, summarize, SOURCE_ROOT) for _ in range(args.trials)]
    if args.probe_control and args.mode in ("all", "offline", "end-to-end"):
        report["end_to_end_control"] = [profile_end_to_end(args.samples, args.resident_traits, args.resident_catalog_traits,
            args.resident_resources, summarize, SOURCE_ROOT, probes=False) for _ in range(args.trials)]
    if args.mode in ("all", "offline", "save"):
        report["save_query"] = profile_save_queries(args.samples, args.save_scenes, summarize)
    if args.mode in ("all", "offline", "time-warp"):
        report["time_warp"] = profile_time_warp(args.samples, summarize, SOURCE_ROOT)
    if args.baseline_ref:
        if SOURCE_ROOT != ROOT: parser.error("nested baseline archives are not supported")
        baseline_sha = subprocess.check_output(["git", "rev-parse", args.baseline_ref + "^{commit}"], cwd=ROOT, text=True).strip()
        archive = subprocess.check_output(["git", "archive", baseline_sha], cwd=ROOT)
        with tempfile.TemporaryDirectory(prefix="mgt-profile-baseline-") as temporary:
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                source.extractall(temporary, filter="data")
            environment = dict(os.environ, MGT_PROFILE_SOURCE_ROOT=temporary, MGT_PROFILE_SOURCE_SHA=baseline_sha)
            command = [sys.executable, str(Path(__file__).resolve()), "--mode", args.mode, "--samples", str(args.samples),
                       "--resident-traits", str(args.resident_traits), "--resident-catalog-traits", str(args.resident_catalog_traits),
                       "--resident-resources", str(args.resident_resources), "--save-scenes", str(args.save_scenes),
                       "--trials", str(args.trials), "--tick-microseconds", str(args.tick_microseconds)]
            if args.probe_control: command.append("--probe-control")
            baseline = subprocess.run(command, env=environment, capture_output=True, text=True, check=True, timeout=600)
            report["baseline"] = json.loads(baseline.stdout)
            report["baseline"]["archive_sha256"] = hashlib.sha256(archive).hexdigest()
    ending_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    ending_changes = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    if ending_sha != harness_sha or ending_changes != report["harness_working_tree_changes"]:
        raise SystemExit("source/harness changed during measurement; freeze HEAD and rerun")
    report["summary"] = human_summary(report)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
        print(str(args.output.resolve()))
        print(report["summary"])
        args.output.with_suffix(".summary.txt").write_text(report["summary"] + "\n", encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.stderr.write((error.stdout or "") + (error.stderr or ""))
        raise SystemExit(error.returncode) from error
