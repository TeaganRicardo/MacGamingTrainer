"""Actual container controls through the temporary production Save backend."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only container Save frontend test")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
from games.hades2.save_document import Hades2SaveDocument


def state(path):
    return Hades2SaveDocument.load(path).lua_state["GameState"]["AdvancedFixture"]


with tempfile.TemporaryDirectory(prefix="mgt-container-save-journey-") as temporary:
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
                  ROOT / "tests/fixtures/swift/SaveContainerPlayerJourney.swift", generated])
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise SystemExit("swiftc required")
    binary = base / "advanced-save-journey"
    subprocess.run([swiftc, "-parse-as-library", *map(str, sources), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home),
               PYTHONPATH=str(ROOT / "Backend"), MGT_SAVE_JOURNEY_FIXTURE=str(base), MGT_SAVE_CONTAINER_FIXTURE="1")
    result = subprocess.run([str(binary), sys.executable, str(ROOT / "tests/fixtures/hades2/save_editor_player_journey.py")],
                            cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        print((base / "commands.jsonl").read_text())
        raise SystemExit(result.returncode)
    assert (base / "saves/Profile1.sav").read_bytes() == (base / "source-original.sav").read_bytes()
    installed = Hades2SaveDocument.load(base / "saves/Profile2.sav")
    assert installed.header.timestamp == 18446744073709551614
    assert installed.header.completed_runs == 4294967295
    assert installed.lua_values[1] == -5.25
    assert installed.lua_values[2]["Child"] == "container table"
    assert installed.lua_values[3] == -float("inf")
    assert installed.lua_state["NewRoot"] == "created"
    assert installed.lua_values[4][float("inf")]["Nested"] == "infinite edited"
    assert installed.lua_values[4]["UniqueSibling"] == "sibling edited"
    requests = [json.loads(line) for line in (base / "commands.jsonl").read_text().splitlines()]
    assert any(request["command"] == "save_editor_query" and request["params"].get("path") == [{"saveContainer": "header"}] for request in requests)
    assert any(request["command"] == "save_editor_query" and request["params"].get("path") == [{"saveContainer": "payload"}] for request in requests)
    assert sum(request["command"] == "save_editor_apply" for request in requests) == 1
    assert all(request["command"] == "hello" or request["command"].startswith("save_editor_") for request in requests)
    print(result.stdout.strip())
    print("container_save_native_bytes_and_reopen_ok")
