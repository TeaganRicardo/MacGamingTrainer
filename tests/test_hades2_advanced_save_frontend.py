"""Actual Advanced controls through the temporary production Save backend."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Advanced Save frontend test")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.save_document import Hades2SaveDocument


def state(path):
    return Hades2SaveDocument.load(path).lua_state["GameState"]["AdvancedFixture"]


with tempfile.TemporaryDirectory(prefix="mgt-advanced-save-journey-") as temporary:
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
                  ROOT / "tests/fixtures/swift/SaveAdvancedPlayerJourney.swift", generated])
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise SystemExit("swiftc required")
    binary = base / "advanced-save-journey"
    subprocess.run([swiftc, "-parse-as-library", *map(str, sources), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home),
               PYTHONPATH=str(ROOT / "Backend"), MGT_SAVE_JOURNEY_FIXTURE=str(base))
    result = subprocess.run([str(binary), sys.executable, str(ROOT / "tests/fixtures/hades2/save_editor_player_journey.py")],
                            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert (base / "saves/Profile1.sav").read_bytes() == (base / "source-original.sav").read_bytes()
    first = state(base / "after-advanced-first.sav")
    assert first["Number"] == 8.25 and first["Boolean"] is False
    assert first["Text"] == "  exact  " and first["Empty"] == ""
    assert first["Binary"].encode("utf-8", errors="surrogateescape") == b"\x00\xfe"
    assert first["Nil"] == 3 and "Removed" not in first
    assert first["Members"][True] == "boolean changed"
    assert first["Members"][1] == "number changed"
    assert first["Members"]["1"] == "string changed"
    assert first["Members"]["\udcff"] == "binary changed"
    installed = state(base / "saves/Profile2.sav")
    assert "Nil" in installed and installed["Nil"] is None
    assert installed["Members"]["Added"] is False
    assert "1" not in installed["Members"]
    assert installed["Members"][True] == "boolean changed" and installed["Members"][1] == "number changed"
    assert installed["Members"]["\udcff"] == "binary changed"
    requests = [json.loads(line) for line in (base / "commands.jsonl").read_text().splitlines()]
    commands = [request["command"] for request in requests]
    assert commands.count("save_editor_apply") == 2
    assert any(request["command"] == "save_editor_stage" and request["params"].get("value") == "" for request in requests)
    assert any(request["command"] == "save_editor_stage" and request["params"].get("operation") == "addMembership" for request in requests)
    assert any(request["command"] == "save_editor_stage" and request["params"].get("operation") == "removeMembership" for request in requests)
    assert all(command == "hello" or command.startswith("save_editor_") for command in commands)
    print(result.stdout.strip())
    print("advanced_save_native_bytes_and_reopen_ok")
