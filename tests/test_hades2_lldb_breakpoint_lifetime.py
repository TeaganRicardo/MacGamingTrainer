import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from hades2_lldb_worker_support import run_lldb_worker

# GitHub's runner Python is not ABI-matched to Xcode's private _lldb
# extension. Run the regression under the same Xcode Python + LLDB module path
# used by the production Hades sidecar. Do not nest a second SBDebugger inside
# LLDB's own command-interpreter Python: that re-entrant harness can deadlock.
if os.environ.get("MGT_LLDB_EMBEDDED_TEST") != "1":
    path = str(Path(__file__).resolve())
    environment = dict(os.environ)
    environment["MGT_LLDB_EMBEDDED_TEST"] = "1"
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
        stdout = run_lldb_worker(
            ["/usr/bin/xcrun", "python3", path],
            environment,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(
            "Xcode-Python LLDB breakpoint-lifetime regression exceeded 30 seconds"
        ) from error
    except subprocess.CalledProcessError as error:
        raise AssertionError(
            "Xcode-Python LLDB regression failed:\n"
            + (error.stdout or "") + (error.stderr or "")
        ) from error
    if "hades2_lldb_breakpoint_lifetime_ok" not in stdout:
        raise AssertionError(
            "Xcode-Python LLDB regression failed:\n"
            + stdout
        )
    print("hades2_lldb_breakpoint_lifetime_ok")
    raise SystemExit(0)

sys.path.insert(0, str(ROOT / "Backend"))

from hades2_lldb_fixture import (
    HELPER_SOURCE, TransportError, attach_helper, cleanup, lldb,
)


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
    # before EvaluateExpression. Hold pcall until LLDB unwinds it: a finite slow
    # call can finish before an overloaded debugger delivers its halt, which is
    # a valid known completion rather than an unknown outcome. The native entry
    # marker proves this case actually crossed into pcall before interruption.
    child, debugger, transport, addresses = attach_helper(executable, -1)
    try:
        try:
            transport.execute("return true", expression_timeout_seconds=0.1)
        except TransportError as error:
            assert error.code == "outcome_unknown", error.code
            message = str(error).lower()
            assert "deleted" not in message, message
        else:
            raise AssertionError("blocked expression unexpectedly completed")
        assert transport.tainted is True
        assert transport.target.GetNumBreakpoints() == 0, "timeout path leaked a breakpoint"
        transport.stop(time.monotonic() + 2)
        error = lldb.SBError()
        entered = transport.process.ReadUnsignedFromMemory(addresses["fixture_pcall_entries"], 4, error)
        assert error.Success() and entered == 1, (str(error), entered)
        focus = transport.process.ReadMemory(
            addresses["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"], 1, error
        )
        assert error.Success() and focus == b"\x01", (str(error), focus)
        transport.resume(time.monotonic() + 2)
        try:
            transport.execute("return true")
        except TransportError as error:
            assert error.code == "restart_required", error.code
        else:
            raise AssertionError("tainted transport allowed a second native call")
    finally:
        cleanup(child, debugger, transport)

print("hades2_lldb_breakpoint_lifetime_ok")
