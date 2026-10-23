"""Native Save workbench journeys against real temporary Save transactions."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 Save Editor player journey test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")
sys.path.insert(0, str(ROOT / "Backend"))
from core.save_snapshots import SaveSnapshotStore
from games.hades2.save_document import Hades2SaveDocument


def state(path):
    return Hades2SaveDocument.load(path).lua_state["GameState"]


with tempfile.TemporaryDirectory(prefix="mgt-save-player-journey-") as temporary:
    base = Path(temporary)
    (base / ".fixture-owned").touch()
    home = base / "home"
    home.mkdir()
    generated = base / "ActiveGame.generated.swift"
    subprocess.run(
        [sys.executable, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
        check=True, cwd=ROOT,
    )
    sources = (
        sorted((ROOT / "Sources/Core").rglob("*.swift"))
        + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
        + [ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
           ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
           ROOT / "tests/fixtures/swift/SaveEditorPlayerJourney.swift", generated]
    )
    binary = base / "save-player-journey"
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True, cwd=ROOT,
    )
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home),
               PYTHONPATH=str(ROOT / "Backend"), MGT_SAVE_JOURNEY_FIXTURE=str(base))
    result = subprocess.run(
        [str(binary), sys.executable, str(ROOT / "tests/fixtures/hades2/save_editor_player_journey.py")],
        check=False, cwd=ROOT, env=env, text=True, capture_output=True, timeout=60,
    )
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)

    # Independently decode the bytes installed by the production transaction,
    # and verify both recoverable pre-write snapshots through the Core store.
    source = base / "saves/Profile1.sav"
    assert source.read_bytes() == (base / "source-original.sav").read_bytes()
    assert state(base / "after-simple.sav")["Resources"]["MetaCurrency"] == 20
    installed = state(base / "saves/Profile2.sav")
    assert installed["Resources"]["MetaCurrency"] == 75
    assert installed["Resources"]["GiftPoints"] == 2
    assert installed["NPCInteractions"]["NPC_Hecate_01"] == 1
    assert installed["EquippedFamiliar"] == "HoundFamiliar"
    assert installed["UnknownFutureField"]["Marker"] == "fixed-source"
    card = installed["MetaUpgradeState"]["ChanneledCast"]
    assert card.get("Unlocked") is None and card.get("Equipped") is None and card["Level"] == 1
    report = json.loads((base / "journey.json").read_text())
    assert report["sourceSHA256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert report["source"] == "main/Profile1.sav" and report["target"] == "main/Profile2.sav"
    assert report["runtimeReloaded"] is False and report["swiftUIPopupSelectionTested"] is False
    assert report["firstSnapshot"] != report["lastSnapshot"]
    store = SaveSnapshotStore("hades2", base / "data")
    for key, amount, marker in (("firstSnapshot", 900, "initial-target"),
                                ("lastSnapshot", 999, "external-newer-target")):
        verified = store.load_verified_snapshot(report[key])
        previous = state(verified["root"] / "files/main/Profile2.sav")
        assert previous["Resources"]["MetaCurrency"] == amount
        assert previous["UnknownFutureField"]["Marker"] == marker
    requests = [json.loads(line) for line in (base / "commands.jsonl").read_text().splitlines()]
    commands = [request["command"] for request in requests]
    assert all(command == "hello" or command.startswith("save_editor_") for command in commands)
    assert commands.count("save_editor_apply") == 2
    assert commands.count("save_editor_open") == 2 and commands.count("save_editor_close") == 2
    print(result.stdout.strip())
    print("hades2_save_editor_player_journey_bytes_and_snapshots_ok")
