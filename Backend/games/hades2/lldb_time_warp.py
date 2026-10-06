"""Hades II LLDB driver for the Core-owned Process Time Warp controller."""
from __future__ import annotations

import importlib
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from core.process_time_warp import ProcessTimeWarpError


class LLDBProcessTimeWarpDriver:
    def __init__(self, transport, lldb_module=None):
        self.transport = transport
        self._lldb_module = lldb_module

    @property
    def pid(self):
        return self.transport.pid

    def is_alive(self):
        return bool(self.transport.alive())

    def _lldb(self):
        if self._lldb_module is not None:
            return self._lldb_module
        try:
            module = importlib.import_module("lldb")
        except ImportError:
            path = subprocess.check_output(['/usr/bin/xcrun', 'lldb', '-P'], text=True, shell=False).strip()
            if path and path not in sys.path:
                sys.path.insert(0, path)
            module = importlib.import_module("lldb")
        self._lldb_module = module
        return module

    @contextmanager
    def session(self):
        if getattr(self.transport, 'tainted', False):
            raise ProcessTimeWarpError(
                "restart_required",
                "host.timeWarp.error.restartRequired",
                diagnostic="Debugger connection state is unknown; restart the backend or reconnect to the game.",
            )
        lldb = self._lldb()
        process = self.transport.process
        if process is None:
            raise ProcessTimeWarpError(
                "disconnected",
                "host.timeWarp.error.disconnected",
                diagnostic="Debugger process is unavailable.",
            )
        state = process.GetState()
        resume_after = state != lldb.eStateStopped
        self.transport.stop(time.monotonic() + 3)
        try:
            yield
        finally:
            if resume_after and self.transport.process is not None and self.transport.alive():
                self.transport.resume(time.monotonic() + 3)

    def _export_address(self, name, required=True):
        lldb = self._lldb()
        target = self.transport.target
        if target is None:
            if required:
                raise ProcessTimeWarpError(
                    "disconnected",
                    "host.timeWarp.error.disconnected",
                    diagnostic="Debugger target is unavailable.",
                )
            return None
        addresses = set()
        for index in range(target.GetNumModules()):
            module = target.GetModuleAtIndex(index)
            for candidate in (name, "_" + name):
                symbol = module.FindSymbol(candidate, lldb.eSymbolTypeCode)
                if not symbol.IsValid():
                    continue
                address = symbol.GetStartAddress().GetLoadAddress(target)
                if address not in (0, lldb.LLDB_INVALID_ADDRESS):
                    addresses.add(address)
        if len(addresses) == 1:
            return addresses.pop()
        if required:
            detail = "not found" if not addresses else "resolved ambiguously"
            raise ProcessTimeWarpError(
                "time_warp_symbol",
                "host.timeWarp.error.symbolUnavailable",
                arguments=(name,),
                diagnostic=f"Time Warp export {name} was {detail}.",
            )
        return None

    def helper_present(self):
        if getattr(self.transport, "target", None) is None:
            return False
        return self._export_address("MGTTimeWarpABI", required=False) is not None

    def load_helper(self, path):
        path = Path(path)
        if not path.is_file():
            raise ProcessTimeWarpError(
                "time_warp_helper_missing",
                "host.timeWarp.error.helperMissing",
                arguments=(str(path),),
                diagnostic=f"Time Warp helper is missing: {path}",
            )
        lldb = self._lldb()
        error = lldb.SBError()
        token = self.transport.process.LoadImage(lldb.SBFileSpec(str(path)), error)
        if error.Fail() or token == lldb.LLDB_INVALID_IMAGE_TOKEN:
            raise ProcessTimeWarpError(
                "time_warp_load_failed",
                "host.timeWarp.error.loadFailed",
                arguments=(str(error),),
                diagnostic="Time Warp helper load failed: " + str(error),
            )
        if not self.helper_present():
            raise ProcessTimeWarpError(
                "time_warp_load_failed",
                "host.timeWarp.error.loadedSymbolsMissing",
                diagnostic="Time Warp helper loaded but its exported symbols are unavailable.",
            )

    def _frame(self):
        process = self.transport.process
        thread = process.GetSelectedThread()
        if thread.IsValid() and thread.GetNumFrames() > 0:
            return thread.GetFrameAtIndex(0)
        for thread in process:
            if thread.IsValid() and thread.GetNumFrames() > 0:
                return thread.GetFrameAtIndex(0)
        raise ProcessTimeWarpError(
            "time_warp_call_failed",
            "host.timeWarp.error.noCallableThread",
            diagnostic="No callable thread is available while the target is paused.",
        )

    def _evaluate_int(self, expression, *, mutation=False):
        lldb = self._lldb()
        options = lldb.SBExpressionOptions()
        options.SetLanguage(lldb.eLanguageTypeC_plus_plus)
        options.SetTimeoutInMicroSeconds(2000000)
        options.SetIgnoreBreakpoints(True)
        options.SetUnwindOnError(True)
        result = self._frame().EvaluateExpression(expression, options)
        if result.GetError().Fail():
            if mutation:
                self.transport.tainted = True
                raise ProcessTimeWarpError(
                    "outcome_unknown",
                    "host.timeWarp.error.outcomeUnknown",
                    arguments=(str(result.GetError()),),
                    diagnostic="Time Warp mutation outcome is unknown; no retry was attempted. Restart the backend or reconnect: " + str(result.GetError()),
                )
            raise ProcessTimeWarpError(
                "time_warp_call_failed",
                "host.timeWarp.error.callFailed",
                arguments=(str(result.GetError()),),
                diagnostic="Time Warp helper call failed: " + str(result.GetError()),
            )
        return result.GetValueAsSigned()

    def abi(self):
        address = self._export_address("MGTTimeWarpABI")
        return self._evaluate_int(f"((unsigned int(*)(void)){address})()")

    def hook_mask(self):
        address = self._export_address("MGTTimeWarpHookMask")
        return self._evaluate_int(f"((unsigned int(*)(void)){address})()")

    def get_speed(self):
        address = self._export_address("MGTTimeWarpGetSpeed")
        scaled = self._evaluate_int(f"(long long)((((double(*)(void)){address})()) * 1000000.0)")
        return scaled / 1000000.0

    def set_speed(self, speed):
        address = self._export_address("MGTTimeWarpSetSpeed")
        return self._evaluate_int(f"((int(*)(double)){address})({speed:.17g})", mutation=True)

    def install(self, image_names, speed):
        lldb = self._lldb()
        process = self.transport.process
        error = lldb.SBError()
        scratch = process.AllocateMemory(
            len(image_names) + 1,
            lldb.ePermissionsReadable | lldb.ePermissionsWritable,
            error,
        )
        if error.Fail() or not scratch:
            raise ProcessTimeWarpError(
                "time_warp_memory",
                "host.timeWarp.error.memoryAllocationFailed",
                diagnostic="Unable to allocate target memory for the Time Warp image allowlist.",
            )
        try:
            payload = image_names + b"\0"
            count = process.WriteMemory(scratch, payload, error)
            if error.Fail() or count != len(payload):
                raise ProcessTimeWarpError(
                    "time_warp_memory",
                    "host.timeWarp.error.memoryWriteFailed",
                    diagnostic="Unable to write the Time Warp image allowlist.",
                )
            address = self._export_address("MGTTimeWarpInstall")
            return self._evaluate_int(
                f"((int(*)(const char*,unsigned long,double)){address})"
                f"((const char*){scratch},{len(image_names)},{speed:.17g})",
                mutation=True,
            )
        finally:
            process.DeallocateMemory(scratch)

