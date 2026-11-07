import math
from pathlib import Path

from .adapter import HostPresentationError


class ProcessTimeWarpError(HostPresentationError):
    """Core-owned Time Warp failure with a Host presentation identity.

    The backend never knows the active UI language. Every player-facing Time
    Warp failure therefore carries a `host.timeWarp.error.*` key plus optional
    runtime arguments; detailed tool/runtime text stays diagnostic-only.
    """

    PRESENTATION_PREFIX = "host.timeWarp.error."


class ProcessTimeWarpController:
    ABI_VERSION = 2
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

    @classmethod
    def _validate_speed(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Time Warp speed must be numeric.")
        speed = float(value)
        if not math.isfinite(speed) or not cls.MIN_SPEED <= speed <= cls.MAX_SPEED:
            raise ValueError(f"Time Warp speed must be {cls.MIN_SPEED}..{cls.MAX_SPEED}.")
        return speed

    def _check_alive(self):
        if not self.driver.is_alive():
            raise ProcessTimeWarpError(
                "disconnected",
                "host.timeWarp.error.disconnected",
                diagnostic="游戏进程已退出或调试连接已断开。",
            )

    @staticmethod
    def _install_error(code):
        if code == -7:
            return ProcessTimeWarpError(
                "restart_required", "host.timeWarp.error.partialInstall",
                diagnostic="Some Time Warp clock slots could not be rebound; the helper was reset to 1x.",
            )
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

    def _installation_state(self):
        abi = self.driver.abi()
        if abi != self.ABI_VERSION:
            raise ProcessTimeWarpError(
                "time_warp_abi_mismatch", "host.timeWarp.error.abiMismatchVersion",
                arguments=(self.ABI_VERSION, abi),
                diagnostic=f"Time Warp helper ABI 不兼容（需要 {self.ABI_VERSION}，当前 {abi}）。",
            )
        state = self.driver.install_state(self.image_payload)
        if state == -4:
            raise self._install_error(state)
        if state == 2:
            raise self._install_error(-7)
        if state not in (0, 1):
            raise ProcessTimeWarpError(
                "restart_required", "host.timeWarp.error.installStateUnknown",
                diagnostic=f"Time Warp helper installation state is not usable ({state}).",
            )
        return state

    def _verify_speed(self, speed):
        actual = self.driver.get_speed()
        if not math.isfinite(actual) or abs(actual - speed) > 0.000001:
            raise ProcessTimeWarpError(
                "time_warp_verify_failed", "host.timeWarp.error.verifyFailed",
                arguments=(f"{speed:g}", f"{actual:g}"),
                diagnostic=f"Time Warp 设置校验失败（目标 {speed:g}，实际 {actual:g}）。",
            )
        return actual

    def _set_installed_speed(self, speed):
        code = self.driver.set_speed(speed)
        if code == -7:
            raise self._install_error(code)
        if code != 0:
            raise ProcessTimeWarpError(
                "time_warp_set_failed", "host.timeWarp.error.setFailed",
                arguments=(code,), diagnostic=f"Time Warp 设置失败（{code}）。",
            )
        return self._verify_speed(speed)

    def set_speed(self, value):
        speed = self._validate_speed(value)
        self._check_alive()
        with self.driver.session():
            if not self.driver.helper_present():
                self.driver.load_helper(self.helper_path)
            if self._installation_state() == 0:
                code = self.driver.install(self.image_payload, speed)
                if code != 0:
                    raise self._install_error(code)
                if self.driver.hook_mask() == 0:
                    raise ProcessTimeWarpError(
                        "time_warp_unsupported",
                        "host.timeWarp.error.noClockBindings",
                        diagnostic="目标镜像没有可用的 Time Warp 时钟绑定。",
                    )
                return self._verify_speed(speed)
            return self._set_installed_speed(speed)

    def current_speed(self):
        if not self.driver.is_alive() or not self.driver.helper_present():
            return 1.0
        with self.driver.session():
            return self.driver.get_speed() if self._installation_state() == 1 else 1.0

    def reset(self):
        if not self.driver.is_alive():
            return 1.0
        if not self.driver.helper_present():
            return 1.0
        with self.driver.session():
            if self._installation_state() == 0:
                return 1.0
            return self._set_installed_speed(1.0)
