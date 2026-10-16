import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))


class DeadTransport:
    def alive(self):
        return False


class FakeAdapter:
    game_id = "hades2"
    module_protocol_version = 5
    transport = DeadTransport()
    state = {}

    def list_profiles(self):
        return []


original_home = os.environ.get("HOME")
with tempfile.TemporaryDirectory(prefix="mgt-hades-diagnostics-log-") as td:
    root = Path(td)
    home = root / "home"
    home.mkdir()
    os.environ["HOME"] = str(home)

    from games.hades2 import diagnostics, preparation

    legacy_data = root / "legacy-hades-data"
    legacy_data.mkdir()
    preparation.DATA = legacy_data

    scoped_log = (
        home
        / "Library/Application Support/MacGamingTrainer"
        / "hades2"
        / "trainer.log"
    )
    scoped_log.parent.mkdir(parents=True)
    scoped_log.write_text("CURRENT SESSION LOG\n", encoding="utf-8")
    (scoped_log.parent / "trainer-host.log").write_text("HOST CONTEXT MUST NOT REPLACE SESSION\n", encoding="utf-8")
    (scoped_log.parent / "current-session.json").write_text(json.dumps({
        "id": "session-1",
        "startedAt": "2026-10-16T00:00:00Z",
        "endedAt": None,
        "targetProcessName": "Hades II",
        "targetBundleIdentifier": "com.supergiantgames.hades2",
        "targetPID": 1234,
        "appVersion": "0.3.0",
        "appBuild": "6",
        "legacy": False,
    }), encoding="utf-8")
    history = scoped_log.parent / "sessions"
    history.mkdir()
    (history / "old.log").write_text("OLD SESSION MUST NOT EXPORT\n", encoding="utf-8")
    (legacy_data / "trainer.log").write_text("LEGACY LOG MUST NOT EXPORT\n", encoding="utf-8")

    result = diagnostics.export_diagnostics(FakeAdapter())
    archive_path = Path(result["diagnosticBundle"])
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "trainer-session.log" in names
        assert "trainer-session.json" in names
        assert "trainer-host.log.tail" not in names
        tail = archive.read("trainer-session.log").decode("utf-8")
        assert "CURRENT SESSION LOG" in tail
        assert "HOST CONTEXT MUST NOT REPLACE SESSION" not in tail
        assert "OLD SESSION MUST NOT EXPORT" not in tail
        assert "LEGACY LOG MUST NOT EXPORT" not in tail
        report = json.loads(archive.read("report.json"))
        assert report["protocolVersion"] == 6
        assert report["trainerLogScope"] == "current_target_session"
        assert report["trainerSession"]["id"] == "session-1"

    # With no target session, export the Host context explicitly rather than
    # selecting completed history or inventing a game session.
    scoped_log.unlink()
    (scoped_log.parent / "current-session.json").unlink()
    host_result = diagnostics.export_diagnostics(FakeAdapter())
    host_archive_path = Path(host_result["diagnosticBundle"])
    with zipfile.ZipFile(host_archive_path) as archive:
        names = set(archive.namelist())
        assert "trainer-host.log.tail" in names
        assert "trainer-session.log" not in names
        assert "trainer-session.json" not in names
        host_tail = archive.read("trainer-host.log.tail").decode("utf-8")
        assert "HOST CONTEXT MUST NOT REPLACE SESSION" in host_tail
        assert "OLD SESSION MUST NOT EXPORT" not in host_tail
        host_report = json.loads(archive.read("report.json"))
        assert host_report["trainerLogScope"] == "host_context"
        assert host_report["trainerSession"] is None

if original_home is None:
    os.environ.pop("HOME", None)
else:
    os.environ["HOME"] = original_home

print("hades2_diagnostics_log_scope_ok")
