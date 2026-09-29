import importlib
import math
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from .adapter import AdapterError


class ProcessTimeWarpError(AdapterError):
    """Core-owned Time Warp failure with a Host presentation identity.

    The backend never knows the active UI language. Every player-facing Time
    Warp failure therefore carries a `host.timeWarp.error.*` key plus optional
    runtime arguments; detailed tool/runtime text stays diagnostic-only.
    """

    PRESENTATION_PREFIX = "host.timeWarp.error."

    def __init__(self, code, presentation, *, diagnostic=None, arguments=()):
        if not isinstance(presentation, str) or not presentation.startswith(self.PRESENTATION_PREFIX):
            raise ValueError("Process Time Warp presentation must use a host.timeWarp.error.* key.")
        super().__init__(
            code,
            presentation,
            diagnostic=diagnostic,
            arguments=arguments,
        )


class ProcessTimeWarpController:
    ABI_VERSION = 1
    MIN_SPEED = 0.0
    MAX_SPEED = 10.0

    def __init__(self, driver, helper_path, image_names):
        self.driver = driver
        self.helper_path = Path(helper_path)
        if not image_names or any(not isinstance(name, str) or not name or "\n" in name or "\0" in name for name in image_names):
            raise ValueError("Time Warp image allowlist is invalid.")
        self.image_payload = "\n".join(image_names).encode("utf-8")
        if len(self.image_payload) >= 1024:
            raise ValueError("Time Warp image allowlist is too long.")
        self._pid = None
        self._installed = False

    @classmethod
    def _validate_speed(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Time Warp speed must be numeric.")
        speed = float(value)
        if not math.isfinite(speed) or not cls.MIN_SPEED <= speed <= cls.MAX_SPEED:
            raise ValueError(f"Time Warp speed must be {cls.MIN_SPEED}..{cls.MAX_SPEED}.")
        return speed

    def _refresh_pid(self):
        pid = self.driver.pid
        if pid != self._pid:
            self._pid = pid
            self._installed = False
        return pid

    def _check_alive(self):
        if not self.driver.is_alive():
            raise ProcessTimeWarpError(
                "disconnected",
                "host.timeWarp.error.disconnected",
                diagnostic="游戏进程已退出或调试连接已断开。",
            )

    @staticmethod
    def _install_error(code):
        if code == -3:
            return ProcessTimeWarpError(
                "time_warp_unsupported",
                "host.timeWarp.error.unsupportedImports",
                diagnostic="所选游戏镜像未导入受支持的单调时钟函数。",
            )
        return ProcessTimeWarpError(
            "time_warp_install_failed",
            "host.timeWarp.error.installFailed",
            arguments=(code,),
            diagnostic=f"Time Warp helper 安装失败（{code}）。",
        )

    def set_speed(self, value):
        speed = self._validate_speed(value)
        self._check_alive()
        self._refresh_pid()

        with self.driver.session():
            if not self.driver.helper_present():
                self.driver.load_helper(self.helper_path)
                self._installed = False

            abi = self.driver.abi()
            if abi != self.ABI_VERSION:
                raise ProcessTimeWarpError(
                    "time_warp_abi_mismatch",
                    "host.timeWarp.error.abiMismatchVersion",
                    arguments=(self.ABI_VERSION, abi),
                    diagnostic=f"Time Warp helper ABI 不兼容（需要 {self.ABI_VERSION}，当前 {abi}）。",
                )

            if not self._installed:
                code = self.driver.install(self.image_payload, speed)
                if code != 0:
                    raise self._install_error(code)
                if self.driver.hook_mask() == 0:
                    raise ProcessTimeWarpError(
                        "time_warp_unsupported",
                        "host.timeWarp.error.noClockBindings",
                        diagnostic="目标镜像没有可用的 Time Warp 时钟绑定。",
                    )
                self._installed = True
            else:
                code = self.driver.set_speed(speed)
                if code != 0:
                    raise ProcessTimeWarpError(
                        "time_warp_set_failed",
                        "host.timeWarp.error.setFailed",
                        arguments=(code,),
                        diagnostic=f"Time Warp 设置失败（{code}）。",
                    )

            actual = self.driver.get_speed()
            if not math.isfinite(actual) or abs(actual - speed) > 0.000001:
                raise ProcessTimeWarpError(
                    "time_warp_verify_failed",
                    "host.timeWarp.error.verifyFailed",
                    arguments=(f"{speed:g}", f"{actual:g}"),
                    diagnostic=f"Time Warp 设置校验失败（目标 {speed:g}，实际 {actual:g}）。",
                )
            return actual

    def current_speed(self):
        if not self.driver.is_alive() or not self.driver.helper_present():
            return 1.0
        self._refresh_pid()
        with self.driver.session():
            if self.driver.abi() != self.ABI_VERSION:
                raise ProcessTimeWarpError(
                    "time_warp_abi_mismatch",
                    "host.timeWarp.error.abiMismatch",
                    diagnostic="Time Warp helper ABI 不兼容。",
                )
            return self.driver.get_speed()

    def reset(self):
        if not self.driver.is_alive():
            self._pid = None
            self._installed = False
            return 1.0
        self._refresh_pid()
        if not self._installed and not self.driver.helper_present():
            return 1.0
        return self.set_speed(1.0)


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
                diagnostic="调试连接状态不明；请先重启后端或重新连接游戏。",
            )
        lldb = self._lldb()
        process = self.transport.process
        if process is None:
            raise ProcessTimeWarpError(
                "disconnected",
                "host.timeWarp.error.disconnected",
                diagnostic="调试进程不存在。",
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
                    diagnostic="调试目标不存在。",
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
            detail = "未找到" if not addresses else "匹配不唯一"
            raise ProcessTimeWarpError(
                "time_warp_symbol",
                "host.timeWarp.error.symbolUnavailable",
                arguments=(name, detail),
                diagnostic=f"Time Warp 导出符号 {name} {detail}。",
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
                diagnostic=f"Time Warp helper 不存在：{path}",
            )
        lldb = self._lldb()
        error = lldb.SBError()
        token = self.transport.process.LoadImage(lldb.SBFileSpec(str(path)), error)
        if error.Fail() or token == lldb.LLDB_INVALID_IMAGE_TOKEN:
            raise ProcessTimeWarpError(
                "time_warp_load_failed",
                "host.timeWarp.error.loadFailed",
                arguments=(str(error),),
                diagnostic="Time Warp helper 加载失败：" + str(error),
            )
        if not self.helper_present():
            raise ProcessTimeWarpError(
                "time_warp_load_failed",
                "host.timeWarp.error.loadedSymbolsMissing",
                diagnostic="Time Warp helper 已加载但导出符号不可见。",
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
            diagnostic="暂停后找不到可执行 Time Warp 调用的线程。",
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
                    diagnostic="Time Warp 修改结果不明，未自动重试；请重启后端或重新连接游戏：" + str(result.GetError()),
                )
            raise ProcessTimeWarpError(
                "time_warp_call_failed",
                "host.timeWarp.error.callFailed",
                arguments=(str(result.GetError()),),
                diagnostic="Time Warp helper 调用失败：" + str(result.GetError()),
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
                diagnostic="无法为 Time Warp image allowlist 分配目标内存。",
            )
        try:
            payload = image_names + b"\0"
            count = process.WriteMemory(scratch, payload, error)
            if error.Fail() or count != len(payload):
                raise ProcessTimeWarpError(
                    "time_warp_memory",
                    "host.timeWarp.error.memoryWriteFailed",
                    diagnostic="无法写入 Time Warp image allowlist。",
                )
            address = self._export_address("MGTTimeWarpInstall")
            return self._evaluate_int(
                f"((int(*)(const char*,unsigned long,double)){address})"
                f"((const char*){scratch},{len(image_names)},{speed:.17g})",
                mutation=True,
            )
        finally:
            process.DeallocateMemory(scratch)
