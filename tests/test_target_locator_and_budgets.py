"""Verify Core locate_target, bounded_run, Hades II Steam library discovery/caching, and Hades I timeouts."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapterContext
from core.module_manifest import GameModuleManifest
from core.target_probe import (
    AmbiguousTargetError,
    BoundedCommandTimeoutError,
    LocatedTarget,
    bounded_run,
    locate_target,
)
from games.hades.adapter import HadesAdapter
from games.hades.preferences import HadesPreferenceStore
from games.hades2 import diagnostics, error_presentation, localization, preparation, save_investigation
from games.hades2.adapter import Hades2Adapter
from games.hades2.config import SUPPORTED_BUILD, resolve_game_install
from games.hades.recovery import process_identity

HADES2_MANIFEST = GameModuleManifest.load(ROOT / "Backend/games/hades2/module.json")
HADES_MANIFEST = GameModuleManifest.load(ROOT / "Backend/games/hades/module.json")


def _write_hades2_install(
    steamapps: Path,
    *,
    install_dir: str = "Hades II",
    bundle_version: str = SUPPORTED_BUILD["bundleVersion"],
    steam_build: str = SUPPORTED_BUILD["steamBuildID"],
    locale_name: str = "WeaponUpgrade",
    locale_zh: str = "外置赐福",
) -> tuple[Path, Path, Path]:
    app = steamapps / "common" / install_dir / "Hades II.app"
    exe = app / "Contents/MacOS/Hades II"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"hades2-binary")
    (app / "Contents/Info.plist").write_text(
        "<plist version='1.0'><dict>"
        "<key>CFBundleIdentifier</key><string>com.supergiantgames.macos.hades2</string>"
        f"<key>CFBundleVersion</key><string>{bundle_version}</string>"
        "<key>CFBundleExecutable</key><string>Hades II</string>"
        "</dict></plist>",
        encoding="utf-8",
    )
    text_dir = app / "Contents/Resources/Content/Game/Text/zh-CN"
    text_dir.mkdir(parents=True)
    (text_dir / "TestText.zh-CN.sjson").write_text(
        f'{{ Id = "{locale_name}" DisplayName = "{locale_zh}" }}\n',
        encoding="utf-8",
    )
    scripts_dir = app / "Contents/Resources/Content/Scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "StoryResetData.lua").write_text("-- external library script\n", encoding="utf-8")

    manifest = steamapps / "appmanifest_1145350.acf"
    manifest.write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"1145350"\n\t"installdir"\t\t"{install_dir}"\n\t"buildid"\t\t"{steam_build}"\n}}\n',
        encoding="utf-8",
    )
    return app, exe, manifest


# 1. bounded_run enforces positive budget and maps TimeoutExpired to BoundedCommandTimeoutError.
for bad_budget in (0, -1, False, True, float("nan"), float("inf"), float("-inf")):
    try:
        bounded_run([sys.executable, "-c", "pass"], bad_budget)
    except ValueError:
        pass
    else:
        raise AssertionError(f"bounded_run accepted invalid budget {bad_budget!r}")

try:
    bounded_run([sys.executable, "-c", "import time; time.sleep(10)"], 0.05)
except BoundedCommandTimeoutError as error:
    assert error.budget == 0.05 and "超时" in str(error)
else:
    raise AssertionError("bounded_run allowed child to exceed budget")


# 2. locate_target follows Host identity rules (bundle ID or executable suffix) + proc_pidpath.
with tempfile.TemporaryDirectory(prefix="mgt-wp33-locate-") as tmp:
    root = Path(tmp)
    good_bundle = root / "External/Hades II.app"
    good_exe = good_bundle / "Contents/MacOS/Hades II"
    good_exe.parent.mkdir(parents=True)
    good_exe.write_bytes(b"real")
    (good_bundle / "Contents/Info.plist").write_text(
        "<plist><dict>"
        "<key>CFBundleIdentifier</key><string>com.supergiantgames.macos.hades2</string>"
        "<key>CFBundleExecutable</key><string>Hades II</string>"
        "</dict></plist>",
        encoding="utf-8",
    )
    bad_bundle = root / "Imposter/Hades II.app"
    bad_exe = bad_bundle / "Contents/MacOS/Hades II"
    bad_exe.parent.mkdir(parents=True)
    bad_exe.write_bytes(b"imposter")
    (bad_bundle / "Contents/Info.plist").write_text(
        "<plist><dict><key>CFBundleIdentifier</key><string>com.example.imposter</string></dict></plist>",
        encoding="utf-8",
    )
    bare_exe = root / "Bare/Hades II"
    bare_exe.parent.mkdir(parents=True)
    bare_exe.write_bytes(b"bare")

    probes = {
        101: str(bare_exe),
        102: str(bad_exe),
        103: str(good_exe),
    }
    ps_table = "101 Hades II\n102 Hades II\n103 Hades II\n"
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=ps_table, stderr=""),
    ):
        found = locate_target(HADES2_MANIFEST, executable_probe=probes.get)
    assert found == LocatedTarget(103, good_exe.resolve(), good_bundle.resolve()), found
    pid, exe_path, bundle_path = found
    assert (pid, exe_path, bundle_path) == (103, good_exe.resolve(), good_bundle.resolve())

    # Truncated MAXCOMLEN command names in `ps` still match when proc_pidpath verifies full suffix.
    long_manifest = SimpleNamespace(
        process_name="VeryLongGameBinaryName",
        bundle_identifier="",
        executable_path_suffix="VeryLong/VeryLongGameBinaryName",
    )
    long_exe = root / "Library/VeryLong/VeryLongGameBinaryName"
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="201 VeryLongGameBin\n", stderr=""),
    ):
        long_found = locate_target(long_manifest, executable_probe=lambda pid: str(long_exe) if pid == 201 else None)
    assert long_found == LocatedTarget(201, long_exe.resolve(), None), long_found

    # Imposter CFBundleIdentifier must be rejected even when both bundle_identifier and executable_path_suffix are declared.
    both_manifest = SimpleNamespace(
        process_name="Hades II",
        bundle_identifier="com.supergiantgames.macos.hades2",
        executable_path_suffix="Imposter/Hades II.app/Contents/MacOS/Hades II",
    )
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="102 Hades II\n", stderr=""),
    ):
        imposter_match = locate_target(both_manifest, executable_probe=lambda pid: str(bad_exe) if pid == 102 else None)
    assert imposter_match is None, f"imposter bundle bypassed bundle_identifier check: {imposter_match}"

    # Malformed Info.plist XML or invalid plist types never crash locate_target.
    malformed_bundle = root / "Malformed/Hades II.app"
    malformed_exe = malformed_bundle / "Contents/MacOS/Hades II"
    malformed_exe.parent.mkdir(parents=True)
    malformed_exe.write_bytes(b"malformed")
    (malformed_bundle / "Contents/Info.plist").write_text("<plist><dict>", encoding="utf-8")
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="105 Hades II\n", stderr=""),
    ):
        assert locate_target(HADES2_MANIFEST, executable_probe=lambda _pid: str(malformed_exe)) is None
    (malformed_bundle / "Contents/Info.plist").write_text(
        "<plist><dict><key>CFBundleIdentifier</key><date>bad</date></dict></plist>",
        encoding="utf-8",
    )
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="105 Hades II\n", stderr=""),
    ):
        assert locate_target(HADES2_MANIFEST, executable_probe=lambda _pid: str(malformed_exe)) is None

    # Ambiguous matches fail closed.
    with patch(
        "core.target_probe.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="103 Hades II\n104 Hades II\n", stderr=""),
    ):
        try:
            locate_target(HADES2_MANIFEST, executable_probe=lambda _pid: str(good_exe))
        except AmbiguousTargetError:
            pass
        else:
            raise AssertionError("multiple identical matches did not raise AmbiguousTargetError")


# 3. Hades II resolves non-default Steam libraries from libraryfolders.vdf and caches per (path, mtime).
with tempfile.TemporaryDirectory(prefix="mgt-wp33-steam-") as tmp:
    base = Path(tmp)
    home = base / "home"
    default_steamapps = home / "Library/Application Support/Steam/steamapps"
    default_steamapps.mkdir(parents=True)
    external_root = base / "Volumes/ExternalSSD/SteamLibrary"
    ext_app, ext_exe, ext_manifest = _write_hades2_install(
        external_root / "steamapps",
        install_dir="Hades II Custom",
    )
    (default_steamapps / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n'
        '{\n'
        f'\t"0"\t{{ "path" "{default_steamapps.parent}" "apps" {{ "228980" "1" }} }}\n'
        f'\t"1"\t{{ "path" "{external_root}" "apps" {{ "1145350" "1" }} }}\n'
        '}\n',
        encoding="utf-8",
    )
    run_app, _run_exe, _run_manifest = _write_hades2_install(
        base / "RunningLib/steamapps",
        install_dir="Hades II Running",
        bundle_version="999999",
        steam_build="88888888",
        locale_zh="运行中目录赐福",
    )

    uuid_calls = []

    def fake_uuid(exe):
        uuid_calls.append(Path(exe))
        return SUPPORTED_BUILD["uuid"]

    localization.invalidate_display_names()
    preparation.invalidate_compatibility_cache()
    with patch.dict(os.environ, {"HOME": str(home)}), patch.object(
        preparation, "_uuid", side_effect=fake_uuid
    ), patch("games.hades2.preparation.locate_target", return_value=None), patch(
        "games.hades2.adapter.locate_target", return_value=None
    ):
        assert not (default_steamapps / "common/Hades II/Hades II.app").exists()

        # Non-default Steam library resolves compatibility, localization, investigation, diagnostics, and adapter.
        compat_first = preparation.compatibility()
        assert compat_first["compatible"] is True
        assert Path(compat_first["game"]).resolve() == ext_app.resolve()
        assert len(uuid_calls) == 1

        # Second call hits cache without spawning dwarfdump, and returns a defensive copy.
        compat_first["warnings"].append("mutated-by-caller")
        compat_second = preparation.compatibility()
        assert compat_second["warnings"] == []
        assert len(uuid_calls) == 1

        # Bumping mtime invalidates compatibility cache cleanly.
        stat = ext_exe.stat()
        os.utime(ext_exe, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
        preparation.compatibility()
        assert len(uuid_calls) == 2

        # strict=True raises even on cached incompatible build.
        (ext_manifest).write_text('"AppState" { "installdir" "Hades II Custom" "buildid" "111" }\n', encoding="utf-8")
        stat_acf = ext_manifest.stat()
        os.utime(ext_manifest, ns=(stat_acf.st_atime_ns, stat_acf.st_mtime_ns + 10_000_000))
        bad_compat = preparation.compatibility(strict=False)
        assert bad_compat["compatible"] is False and len(uuid_calls) == 3
        try:
            preparation.compatibility(strict=True)
        except RuntimeError:
            assert len(uuid_calls) == 3
        else:
            raise AssertionError("cached incompatible result did not raise under strict=True")

        names = localization.official_display_names({"WeaponUpgrade"}, "zh-CN")
        assert names == {"WeaponUpgrade": "外置赐福"}, names
        inv_scripts, _inv_text = save_investigation._original_roots(None)
        assert inv_scripts is not None and ext_app.resolve() in inv_scripts.resolve().parents

        class _Controller:
            pass

        class _Session:
            pid = None

            def alive(self):
                return False

            def invalidate_generation(self):
                pass

        context = GameAdapterContext.from_manifest(HADES2_MANIFEST, home=home)
        adapter = Hades2Adapter(context=context, resident_session=_Session(), time_warp_controller=_Controller())
        scan_state = adapter.scan()
        assert scan_state["status"] == "not_running"
        assert adapter.save_provider_context().game_path.resolve() == ext_app.resolve()
        diag = diagnostics.build_diagnostics(adapter)
        install_check = next(row for row in diag["checks"] if row["name"] == "Hades II 安装")
        assert install_check["ok"] is True and Path(install_check["detail"]).resolve() == ext_app.resolve()

    # Steam metadata strings in steamapps/libraryfolders.vdf do not short-circuit config/libraryfolders.vdf.
    meta_home = base / "meta_home"
    (meta_home / "Library/Application Support/Steam/steamapps").mkdir(parents=True)
    (meta_home / "Library/Application Support/Steam/config").mkdir(parents=True)
    meta_ext_lib = base / "ConfigLibrary"
    meta_ext_app, _, _ = _write_hades2_install(meta_ext_lib / "steamapps")
    (meta_home / "Library/Application Support/Steam/steamapps/libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"TimeNextStatsReport"\t\t"1700000000"\n\t"ContentStatsID"\t\t"-1"\n}\n',
        encoding="utf-8",
    )
    (meta_home / "Library/Application Support/Steam/config/libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{meta_ext_lib}"\n\t\t"apps"\n\t\t{{\n\t\t\t"1145350"\t\t"1"\n\t\t}}\n\t}}\n}}\n',
        encoding="utf-8",
    )
    resolved_meta_app, _, _ = resolve_game_install(home=meta_home)
    assert resolved_meta_app.resolve() == meta_ext_app.resolve(), resolved_meta_app

    # Running process overrides libraryfolders.vdf.
    localization.invalidate_display_names()
    preparation.invalidate_compatibility_cache()
    live_located = LocatedTarget(7777, run_app / "Contents/MacOS/Hades II", run_app)
    with patch.dict(os.environ, {"HOME": str(home)}), patch.object(
        preparation, "_uuid", side_effect=fake_uuid
    ), patch("games.hades2.preparation.locate_target", return_value=live_located), patch(
        "games.hades2.adapter.locate_target", return_value=live_located
    ):
        class _LiveSession:
            pid = None
            pending_resume_pid = None
            cleanup_pending = False

            def alive(self):
                return False

            def invalidate_generation(self):
                pass

        context = GameAdapterContext.from_manifest(HADES2_MANIFEST, home=home)
        adapter = Hades2Adapter(context=context, resident_session=_LiveSession(), time_warp_controller=_Controller())
        state = adapter.scan()
        assert state["pid"] == 7777 and state["version"] == "1.999999" and state["steamBuild"] == "88888888"
        assert adapter.install_path().resolve() == run_app.resolve()
        assert adapter.save_provider_context().game_path.resolve() == run_app.resolve()
        assert localization.official_display_names({"WeaponUpgrade"}, "zh-CN") == {"WeaponUpgrade": "运行中目录赐福"}
        assert preparation.official_display_names({"WeaponUpgrade"}, "zh-CN", ext_app) == {
            "WeaponUpgrade": "外置赐福"
        }

        # Scan timeout & empty-stderr process errors preserve structured presentation keys without Chinese leakage.
        with patch("games.hades2.adapter.locate_target", side_effect=BoundedCommandTimeoutError(["/bin/ps"], 2.0)):
            try:
                adapter.scan()
            except RuntimeError as error:
                pres = error_presentation.presentation_for(str(error))
                assert pres == ("hades2.error.timeout", ["/bin/ps", "2"]), pres
            else:
                raise AssertionError("Hades2Adapter.scan() did not raise on timeout")

        with patch(
            "games.hades2.adapter.locate_target",
            side_effect=subprocess.CalledProcessError(2, ["/bin/ps"], output=b"", stderr=b""),
        ):
            try:
                adapter.scan()
            except RuntimeError as error:
                pres = error_presentation.presentation_for(str(error))
                assert pres[0] == "hades2.error.processQueryFailed" and len(pres[1]) == 3 and pres[1][2] == "exit 2", pres
            else:
                raise AssertionError("Hades2Adapter.scan() did not raise on CalledProcessError")

        empty_fail = subprocess.CalledProcessError(2, ["/bin/ps"], output=b"", stderr=b"")
        with patch("games.hades2.preparation.bounded_run", side_effect=empty_fail):
            try:
                preparation._command("/bin/ps")
            except RuntimeError as error:
                pres = error_presentation.presentation_for(str(error))
                assert pres == ("hades2.error.commandFailed", ["/bin/ps", "2", "exit 2"]), pres
            else:
                raise AssertionError("preparation._command did not raise on CalledProcessError")


# 4. Hades I subprocess calls carry finite timeouts and surface timeouts cleanly.
with tempfile.TemporaryDirectory(prefix="mgt-wp33-hades1-") as tmp:
    base = Path(tmp)
    context = GameAdapterContext.from_manifest(HADES_MANIFEST, home=base)
    adapter = HadesAdapter(context, preferences=HadesPreferenceStore(base / "prefs.json"))

    with patch("core.target_probe.subprocess.run", side_effect=subprocess.TimeoutExpired(["/bin/ps"], 2)):
        try:
            adapter.dispatch("connect", {}, "connect-timeout")
        except BoundedCommandTimeoutError as error:
            assert error.budget > 0
        else:
            raise AssertionError("Hades I process probe timeout was swallowed")

    with patch("core.target_probe.subprocess.run", side_effect=subprocess.TimeoutExpired(["/usr/bin/open"], 10)):
        try:
            adapter.dispatch("launch", {}, "launch-timeout")
        except BoundedCommandTimeoutError as error:
            assert error.budget == 10.0
        else:
            raise AssertionError("Hades I launch timeout was swallowed")

    with patch("core.target_probe.subprocess.run", side_effect=subprocess.TimeoutExpired(["/bin/ps"], 2)):
        try:
            process_identity(42)
        except BoundedCommandTimeoutError:
            pass
        else:
            raise AssertionError("Hades I recovery process_identity timeout was swallowed")

print("target_locator_and_budgets_ok")
