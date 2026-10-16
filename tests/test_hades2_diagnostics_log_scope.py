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

    log_directory = (
        home
        / "Library/Application Support/MacGamingTrainer"
        / "hades2"
    )
    sessions = log_directory / "sessions"
    session_id = "session-1"
    session_directory = sessions / session_id
    session_directory.mkdir(parents=True)

    # The legacy flat path must not become the selected session source once a
    # Session Bundle is active.
    (log_directory / "trainer.log").write_text(
        "STALE LEGACY PATH MUST NOT EXPORT\n",
        encoding="utf-8",
    )
    (log_directory / "trainer-host.log").write_text(
        "HOST CONTEXT MUST NOT REPLACE SESSION\n",
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": 1,
        "id": session_id,
        "startedAt": "2026-10-16T00:00:00Z",
        "endedAt": None,
        "targetProcessName": "Hades II",
        "targetBundleIdentifier": "com.supergiantgames.hades2",
        "targetPID": 1234,
        "appVersion": "0.3.0",
        "appBuild": "6",
        "gameVersion": "1.143476",
        "runtimeRevision": 112,
        "state": "active",
        "endReason": None,
        "streams": {
            "HOST": "host.log",
            "BACKEND": "backend.log",
            "RUNTIME": "runtime.log",
        },
        "legacy": False,
    }
    (session_directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (session_directory / "host.log").write_text(
        "HOST SESSION HOST STREAM\n",
        encoding="utf-8",
    )
    (session_directory / "backend.log").write_text(
        "BACKEND SESSION BACKEND STREAM\n",
        encoding="utf-8",
    )
    (session_directory / "runtime.log").write_text(
        "RUNTIME SESSION RUNTIME STREAM\n",
        encoding="utf-8",
    )
    (log_directory / "current-session.json").write_text(
        json.dumps({"id": session_id}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    old_session = sessions / "old-session"
    old_session.mkdir(parents=True)
    (old_session / "manifest.json").write_text(
        json.dumps({
            **manifest,
            "id": "old-session",
            "state": "completed",
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (old_session / "host.log").write_text(
        "OLD SESSION MUST NOT EXPORT\n",
        encoding="utf-8",
    )

    (legacy_data / "trainer.log").write_text(
        "LEGACY LOG MUST NOT EXPORT\n",
        encoding="utf-8",
    )

    result = diagnostics.export_diagnostics(FakeAdapter())
    archive_path = Path(result["diagnosticBundle"])
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "trainer-session/manifest.json" in names
        assert "trainer-session/host.log" in names
        assert "trainer-session/backend.log" in names
        assert "trainer-session/runtime.log" in names
        assert "trainer-session.log" not in names
        assert "trainer-session.json" not in names
        assert "trainer-host.log.tail" not in names
        assert "trainer-session/legacy.log" not in names

        assert "STALE LEGACY PATH" not in archive.read(
            "trainer-session/host.log"
        ).decode("utf-8")
        assert "HOST SESSION HOST STREAM" in archive.read(
            "trainer-session/host.log"
        ).decode("utf-8")
        assert "BACKEND SESSION BACKEND STREAM" in archive.read(
            "trainer-session/backend.log"
        ).decode("utf-8")
        assert "RUNTIME SESSION RUNTIME STREAM" in archive.read(
            "trainer-session/runtime.log"
        ).decode("utf-8")
        assert "OLD SESSION" not in "\n".join(names)
        assert "LEGACY LOG" not in "\n".join(
            archive.read(name).decode("utf-8")
            for name in names
            if name.endswith(".log")
        )

        report = json.loads(archive.read("report.json"))
        assert report["protocolVersion"] == 6
        assert report["trainerLogScope"] == "current_target_session"
        assert report["trainerSession"]["id"] == session_id
        assert report["trainerSession"]["streams"] == manifest["streams"]
        assert report["trainerLogStreams"] == ["BACKEND", "HOST", "RUNTIME"]

        exported_manifest = json.loads(
            archive.read("trainer-session/manifest.json")
        )
        assert exported_manifest == manifest

    # With no target session pointer, export the Host context explicitly rather
    # than selecting completed history or the legacy trainer.log path.
    (log_directory / "current-session.json").unlink()
    host_result = diagnostics.export_diagnostics(FakeAdapter())
    host_archive_path = Path(host_result["diagnosticBundle"])
    with zipfile.ZipFile(host_archive_path) as archive:
        names = set(archive.namelist())
        assert "trainer-host.log.tail" in names
        assert "trainer-session/manifest.json" not in names
        assert "trainer-session/host.log" not in names
        host_tail = archive.read("trainer-host.log.tail").decode("utf-8")
        assert "HOST CONTEXT MUST NOT REPLACE SESSION" in host_tail
        host_report = json.loads(archive.read("report.json"))
        assert host_report["trainerLogScope"] == "host_context"
        assert host_report["trainerSession"] is None
        assert host_report["trainerLogStreams"] == []

if original_home is None:
    os.environ.pop("HOME", None)
else:
    os.environ["HOME"] = original_home

print("hades2_diagnostics_log_scope_ok")
