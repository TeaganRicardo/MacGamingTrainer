import os
import mmap
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from hades2_lldb_worker_support import run_lldb_worker, phase, worker_failure_output
from hades2_debugserver_owner import _AuditToken, DarwinProcesses


def observe_supported_rosetta_once():
    """Diagnostic-PR-only comparison for #565; this branch is not for merging."""
    from argparse import Namespace
    from contextlib import redirect_stderr, redirect_stdout
    import hashlib
    import signal
    import traceback
    import hades_rosetta_diagnostic as diagnostic

    diagnostic_path = Path(diagnostic.__file__).resolve()
    diagnostic_sha = hashlib.sha256(diagnostic_path.read_bytes()).hexdigest()
    assert diagnostic_sha == "e7315084f16348a2d17b620228d7c6600a9831c1b50bbceb16018f10e7e42d01", (
        "The comparison must use the unchanged RDC diagnostic", diagnostic_sha,
    )
    # Run only the frozen probe's parent here. It launches its own Xcode-Python
    # worker and owns the default Rosetta server through Darwin audit identity.
    # run_lldb_worker(xcode_lldb=True) would force a different SDK server.
    # Its preparation has 15s compile, 5s discovery and six 5s identity bounds;
    # its worker keeps the original 30s bound and cleanup its two 2s bounds.
    # An exceptional outer overrun raises in Python so that parent's finally
    # still performs its audit-token cleanup; never SIGKILL the parent first.
    parent_budget_seconds = 100

    def parent_deadline(_signum, _frame):
        raise TimeoutError("Rosetta diagnostic parent exceeded its 100-second envelope")

    with tempfile.TemporaryDirectory(prefix="mgt-565-ci-observation-") as temporary:
        directory = Path(temporary)
        observation = directory / "observation"
        parent_stdout = directory / "parent.stdout"
        parent_stderr = directory / "parent.stderr"
        print("rosetta565.begin " + json.dumps({
            "purpose": "One synthetic translated attach and first Hades execute; no real game acceptance",
            "probe_sha256": diagnostic_sha, "iterations": 1,
            "worker_timeout_seconds": 30, "parent_budget_seconds": parent_budget_seconds,
            "ci": {key: os.environ.get(key) for key in (
                "HEAD_SHA", "RUNNER_ARCH", "MGT_MACOS_RUNNER_LABEL", "DEVELOPER_DIR",
            )},
        }), flush=True)
        result = None
        try:
            with parent_stdout.open("w") as output, parent_stderr.open("w") as errors, \
                    redirect_stdout(output), redirect_stderr(errors):
                if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
                    raise RuntimeError("Rosetta diagnostic cannot replace an existing parent timer")
                previous_handler = signal.signal(signal.SIGALRM, parent_deadline)
                signal.setitimer(signal.ITIMER_REAL, parent_budget_seconds)
                try:
                    result = diagnostic.parent(Namespace(
                        repo=ROOT, output=observation, iterations=1,
                        timeout=30, scenario="normal",
                    ))
                except BaseException:
                    traceback.print_exc()
                    raise
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, previous_handler)
        finally:
            # The existing PR lane retains its console, not diagnostic artifacts,
            # and deletes its temporary tree. Emit complete textual traces and
            # their byte hashes before cleanup, including setup/attach failures.
            # Prefix every line so packet data cannot become a workflow command.
            evidence = [parent_stdout, parent_stderr] + [observation / name for name in (
                "environment.json", "summary.json", "operations.jsonl",
                "owned-servers.json", "worker-go", "server-owned", "attached",
                "worker.stdout", "worker.stderr", "gdb-remote.log", "lldb-process.log",
            )]
            for path in evidence:
                if not path.is_file():
                    print(f"rosetta565.file {path.name}: <not written>", flush=True)
                    continue
                data = path.read_bytes()
                print("rosetta565.file " + json.dumps({
                    "name": path.name, "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }), flush=True)
                for line in data.decode("utf-8", errors="backslashreplace").splitlines():
                    print(f"rosetta565[{path.name}] {line}", flush=True)
            print("rosetta565.end " + json.dumps({"returncode": result}), flush=True)
        if result != 0:
            raise AssertionError(f"Rosetta diagnostic failed ({result}); retained evidence is in the PR log")


# GitHub's runner Python is not ABI-matched to Xcode's private _lldb
# extension. Run the regression under the same Xcode Python + LLDB module path
# used by the production Hades sidecar. Do not nest a second SBDebugger inside
# LLDB's own command-interpreter Python: that re-entrant harness can deadlock.
if os.environ.get("MGT_LLDB_EMBEDDED_TEST") != "1":
    # Exercise actual Darwin token-bound cleanup with an ordinary native binary
    # before the debugger scenarios. Each disposable child deliberately starts
    # a new session, matching debugserver's ownership escape.
    cleanup_worker = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from hades2_debugserver_owner import DarwinProcesses
executable = Path(os.environ['LLDB_DEBUGSERVER_PATH']).resolve()
child = subprocess.Popen([str(executable)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, start_new_session=True)
try:
    if child.stdout.readline().strip() != 'ready':
        raise RuntimeError('native cleanup fixture exited before readiness: ' + str(child.poll()))
    tokens = [token for token in DarwinProcesses().matching(executable) if token[5] == child.pid]
    if len(tokens) != 1:
        raise RuntimeError('ready cleanup fixture is absent from its lifetime inventory')
    token = tokens[0]
    record = json.dumps({'token': list(token), 'executable': str(executable)})
    Path(sys.argv[2]).write_text(record)
    print(record, flush=True)
    print('phase=escaped.native.ready', file=sys.stderr, flush=True)
except BaseException:
    child.kill()
    child.wait()
    raise
mode = sys.argv[3]
if mode == 'success':
    raise SystemExit(0)
if mode == 'failure':
    raise SystemExit(7)
if mode == 'interrupt':
    os.kill(os.getppid(), signal.SIGINT)
time.sleep(60)
'''
    processes = DarwinProcesses()
    with tempfile.TemporaryDirectory(prefix='mgt-debugserver-cleanup-contract-') as directory:
        directory = Path(directory)
        # Relocated protected system binaries can be killed before main on
        # macOS. Build our own native fixture and observe its readiness; the
        # copied SDK debugserver remains covered by the LLDB scenarios below.
        native_source = directory / 'cleanup_fixture.c'
        native_source.write_text('''#include <stdio.h>
#include <unistd.h>
int main(void) {
    puts("ready");
    fflush(stdout);
    sleep(60);
    return 0;
}
''')
        native_executable = directory / 'cleanup_fixture'
        subprocess.run(
            ['/usr/bin/xcrun', 'clang', str(native_source), '-o', str(native_executable)],
            check=True, capture_output=True, text=True, timeout=15,
        )
        probe = directory / 'worker.py'
        probe.write_text(cleanup_worker)
        with subprocess.Popen(['/bin/sleep', '60'], start_new_session=True) as unrelated:
            try:
                for mode in ('success', 'failure', 'timeout', 'interrupt'):
                    record_path = directory / (mode + '.json')
                    try:
                        output = run_lldb_worker(
                            [sys.executable, str(probe), str(ROOT / 'tests'), str(record_path), mode],
                            dict(os.environ), timeout=2, debugserver_path=native_executable,
                        )
                    except subprocess.TimeoutExpired as error:
                        assert mode == 'timeout', worker_failure_output(error)
                        assert 'phase=escaped.native.ready' in worker_failure_output(error)
                    except subprocess.CalledProcessError as error:
                        assert mode == 'failure' and error.returncode == 7, worker_failure_output(error)
                        assert 'phase=escaped.native.ready' in worker_failure_output(error)
                    except KeyboardInterrupt:
                        assert mode == 'interrupt'
                    else:
                        assert mode == 'success' and json.loads(output)['token']
                    record = json.loads(record_path.read_text())
                    token = _AuditToken(*record['token'])
                    assert processes.path(token) is None, 'escaped native session survived worker cleanup'
                    assert not Path(record['executable']).parent.exists(), 'confirmed cleanup retained its private copy'
                    assert unrelated.poll() is None, 'cleanup signaled an unrelated executable'
            finally:
                unrelated.kill()
                unrelated.wait()
    path = str(Path(__file__).resolve())
    environment = dict(os.environ)
    environment["MGT_LLDB_EMBEDDED_TEST"] = "1"
    # These contracts use independent targets and do not share native state.
    # Give each its own bounded worker instead of making a later contract
    # inherit compilation, debugger startup and earlier scenarios' elapsed time.
    for scenario in ("startup", "expressions", "detach", "unknown"):
        environment["MGT_LLDB_LIFECYCLE_SCENARIO"] = scenario
        try:
            with phase('worker.run.' + scenario):
                stdout = run_lldb_worker(
                    ["/usr/bin/xcrun", "python3", path],
                    environment,
                    timeout=30,
                    diagnostics=True,
                    xcode_lldb=True,
                )
        except subprocess.TimeoutExpired as error:
            raise AssertionError(
                f"Xcode-Python LLDB {scenario} regression exceeded 30 seconds:\n"
                + worker_failure_output(error)
            ) from error
        except subprocess.CalledProcessError as error:
            raise AssertionError(
                f"Xcode-Python LLDB {scenario} regression failed:\n"
                + worker_failure_output(error)
            ) from error
        if f"hades2_lldb_breakpoint_lifetime_{scenario}_ok" not in stdout:
            raise AssertionError(
                f"Xcode-Python LLDB {scenario} regression failed:\n" + stdout
            )
        print(stdout, end='')
    observe_supported_rosetta_once()
    print("hades2_lldb_breakpoint_lifetime_ok")
    raise SystemExit(0)

sys.path.insert(0, str(ROOT / "Backend"))

with phase('worker.importNativeModules'):
    from hades2_lldb_fixture import (
        HELPER_SOURCE, TransportError, attach_helper, cleanup, lldb,
    )
    from debugger.lldb_time_warp import LLDBProcessTimeWarpDriver

PROGRESS_SOURCE = r"""
#include <fcntl.h>
#include <sys/mman.h>

static void *record_progress(void *value) {
  volatile uint64_t *counter = value;
  for (;;) { ++*counter; usleep(1000); }
  return 0;
}

__attribute__((constructor)) static void start_progress(void) {
  const char *path = getenv("MGT_LLDB_FIXTURE_PROGRESS");
  if (!path) return;
  int fd = open(path, O_RDWR);
  if (fd < 0) abort();
  void *counter = mmap(0, sizeof(uint64_t), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
  close(fd);
  if (counter == MAP_FAILED) abort();
  pthread_t worker;
  if (pthread_create(&worker, 0, record_progress, counter)) abort();
}

unsigned int MGTTimeWarpABI(void) { return 1; }
"""


def assert_progress(counter):
    # Read independently of LLDB: an alive child and eStateDetached do not prove
    # the target runs. Observe the full window to catch a delayed stop signal.
    previous = int.from_bytes(counter[:], sys.byteorder)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        time.sleep(.2)
        current = int.from_bytes(counter[:], sys.byteorder)
        assert current > previous, "detached target stopped making native progress"
        previous = current


def check_startup(executable, progress):
    child, debugger, transport, _addresses = attach_helper(executable, 0, diagnostics=True)
    try:
        assert any(thread.GetName() == "MainThread" for thread in transport.process), (
            "fixture attached before its main thread initialized",
            [thread.GetName() for thread in transport.process],
        )
        transport.detach()
        assert_progress(progress)
    finally:
        cleanup(child, debugger, transport, diagnostics=True)


def check_expressions(executable, progress):
    child, debugger, transport, addresses = attach_helper(executable, 0, diagnostics=True)
    try:
        configuration = lldb.SBCommandReturnObject()
        debugger.GetCommandInterpreter().HandleCommand(
            'settings show target.preload-symbols', configuration,
        )
        assert configuration.Succeeded(), configuration.GetError()
        assert configuration.GetOutput().strip() == 'target.preload-symbols (boolean) = true', (
            'fresh targets must preload symbol indexes before serial runtime discovery',
            configuration.GetOutput(),
        )
        # Repeated operations must leave no pending stop signal, breakpoint or
        # focus change. Verify native entry counts rather than a timing bound or
        # the debugger primitive used to pause the target.
        for index in range(8):
            with phase(f'expression.success.{index}'):
                assert transport.execute("return true", expression_timeout_seconds=1.0) == "{}"
            assert transport.process.GetState() == lldb.eStateRunning
            assert transport.target.GetNumBreakpoints() == 0, "successful expression leaked a breakpoint"
            with phase(f'target.stop.{index}'):
                transport.stop(time.monotonic() + 2)
            stop_id = transport.process.GetStopID()
            with phase(f'target.alreadyStopped.{index}'):
                transport.stop(time.monotonic() + 2)
            assert transport.process.GetStopID() == stop_id, "already stopped target stopped again"
            error = lldb.SBError()
            focus = transport.process.ReadMemory(
                addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error
            )
            assert error.Success() and focus == b"\x01", (str(error), focus)
            entered = transport.process.ReadUnsignedFromMemory(addresses["fixture_pcall_entries"], 4, error)
            assert error.Success() and entered == index + 1, (str(error), entered)
            with phase(f'target.resume.{index}'):
                transport.resume(time.monotonic() + 2)
        # Time Warp calls expressions at the signal stop itself, without Lua's
        # subsequent World::Update breakpoint. Exercise that direct consumer.
        driver = LLDBProcessTimeWarpDriver(transport, lldb_module=lldb)
        with phase('expression.timeWarpRunning'), driver.session():
            assert driver.abi() == 1
        assert transport.process.GetState() == lldb.eStateRunning
        with phase('timeWarp.stop'):
            transport.stop(time.monotonic() + 2)
        with phase('expression.timeWarpStopped'), driver.session():
            assert driver.abi() == 1
        assert transport.process.GetState() == lldb.eStateStopped
        with phase('timeWarp.resume'):
            transport.resume(time.monotonic() + 2)
        process = transport.process
        with phase('target.detach'):
            transport.detach()
        assert process.GetState() == lldb.eStateDetached
        assert child.poll() is None, "detach terminated the target"
        assert transport.process is None and transport.pid is None
        with phase('target.detachedProgress'):
            assert_progress(progress)
    finally:
        cleanup(child, debugger, transport, diagnostics=True)


def check_detach(executable, progress):
    # Repeated fresh targets cover detach from both running and already stopped
    # sessions without using reattach itself as the liveness observer.
    for index in range(8):
        child, debugger, transport, addresses = attach_helper(executable, 0, diagnostics=True)
        try:
            with phase(f'detachCycle.resume.{index}'):
                transport.resume(time.monotonic() + 2)
            if index % 2 == 0:
                with phase(f'detachCycle.stop.{index}'):
                    transport.stop(time.monotonic() + 2)
            with phase(f'detachCycle.detach.{index}'):
                transport.detach()
            with phase(f'detachCycle.progress.{index}'):
                assert_progress(progress)
        finally:
            cleanup(child, debugger, transport, diagnostics=True)


def check_unknown(executable, _progress):
    # This case has no independent progress thread, matching its original
    # single-threaded held-native-call fixture.
    del os.environ["MGT_LLDB_FIXTURE_PROGRESS"]

    # Before the transport fix, this production execute() path failed with
    # "breakpoint N which has been deleted": boundary() deleted the stop reason
    # before EvaluateExpression. Hold pcall until LLDB unwinds it: a finite slow
    # call can finish before an overloaded debugger delivers its halt, which is
    # a valid known completion rather than an unknown outcome. The native entry
    # marker proves this case actually crossed into pcall before interruption.
    child, debugger, transport, addresses = attach_helper(executable, -1, diagnostics=True)
    try:
        try:
            with phase('expression.blocked'):
                transport.execute("return true", expression_timeout_seconds=0.1)
        except TransportError as error:
            assert error.code == "outcome_unknown", error.code
            message = str(error).lower()
            assert "deleted" not in message, message
        else:
            raise AssertionError("blocked expression unexpectedly completed")
        assert transport.tainted is True
        assert transport.target.GetNumBreakpoints() == 0, "timeout path leaked a breakpoint"
        with phase('blockedExpression.stop'):
            transport.stop(time.monotonic() + 2)
        error = lldb.SBError()
        entered = transport.process.ReadUnsignedFromMemory(addresses["fixture_pcall_entries"], 4, error)
        assert error.Success() and entered == 1, (str(error), entered)
        focus = transport.process.ReadMemory(
            addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error
        )
        assert error.Success() and focus == b"\x01", (str(error), focus)
        with phase('blockedExpression.resume'):
            transport.resume(time.monotonic() + 2)
        try:
            with phase('expression.taintedRefusal'):
                transport.execute("return true")
        except TransportError as error:
            assert error.code == "restart_required", error.code
        else:
            raise AssertionError("tainted transport allowed a second native call")
    finally:
        cleanup(child, debugger, transport, diagnostics=True)

scenario = os.environ["MGT_LLDB_LIFECYCLE_SCENARIO"]
check = {"startup": check_startup, "expressions": check_expressions, "detach": check_detach, "unknown": check_unknown}[scenario]

with tempfile.TemporaryDirectory(prefix="mgt-lldb-breakpoint-lifetime-") as temporary:
    temporary = Path(temporary)
    source = temporary / "helper.c"
    executable = temporary / "helper"
    startup_delay = """
__attribute__((constructor)) static void delay_fixture_startup(void) {
  usleep(500000);
}
""" if scenario == "startup" else ""
    source.write_text(HELPER_SOURCE + PROGRESS_SOURCE + startup_delay, encoding="utf-8")
    with phase('fixture.compile'):
        subprocess.run(
            ["/usr/bin/clang", "-g", "-O0", "-pthread", str(source), "-o", str(executable)],
            check=True,
            capture_output=True,
            text=True,
        )

    progress_path = temporary / "progress"
    progress_path.write_bytes(bytes(8))
    os.environ["MGT_LLDB_FIXTURE_PROGRESS"] = str(progress_path)
    with progress_path.open("r+b") as progress_file, mmap.mmap(progress_file.fileno(), 8) as progress:
        check(executable, progress)

print(f"hades2_lldb_breakpoint_lifetime_{scenario}_ok")
