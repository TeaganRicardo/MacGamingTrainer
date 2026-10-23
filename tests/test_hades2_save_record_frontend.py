"""Ordinary stored-record controls through the real temporary Save transaction."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Save record frontend test")
ROOT = Path(__file__).resolve().parents[1]
# A fixed archived backend can be used while UI and backend owners develop in
# parallel. The combined final-head gate uses its own repository by default.
BACKEND_ROOT = Path(os.environ.get("MGT_SAVE_JOURNEY_BACKEND_ROOT", ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "Backend"))
from games.hades2.save_document import Hades2SaveDocument


with tempfile.TemporaryDirectory(prefix="mgt-record-save-journey-") as temporary:
    base = Path(temporary)
    (base / ".fixture-owned").touch()
    home = base / "home"
    home.mkdir()
    generated = base / "ActiveGame.generated.swift"
    subprocess.run([sys.executable, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)], check=True, cwd=ROOT)
    sources = (sorted((ROOT / "Sources/Core").rglob("*.swift"))
               + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
               + [ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
                  ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
                  ROOT / "tests/fixtures/swift/SaveRecordPlayerJourney.swift", generated])
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise SystemExit("swiftc required")
    binary = base / "record-save-journey"
    subprocess.run([swiftc, "-parse-as-library", *map(str, sources), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home),
               PYTHONPATH=str(BACKEND_ROOT / "Backend"), MGT_SAVE_JOURNEY_RECORDS="1",
               MGT_SAVE_JOURNEY_FIXTURE=str(base))
    result = subprocess.run([str(binary), sys.executable, str(ROOT / "tests/fixtures/hades2/save_editor_player_journey.py")],
                            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    installed = Hades2SaveDocument.load(base / "saves/Profile2.sav").lua_state
    state = installed["GameState"]
    run = state["RunHistory"][1]
    assert run["RunResult"] == 3 and type(run["RunResult"]) in (int, float)
    assert run["EndingRoomName"] == "" and run["ActiveBounty"] == "  revised  "
    assert state["FishingFails"] == 7 and state["FishingSuccesses"] == 9
    assert state["QuestStatus"]["QuestHelpDora"] == "Complete"
    assert state["QuestsCompleted"]["QuestHelpDora"] is True
    assert state["QuestsViewed"]["QuestHelpDora"] is True
    assert state["TextLinesRecord"]["UnverifiedScene"] is True
    assert state["TextLinesChoiceRecord"]["UnverifiedScene"] == " Choice B "
    assert state["SpeechRecord"]["/VO/Unknown_0001"] == 12
    assert state["SpeechRecord"]["/VO/Legacy_0001"] is False
    assert state["Resources"]["GiftPoints"] == 5
    assert state["LifetimeResourcesGained"]["GiftPoints"] == 103
    assert installed["CurrentRun"]["ResourcesGained"]["GiftPoints"] == 7
    assert state["UnviewedLastResourceGained"] == "GiftPoints"
    assert state["QuestStatus"]["QuestUnlockMoros"] == "CashedOut"
    assert state["QuestsCompleted"]["QuestUnlockMoros"] is True
    assert state["GiftRecord"]["Hecate"]["GiftPoints"] == 10
    assert state["GiftResourceRecord"]["GiftPoints"] == 14
    assert state["GiftRecord"]["Hecate"][1] == "GiftPoints"
    assert state["GiftTextLinesOrderRecord"]["Hecate"][1] == "OriginalGiftLine"
    assert installed["CurrentRun"]["GiftRecord"]["Hecate"]["GiftPoints"] == 1
    assert installed["CurrentRun"]["GiftResourceRecord"]["GiftPoints"] == 1
    assert installed["CurrentRun"]["RunResult"] == 2 and installed["CurrentRun"]["GameplayTime"] == 999
    assert (base / "saves/Profile1.sav").read_bytes() == (base / "source-original.sav").read_bytes()
    requests = [json.loads(line) for line in (base / "commands.jsonl").read_text().splitlines()]
    commands = [request["command"] for request in requests]
    assert commands.count("save_editor_apply") == 2 and commands.count("save_editor_close") == 3
    assert any(request["command"] == "save_editor_stage" and request["params"].get("value") == "" for request in requests)
    assert any(request["command"] == "save_editor_stage" and request["params"].get("entryId") == "history:run:1:RunResult"
               and request["params"].get("operation") == "setEnum" and request["params"].get("value") == "3" for request in requests)
    assert all(command == "hello" or command.startswith("save_editor_") for command in commands)
    print(result.stdout.strip())
    print("save_record_native_bytes_and_reopen_ok")
