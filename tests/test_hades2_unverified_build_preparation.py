import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backend"))
from games.hades2 import preparation


with tempfile.TemporaryDirectory(prefix="mgt-verified-build-25481925-") as directory:
    root = Path(directory)
    game = root / "Hades II.app"
    executable = game / "Contents/MacOS/Hades II"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"verified target fixture")
    (game / "Contents/Info.plist").write_bytes(
        b"<?xml version='1.0'?><plist version='1.0'><dict>"
        b"<key>CFBundleVersion</key><string>143476</string>"
        b"</dict></plist>"
    )
    manifest = root / "appmanifest_1145350.acf"
    manifest.write_text('"buildid" "25481925"', encoding="utf-8")

    old_values = {
        "GAME": preparation.GAME,
        "GAME_SPEC": preparation.GAME_SPEC,
        "STEAM_SPEC": preparation.STEAM_SPEC,
        "_uuid": preparation._uuid,
    }
    preparation.GAME = game
    preparation.GAME_SPEC = SimpleNamespace(
        app_path=game,
        executable_path=executable,
        minimum_architecture="arm64",
    )
    preparation.STEAM_SPEC = SimpleNamespace(manifest_path=manifest)
    preparation._uuid = lambda _path: "35CD2E50-2D78-3A63-835B-3EB1224C6D65"
    try:
        identity = preparation.compatibility()
        assert identity["version"] == "143476"
        assert identity["steam_build"] == "25481925"
        assert identity["uuid"] == "35CD2E50-2D78-3A63-835B-3EB1224C6D65"
        assert identity["compatible"] is True
        assert identity["warnings"] == []
    finally:
        for name, value in old_values.items():
            setattr(preparation, name, value)

symbols = __import__("json").loads(
    (Path(__file__).resolve().parents[1] / "Backend/games/hades2/symbols.json").read_text()
)
assert symbols["uuid"] == "35CD2E50-2D78-3A63-835B-3EB1224C6D65"
assert symbols["symbols"]["_ZN3sgg5World6UpdateEf"]["rva"] == 2463044
assert symbols["symbols"]["_ZN3sgg5World6UpdateEf"]["prefix"] == "ff0307d1ef3b126ded33136deb2b146d"


with tempfile.TemporaryDirectory(prefix="mgt-unverified-build-") as directory:
    root = Path(directory)
    game = root / "Hades II.app"
    executable = game / "Contents/MacOS/Hades II"
    executable.parent.mkdir(parents=True)
    original_bytes = b"unverified but signed game executable"
    executable.write_bytes(original_bytes)
    (game / "Contents/Info.plist").write_bytes(
        b"<?xml version='1.0'?><plist version='1.0'><dict>"
        b"<key>CFBundleVersion</key><string>999999</string>"
        b"</dict></plist>"
    )
    manifest = root / "appmanifest_1145350.acf"
    manifest.write_text('"buildid" "99999999"', encoding="utf-8")

    old_values = {
        "GAME": preparation.GAME,
        "DATA": preparation.DATA,
        "GAME_SPEC": preparation.GAME_SPEC,
        "STEAM_SPEC": preparation.STEAM_SPEC,
        "_require_stopped": preparation._require_stopped,
        "_uuid": preparation._uuid,
        "_entitlements": preparation._entitlements,
        "_command": preparation._command,
    }
    unknown_uuid = "AAAAAAAA-BBBB-3CCC-8DDD-EEEEEEEEEEEE"
    prepared_entitlements = {
        "com.apple.security.get-task-allow": True,
        "com.apple.security.cs.disable-library-validation": True,
    }
    preparation.GAME = game
    preparation.DATA = root / "trainer-data"
    preparation.GAME_SPEC = SimpleNamespace(
        app_path=game,
        executable_path=executable,
        executable_name="Hades II",
        process_name="Hades2",
        display_name="Hades II",
        bundle_identifier="com.supergiantgames.hades2",
        minimum_architecture="arm64",
    )
    preparation.STEAM_SPEC = SimpleNamespace(manifest_path=manifest)
    preparation._require_stopped = lambda: None
    preparation._uuid = lambda _path: unknown_uuid

    def entitlements(path):
        prepared = str(path).endswith(".debug") or (
            Path(path) == executable and executable.read_bytes() != original_bytes
        )
        return prepared_entitlements if prepared else {}

    preparation._entitlements = entitlements
    commands = []

    def command(*args, allowed=(0,)):
        commands.append(args)
        if args[1] == "--force":
            staged = Path(args[-1])
            staged.write_bytes(staged.read_bytes() + b"\nadhoc debug signature")
        if args[1] == "--verify" and args[-1] == str(game):
            result = SimpleNamespace(
                returncode=1,
                stdout=b"",
                stderr=b"invalid Info.plist (plist or signature have been modified)",
            )
        else:
            result = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        if result.returncode not in allowed:
            raise RuntimeError(result.stderr.decode())
        return result

    preparation._command = command
    try:
        identity = preparation.compatibility()
        assert identity["compatible"] is False
        assert identity["warnings"]

        result = preparation.prepare()
        assert result["prepared"] is True
        assert result["manifest"]["compatible"] is False
        assert result["manifest"]["uuid"] == unknown_uuid
        assert result["manifest"]["original_signature_baseline"]["bundle_returncode"] == 1
        prepared_bytes = executable.read_bytes()
        assert prepared_bytes != original_bytes

        restored = preparation.restore()
        assert restored["restored"] is True
        assert executable.read_bytes() == original_bytes
        assert ("/usr/bin/codesign", "--verify", "--strict", str(game)) in commands
    finally:
        for name, value in old_values.items():
            setattr(preparation, name, value)

print("hades2_unverified_build_preparation_ok")
