from pathlib import Path
import os
import sys
import tempfile
import zipfile

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
    scoped_log.write_text("SCOPED LOG\n", encoding="utf-8")
    (legacy_data / "trainer.log").write_text("LEGACY LOG MUST NOT EXPORT\n", encoding="utf-8")

    result = diagnostics.export_diagnostics(FakeAdapter())
    archive_path = Path(result["diagnosticBundle"])
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "trainer.log.tail" in names
        tail = archive.read("trainer.log.tail").decode("utf-8")
        assert "SCOPED LOG" in tail
        assert "LEGACY LOG MUST NOT EXPORT" not in tail

if original_home is None:
    os.environ.pop("HOME", None)
else:
    os.environ["HOME"] = original_home

print("hades2_diagnostics_log_scope_ok")
