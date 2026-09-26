import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import diagnostics
from games.hades2.config import GAME_SPEC


STALE_STATE = {
    "connected": True,
    "pid": 7331,
    "status": "ready",
    "scene": "run",
    "runtimeDiagnostics": {"revision": 49, "heroObjectId": 123},
    "runCount": 7,
    "featureSupport": {"godMode": True},
    "statSupport": {"health": True},
}


class FakeTransport:
    def alive(self):
        return True


class FakeAdapter:
    module_protocol_version = 5
    transport = FakeTransport()

    def __init__(self, refresh_result=None, refresh_error=None):
        self.state = dict(STALE_STATE)
        self.refresh_result = refresh_result
        self.refresh_error = refresh_error
        self.calls = []

    def observe_runtime(self):
        self.calls.append("observe_runtime")
        if self.refresh_error is not None:
            raise self.refresh_error
        return self.refresh_result

    def list_profiles(self):
        return []


def build(adapter, identity):
    with tempfile.TemporaryDirectory(prefix="mgt-diagnostics-live-status-") as directory:
        root = Path(directory)
        game = root / "Hades II.app"
        saves = root / "Saves"
        game.mkdir()
        saves.mkdir()
        completed = SimpleNamespace(returncode=1, stdout="", stderr="not available")
        with (
            patch.object(diagnostics.preparation, "GAME", game),
            patch.object(diagnostics.preparation, "SAVES", saves),
            patch.object(diagnostics.preparation, "compatibility", return_value=identity),
            patch.object(diagnostics.localization, "official_display_names", return_value={"WeaponUpgrade": "测试"}),
            patch.object(diagnostics.subprocess, "run", return_value=completed),
        ):
            return diagnostics.build_diagnostics(adapter)


def test_failed_live_refresh_does_not_report_stale_runtime_state_as_ok():
    adapter = FakeAdapter(refresh_error=RuntimeError("status refresh failed"))
    result = build(adapter, {
        "version": "143476",
        "steam_build": "25481925",
        "compatible": True,
        "warnings": [],
    })

    checks = {item["name"]: item for item in result["checks"]}
    assert checks["运行时状态刷新"]["ok"] is False
    assert "status refresh failed" in checks["运行时状态刷新"]["detail"]
    for name in (
        GAME_SPEC.display_name + " 进程",
        "Lua 连接",
        "Lua runtime revision",
        "当前场景",
        "Hero ObjectId",
        "Run Count",
    ):
        assert checks[name]["ok"] is False, name
    assert result["state"] == {}
    assert adapter.calls == ["observe_runtime"]


def test_incompatible_game_identity_fails_check_and_reports_warnings():
    fresh_state = {"connected": False, "pid": None, "status": "not_running"}
    adapter = FakeAdapter(refresh_result=fresh_state)
    warning = "未经验证的游戏版本：version=199999, build=99999999。"
    result = build(adapter, {
        "version": "199999",
        "steam_build": "99999999",
        "compatible": False,
        "warnings": [warning],
    })

    checks = {item["name"]: item for item in result["checks"]}
    identity_check = checks["游戏版本 / Build"]
    assert identity_check["ok"] is False
    assert warning in identity_check["detail"]
    assert result["state"] == fresh_state
    assert result["passed"] < result["total"]


if __name__ == "__main__":
    test_failed_live_refresh_does_not_report_stale_runtime_state_as_ok()
    test_incompatible_game_identity_fails_check_and_reports_warnings()
    print("diagnostics_live_status_ok")
