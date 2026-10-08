import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable
from games.hades2.save_provider import Hades2SaveProvider
from games.hades2.save_workspace import Hades2SaveWorkspace


def _table(values):
    return LuaTable(0, len(values), list(values.items()))


def _save_bytes(timestamp, resources=None, extra=None):
    game_state = {
        "Resources": _table(resources or {"MetaCurrency": 123.0}),
        "UnknownFutureField": _table(extra or {"KeepMe": "yes"}),
    }
    root = _table({"GameState": _table(game_state), "CurrentRun": _table({})})
    header = Hades2SaveHeader(
        game_version=0x12,
        save_flags=0,
        timestamp=timestamp,
        location="Crossroads",
        completed_runs=12,
        accumulated_meta_points=34,
        active_shrine_points=5,
        meta_upgrade_level=20,
        cosmetics_points=7,
        easy_mode=0,
        hard_mode=0,
        notable_lua_data=("GameState", "CurrentRun"),
        map_name="Hub_Main",
        next_map_name="F_Opening01",
    )
    return Hades2SaveDocument(header, [root]).to_bytes()


def _active_profile(name="Profile1"):
    raw = name.encode("utf-8")
    return b"SGB1" + struct.pack("<I", len(raw)) + raw


def _environment(name, *, include_temp=False, running=False):
    base = Path(tempfile.mkdtemp(prefix="mgt-save-workspace-")) / name
    saves = base / "saves"
    saves.mkdir(parents=True)
    (saves / "activeProfile").write_bytes(_active_profile())
    (saves / "Profile1.sav").write_bytes(_save_bytes(100))
    if include_temp:
        (saves / "Profile1_Temp.sav").write_bytes(_save_bytes(200))
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "activeProfile", "saveinfo")),),
        provider="games.hades2.save_provider:Hades2SaveProvider",
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    service = CoreSaveService(
        "hades2",
        spec,
        base / "data",
        lambda: running,
        provider_loader=lambda _target: Hades2SaveProvider(),
    )
    return base, saves, service


_base, _saves, service = _environment("hub")
hub = Hades2SaveWorkspace.open(service)
assert hub.profile == "Profile1"
assert hub.relative_path == "Profile1.sav"

_base, _saves, service = _environment("run", include_temp=True)
run = Hades2SaveWorkspace.open(service)
assert run.profile == "Profile1"
assert run.relative_path == "Profile1_Temp.sav"

print("hades2_save_workspace_ok")
