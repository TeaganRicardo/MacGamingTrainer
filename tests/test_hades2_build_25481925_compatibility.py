import json
import plistlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import preparation


EXPECTED_VERSION = "143476"
EXPECTED_DISPLAY_VERSION = "1.143476"
EXPECTED_STEAM_BUILD = "25481925"
EXPECTED_UUID = "35CD2E50-2D78-3A63-835B-3EB1224C6D65"
EXPECTED_ORIGINAL_SHA256 = "933a2db2251a3fddd70900016f323338690235c7b3aae63edd4a78ca18c3bfe3"
EXPECTED_WORLD_UPDATE_RVA = 2463044
EXPECTED_WORLD_UPDATE_PREFIX = "ff0307d1ef3b126ded33136deb2b146d"


def test_verified_build_identity_is_accepted_without_warning():
    with tempfile.TemporaryDirectory(prefix="mgt-hades2-build-25481925-") as directory:
        root = Path(directory)
        game = root / "Hades II.app"
        executable = game / "Contents/MacOS/Hades II"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"verified build placeholder")
        (game / "Contents/Info.plist").write_bytes(
            plistlib.dumps({"CFBundleVersion": EXPECTED_VERSION})
        )
        manifest = root / "appmanifest_1145350.acf"
        manifest.write_text(f'"buildid" "{EXPECTED_STEAM_BUILD}"', encoding="utf-8")

        old_values = (
            preparation.GAME,
            preparation.GAME_SPEC,
            preparation.STEAM_SPEC,
            preparation._uuid,
        )
        preparation.GAME = game
        preparation.GAME_SPEC = SimpleNamespace(executable_path=executable)
        preparation.STEAM_SPEC = SimpleNamespace(manifest_path=manifest)
        preparation._uuid = lambda _path: EXPECTED_UUID
        try:
            identity = preparation.compatibility()
        finally:
            (
                preparation.GAME,
                preparation.GAME_SPEC,
                preparation.STEAM_SPEC,
                preparation._uuid,
            ) = old_values

    assert identity["version"] == EXPECTED_VERSION
    assert identity["steam_build"] == EXPECTED_STEAM_BUILD
    assert identity["uuid"] == EXPECTED_UUID
    assert identity["compatible"] is True
    assert identity["warnings"] == []


def test_verified_build_constants_and_symbol_manifest_match_target_evidence():
    assert preparation.VERSION == EXPECTED_VERSION
    assert preparation.DISPLAY_VERSION == EXPECTED_DISPLAY_VERSION
    assert preparation.STEAM_BUILD == EXPECTED_STEAM_BUILD
    assert preparation.UUID == EXPECTED_UUID
    assert preparation.ORIGINAL_SHA256 == EXPECTED_ORIGINAL_SHA256

    manifest = json.loads(
        (ROOT / "Backend/games/hades2/symbols.json").read_text(encoding="utf-8")
    )
    assert manifest["uuid"] == EXPECTED_UUID
    world = manifest["symbols"]["_ZN3sgg5World6UpdateEf"]
    assert world["rva"] == EXPECTED_WORLD_UPDATE_RVA
    assert world["prefix"] == EXPECTED_WORLD_UPDATE_PREFIX

    # The build changed only the World::Update RVA among the verified transport
    # symbols. These unchanged RVAs are target-machine evidence, not generated
    # from the production manifest under test.
    assert manifest["symbols"]["lua_gettop"]["rva"] == 82504
    assert manifest["symbols"]["lua_settop"]["rva"] == 82532
    assert manifest["symbols"]["luaL_loadbufferx"]["rva"] == 181368
    assert manifest["symbols"]["lua_pcallk"]["rva"] == 87476
    assert manifest["symbols"]["lua_tolstring"]["rva"] == 84188
    assert manifest["symbols"]["_ZN3sgg13ScriptManager12LuaInterfaceE"]["rva"] == 100841032
    assert manifest["symbols"]["_ZN3sgg13ConfigOptions20RequireFocusToUpdateE"]["rva"] == 100793566


def test_adapter_initial_version_uses_the_verified_preparation_baseline():
    source = (ROOT / "Backend/games/hades2/adapter.py").read_text(encoding="utf-8")
    assert "'version':preparation.DISPLAY_VERSION" in source
    assert "'version':'1.139672'" not in source


for _test in (
    test_verified_build_identity_is_accepted_without_warning,
    test_verified_build_constants_and_symbol_manifest_match_target_evidence,
    test_adapter_initial_version_uses_the_verified_preparation_baseline,
):
    _test()

print("hades2_build_25481925_compatibility_ok")
