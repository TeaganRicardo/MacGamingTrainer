import sys
import tempfile
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import diagnostics, schema
from games.hades2.config import GAME_SPEC
from games.hades2.adapter import Hades2Adapter
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


STALE_STATE = {
    "connected": True,
    "pid": 7331,
    "status": "ready",
    "scene": "run",
    "runtimeDiagnostics": {"revision": 49, "heroObjectId": 123},
    "runCount": 7,
    "featureSupport": {"invincibility": True},
    "statSupport": {"health": True},
}


def make_adapter(refresh_result=None, refresh_error=None):
    diagnostics.preparation.DATA = Path(tempfile.mkdtemp(prefix="mgt-diagnostic-adapter-"))
    session = FakeResidentSession(refresh_result, handler=lambda *args: refresh_error)
    adapter = Hades2Adapter(resident_session=session, time_warp_controller=FakeTimeWarpController())
    adapter.state.update(STALE_STATE)
    return adapter


def build(adapter, identity, command="diagnostics"):
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
            patch.object(diagnostics, "trainer_log_path", return_value=root / "trainer.log"),
        ):
            return adapter.dispatch(command, {}, "diagnostics-test")


def test_failed_live_refresh_does_not_report_stale_runtime_state_as_ok():
    adapter = make_adapter(refresh_error=RuntimeError("status refresh failed"))
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
    process_check = checks[GAME_SPEC.display_name + " 进程"]
    assert "未运行" not in process_check["detail"]
    assert str(STALE_STATE["pid"]) in process_check["detail"]
    assert result["state"] == {}
    assert [call['kind'] for call in adapter.runtime.calls] == ["observe"]


def test_feature_support_inventory_tracks_schema_without_a_mirror():
    synthetic = "syntheticDiagnosticToggle"
    assert synthetic not in schema.TOGGLES
    fresh_state = {
        "connected": True,
        "pid": 7331,
        "status": "ready",
        "scene": "run",
        "runtimeDiagnostics": {"revision": 51, "heroObjectId": 123},
        "runCount": 7,
        "featureSupport": {synthetic: True, "gameSpeed": True},
        "statSupport": {},
    }
    adapter = make_adapter(refresh_result=fresh_state)
    with patch.object(schema, "TOGGLES", schema.TOGGLES + (synthetic,)):
        result = build(adapter, {
            "version": "143476",
            "steam_build": "25481925",
            "compatible": True,
            "warnings": [],
        })

    feature_checks = [
        item for item in result["checks"]
        if item["name"].startswith("功能支持 · ")
    ]
    feature_ids = [item["name"].removeprefix("功能支持 · ") for item in feature_checks]
    assert feature_ids == [*schema.TOGGLES, synthetic, "gameSpeed"], feature_ids
    assert next(item for item in feature_checks if item["name"].endswith(synthetic))["ok"] is True


def test_incompatible_game_identity_fails_check_and_reports_warnings():
    fresh_state = {"connected": False, "pid": None, "status": "not_running"}
    adapter = make_adapter(refresh_result=fresh_state)
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
    assert result["state"]["status"] == fresh_state["status"]
    assert result["passed"] < result["total"]


def test_public_read_and_export_are_read_only_for_each_connection_outcome():
    identity = {"version": "143476", "steam_build": "25481925", "compatible": True}
    for mode in ("connected", "disconnected", "observation_failure", "alive_failure"):
        adapter = make_adapter(refresh_result=STALE_STATE)
        if mode == "disconnected": adapter.runtime.live = False
        if mode == "observation_failure":
            adapter.runtime.handler = lambda *args: RuntimeError("observation unavailable")
        if mode == "alive_failure":
            def failed_alive(): raise RuntimeError("liveness unavailable")
            adapter.runtime.alive = failed_alive
        adapter.preferences['invincibility'] = True
        before = json.dumps(adapter.preferences, sort_keys=True)
        for command in ("diagnostics", "export_diagnostics"):
            result = build(adapter, identity, command)
            refresh = next(row for row in result['checks'] if row['name'] == '运行时状态刷新')
            assert refresh['ok'] is (mode == 'connected'), mode
            if command == 'export_diagnostics':
                with zipfile.ZipFile(result['diagnosticBundle']) as archive:
                    report = json.loads(archive.read('report.json'))
                    assert report['checks'] == result['checks']
            assert json.dumps(adapter.preferences, sort_keys=True) == before
            assert not adapter.preference_store.path.exists()
        assert all(call['kind'] == 'observe' for call in adapter.runtime.calls)


if __name__ == "__main__":
    test_failed_live_refresh_does_not_report_stale_runtime_state_as_ok()
    test_feature_support_inventory_tracks_schema_without_a_mirror()
    test_incompatible_game_identity_fails_check_and_reports_warnings()
    test_public_read_and_export_are_read_only_for_each_connection_outcome()
    print("diagnostics_live_status_ok")
