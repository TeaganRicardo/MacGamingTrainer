import os
import mmap
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from hades2_lldb_worker_support import run_lldb_worker, phase, worker_failure_output

# GitHub's runner Python is not ABI-matched to Xcode's private _lldb
# extension. Run the regression under the same Xcode Python + LLDB module path
# used by the production Hades sidecar. Do not nest a second SBDebugger inside
# LLDB's own command-interpreter Python: that re-entrant harness can deadlock.
if os.environ.get("MGT_LLDB_EMBEDDED_TEST") != "1":
    path = str(Path(__file__).resolve())
    environment = dict(os.environ)
    environment["MGT_LLDB_EMBEDDED_TEST"] = "1"
    with phase('environment.lldbPythonPath'):
        lldb_python_path = subprocess.check_output(
            ["/usr/bin/xcrun", "lldb", "-P"],
            text=True,
        ).strip()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        lldb_python_path
        if not existing_pythonpath
        else lldb_python_path + os.pathsep + existing_pythonpath
    )
    try:
        with phase('worker.run'):
            stdout = run_lldb_worker(
                ["/usr/bin/xcrun", "python3", path],
                environment,
                timeout=30,
                diagnostics=True,
            )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            "Xcode-Python LLDB breakpoint-lifetime regression exceeded 30 seconds:\n"
            + worker_failure_output(error)
        ) from error
    except subprocess.CalledProcessError as error:
        raise AssertionError(
            "Xcode-Python LLDB regression failed:\n"
            + worker_failure_output(error)
        ) from error
    if "hades2_lldb_breakpoint_lifetime_ok" not in stdout:
        raise AssertionError(
            "Xcode-Python LLDB regression failed:\n"
            + stdout
        )
    print(stdout, end='')
    raise SystemExit(0)

sys.path.insert(0, str(ROOT / "Backend"))

with phase('worker.importNativeModules'):
    from hades2_lldb_fixture import (
        HELPER_SOURCE, TransportError, attach_helper, cleanup, lldb,
    )
    from games.hades2.lldb_time_warp import LLDBProcessTimeWarpDriver

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


with tempfile.TemporaryDirectory(prefix="mgt-lldb-breakpoint-lifetime-") as temporary:
    temporary = Path(temporary)
    source = temporary / "helper.c"
    executable = temporary / "helper"
    source.write_text(HELPER_SOURCE + PROGRESS_SOURCE, encoding="utf-8")
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
    progress_file = progress_path.open("r+b")
    progress = mmap.mmap(progress_file.fileno(), 8)
    child, debugger, transport, addresses = attach_helper(executable, 0, diagnostics=True)
    try:
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

    progress.close()
    progress_file.close()
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

print("hades2_lldb_breakpoint_lifetime_ok")
