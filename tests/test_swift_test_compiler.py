"""Portable and macOS contract tests for tests/swift_test_compiler.py."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import swift_test_compiler as stc


def _make_toolchain(**overrides: str) -> dict[str, str]:
    base = {
        "swiftc": "/usr/bin/swiftc",
        "resolved_swiftc": "/Applications/Xcode.app/Contents/Developer/usr/bin/swiftc",
        "xcrun_swiftc": "/Applications/Xcode.app/Contents/Developer/usr/bin/swiftc",
        "swiftc_version": "Apple Swift version 6.3",
        "sdk_path": "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk",
        "sdk_version": "26.0",
        "developer_dir": "/Applications/Xcode.app/Contents/Developer",
        "arch": "arm64",
    }
    base.update(overrides)
    return base


def test_support_key_sensitivity_and_filepath_safety() -> None:
    """Keys cover toolchain, SDK, flags, file order, repo paths, and generated content."""
    with tempfile.TemporaryDirectory(prefix="mgt-stc-repo-") as fake_repo_tmp, tempfile.TemporaryDirectory(
        prefix="mgt-stc-gen-a-"
    ) as gen_dir_a, tempfile.TemporaryDirectory(prefix="mgt-stc-gen-b-") as gen_dir_b:
        repo_a = Path(fake_repo_tmp) / "checkout_a"
        repo_b = Path(fake_repo_tmp) / "checkout_b"
        repo_a.mkdir()
        repo_b.mkdir()

        # Keep fake repo paths outside tempfile roots? No: use ROOT files or mock _is_temp_path
        # when exercising non-temp repo semantics so the temp hierarchy guard stays exact.
        real_core = ROOT / "Sources/Core/Runtime/TrainerJSON.swift"
        real_defaults = ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"
        # A temporary checkout is correctly uncached in production. Model a
        # stable source checkout here so this key test is location-independent.
        def stable_repo_records(paths):
            original = stc._is_temp_path
            stable = {real_core.resolve(), real_defaults.resolve()}
            with mock.patch.object(
                stc, "_is_temp_path",
                side_effect=lambda p: False if Path(p).resolve() in stable else original(p),
            ):
                return stc._support_file_records(paths)

        gen_a = Path(gen_dir_a) / "GameBinding.generated.swift"
        gen_b = Path(gen_dir_b) / "GameBinding.generated.swift"
        gen_a.write_text("// generated\nlet activeGameID = \"hades2\"\n", encoding="utf-8")
        gen_b.write_text("// generated\nlet activeGameID = \"hades2\"\n", encoding="utf-8")

        records_a, cacheable_a = stable_repo_records([real_core, real_defaults, gen_a])
        records_b, cacheable_b = stable_repo_records([real_core, real_defaults, gen_b])
        assert cacheable_a and cacheable_b, (cacheable_a, cacheable_b)
        assert records_a == records_b, "identical generated binding bytes must share cache across temp dirs"

        tc = _make_toolchain()
        flags = stc.normalize_support_flags(["-parse-as-library"])
        k_base = stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=records_a)
        k_same = stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=records_b)
        assert k_base == k_same

        # Generated content change invalidates key.
        gen_b.write_text("// generated\nlet activeGameID = \"hades\"\n", encoding="utf-8")
        records_b2, _ = stable_repo_records([real_core, real_defaults, gen_b])
        k_gen_changed = stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=records_b2)
        assert k_gen_changed != k_base

        # File order change invalidates key.
        records_reordered, _ = stable_repo_records([real_defaults, real_core, gen_a])
        assert (
            stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=records_reordered)
            != k_base
        )

        # Toolchain / SDK / arch / flag sensitivity.
        assert (
            stc.compute_support_key(
                toolchain=_make_toolchain(swiftc_version="Apple Swift version 6.4"),
                support_flags=flags,
                file_records=records_a,
            )
            != k_base
        )
        assert (
            stc.compute_support_key(
                toolchain=_make_toolchain(sdk_version="26.1"),
                support_flags=flags,
                file_records=records_a,
            )
            != k_base
        )
        assert (
            stc.compute_support_key(
                toolchain=_make_toolchain(arch="x86_64"),
                support_flags=flags,
                file_records=records_a,
            )
            != k_base
        )
        assert (
            stc.compute_support_key(
                toolchain=tc,
                support_flags=stc.normalize_support_flags(["-parse-as-library", "-DTRACE"]),
                file_records=records_a,
            )
            != k_base
        )

        # Module identity and the keys of imported modules are part of the key,
        # so a game rebuilds whenever the TrainerCore it imports changes.
        assert stc.compute_support_key(
            toolchain=tc, support_flags=flags, file_records=records_a, module_name="Hades2",
        ) != k_base
        with_core = stc.compute_support_key(
            toolchain=tc, support_flags=flags, file_records=records_a, module_name="Hades2",
            dependencies={"TrainerCore": "a" * 64},
        )
        assert with_core != stc.compute_support_key(
            toolchain=tc, support_flags=flags, file_records=records_a, module_name="Hades2",
            dependencies={"TrainerCore": "b" * 64},
        )

        # A caller's module name never leaks into library module flags.
        assert "-module-name" not in stc.normalize_support_flags(["-module-name", "TrainerCore"])

        # Non-generated temp files disable cacheability so patched trees never collide.
        ephemeral = Path(gen_dir_a) / "PatchedSource.swift"
        ephemeral.write_text("let patched = true\n", encoding="utf-8")
        _, cacheable_ephemeral = stable_repo_records([real_core, ephemeral, gen_a])
        assert not cacheable_ephemeral

        # Non-temp repo paths with identical bytes in different checkouts produce
        # different keys so embedded #filePath strings cannot bleed across checkouts.
        file_a = repo_a / "Presentation.swift"
        file_b = repo_b / "Presentation.swift"
        file_a.write_text("let path = #filePath\n", encoding="utf-8")
        file_b.write_text("let path = #filePath\n", encoding="utf-8")
        with mock.patch.object(stc, "_is_temp_path", return_value=False):
            rec_repo_a, c_a = stc._support_file_records([file_a])
            rec_repo_b, c_b = stc._support_file_records([file_b])
        assert c_a and c_b
        assert rec_repo_a != rec_repo_b
        assert (
            stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=rec_repo_a)
            != stc.compute_support_key(toolchain=tc, support_flags=flags, file_records=rec_repo_b)
        )


def _fake_swiftc(commands: list[list[str]], on_link=None, linked_sources=None):
    """Record swiftc invocations and write placeholder outputs."""
    def fake_run(cmd: list[str], **kwargs):
        commands.append(list(cmd))
        if linked_sources is not None and "-emit-module-path" not in cmd:
            linked_sources[:] = [Path(arg).read_text(encoding="utf-8") for arg in cmd if arg.endswith(".swift")]
        if "-emit-module-path" in cmd:
            Path(cmd[cmd.index("-emit-module-path") + 1]).write_bytes(b"swiftmodule-v1")
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"staticlib-v1")
        else:
            if on_link is not None:
                on_link()
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"binary-v1")
        return subprocess.CompletedProcess(cmd, 0)
    return fake_run


def _built_modules(commands: list[list[str]]) -> list[str]:
    return [cmd[cmd.index("-module-name") + 1] for cmd in commands if "-emit-module-path" in cmd]


def _mocked_toolchain():
    return (
        mock.patch.object(stc, "resolve_swiftc", return_value="/usr/bin/swiftc"),
        mock.patch.object(stc, "probe_toolchain", return_value=_make_toolchain()),
    )


def test_cache_hit_miss_corruption_recovery_and_opt_out() -> None:
    """Each library module caches separately; a game builds against its cached TrainerCore."""
    with tempfile.TemporaryDirectory(prefix="mgt-stc-cache-") as tmp:
        root = Path(tmp)
        generated = root / "core" / "GameBinding.generated.swift"
        generated.parent.mkdir()
        generated.write_text("package let greeting = \"ok\"\n", encoding="utf-8")
        game_generated = root / "game" / "GameBinding.generated.swift"
        game_generated.parent.mkdir()
        game_generated.write_text("import TrainerCore\nlet reply = greeting\n", encoding="utf-8")
        harness = root / "Harness.swift"
        harness.write_text("@main struct Main { static func main() { print(reply) } }\n", encoding="utf-8")
        core = stc.SwiftModule(stc.SWIFT_CORE_MODULE, [generated])
        game = stc.SwiftModule("Game", [game_generated], [stc.SWIFT_CORE_MODULE])
        cache_dir = root / "cache"
        out_bin = root / "bin"
        commands: list[list[str]] = []
        linked: list[str] = []

        def compile_harness(modules=(core, game), environ=None, **kwargs):
            commands.clear()
            stc.compile_swift_test(
                modules=list(modules), harness_sources=[harness], output=out_bin,
                cache_dir=cache_dir, environ={} if environ is None else environ, **kwargs,
            )

        resolve, probe = _mocked_toolchain()
        with resolve, probe, mock.patch.object(
            stc.subprocess, "run", side_effect=_fake_swiftc(commands, linked_sources=linked)
        ):
            # 1. Cold: TrainerCore, then the game against it, then the harness.
            compile_harness()
            assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE, "Game"], commands
            core_build, game_build, link = commands
            assert "-I" not in core_build, "TrainerCore must not see any other module"
            core_entry = Path(game_build[game_build.index("-I") + 1])
            assert (core_entry / f"{stc.SWIFT_CORE_MODULE}.swiftmodule").is_file()
            assert link[link.index("-module-name") + 1] == stc.HARNESS_MODULE_NAME
            assert sum(1 for arg in link if arg == "-I") == 2
            assert any(arg.endswith(f"lib{stc.SWIFT_CORE_MODULE}.a") for arg in link)
            assert any(arg.endswith("libGame.a") for arg in link)
            assert linked == [
                f"@testable import {stc.SWIFT_CORE_MODULE}\n@testable import Game\n" + harness.read_text(encoding="utf-8")
            ], linked
            entries = {p.name for p in cache_dir.iterdir() if p.is_dir() and not p.name.startswith(".")}
            assert len(entries) == 2, entries

            # 2. Warm: only the harness compiles.
            compile_harness()
            assert _built_modules(commands) == [] and len(commands) == 1, commands

            # 3. A Core-only harness reuses the same cached TrainerCore.
            compile_harness(modules=(core,))
            assert _built_modules(commands) == [], commands

            # 4. A corrupt cached library rebuilds only that module.
            (core_entry / f"lib{stc.SWIFT_CORE_MODULE}.a").write_bytes(b"corrupted!")
            compile_harness()
            assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE], commands
            assert (core_entry / f"lib{stc.SWIFT_CORE_MODULE}.a").read_bytes() == b"staticlib-v1"

            # 5. A corrupt manifest rebuilds as well.
            (core_entry / "manifest.json").write_text("{bad json", encoding="utf-8")
            compile_harness()
            assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE], commands

            # 6. Changing TrainerCore changes the game's key: both rebuild.
            generated.write_text("package let greeting = \"changed\"\n", encoding="utf-8")
            compile_harness()
            assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE, "Game"], commands
            generated.write_text("package let greeting = \"ok\"\n", encoding="utf-8")

            # 7. MGT_SWIFT_TEST_CACHE=0 builds every module privately and never
            # touches the shared cache.
            before = sorted(p.name for p in cache_dir.iterdir())
            compile_harness(environ={stc.CACHE_ENV_VAR: "0"})
            assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE, "Game"], commands
            assert all(not arg.startswith(str(cache_dir)) for cmd in commands for arg in cmd)
            assert sorted(p.name for p in cache_dir.iterdir()) == before

            # 8. A patched temporary source builds its module, and every module
            # importing it, privately; cached TrainerCore is still reused.
            patched = root / "game" / "Patched.swift"
            patched.write_text("import TrainerCore\nlet reply = 1\n", encoding="utf-8")
            compile_harness(modules=(core, stc.SwiftModule("Game", [patched], [stc.SWIFT_CORE_MODULE])))
            assert _built_modules(commands) == ["Game"], commands
            assert not commands[0][commands[0].index("-emit-module-path") + 1].startswith(str(cache_dir))
            assert sorted(p.name for p in cache_dir.iterdir()) == before

            # 9. Explicit modules replace the layout; naming games too is an error.
            try:
                compile_harness(games=("hades2",))
            except ValueError:
                pass
            else:
                raise AssertionError("explicit modules plus games must be rejected")
            # A module importing one that is not built before it is rejected.
            try:
                compile_harness(modules=(game,))
            except stc.SwiftCompilerError:
                pass
            else:
                raise AssertionError("an unbuilt dependency must be rejected")

        # 10. LRU pruning bounds directory count at MAX_CACHE_ENTRIES.
        prune_dir = root / "prune"
        prune_dir.mkdir()
        for idx in range(stc.MAX_CACHE_ENTRIES + 4):
            d = prune_dir / f"entry-{idx:02d}"
            d.mkdir()
            m = d / "manifest.json"
            m.write_text(json.dumps({"idx": idx}), encoding="utf-8")
            os.utime(m, (1000 + idx, 1000 + idx))
        stc._prune_cache(prune_dir, keep_name="entry-00")
        remaining = {p.name for p in prune_dir.iterdir() if p.is_dir() and not p.name.startswith(".")}
        assert "entry-00" in remaining
        assert len(remaining) <= stc.MAX_CACHE_ENTRIES, (len(remaining), remaining)

        # 11. Shims add only missing imports and disambiguate duplicate names.
        h1_dir = root / "d1"
        h2_dir = root / "d2"
        shim_dir = root / "shims"
        h1_dir.mkdir()
        h2_dir.mkdir()
        f1 = h1_dir / "Same.swift"
        f2 = h2_dir / "Same.swift"
        f3 = h2_dir / "Partial.swift"
        f1.write_text("let a = 1\n", encoding="utf-8")
        f2.write_text("import SwiftUI\nimport TrainerCore\n@testable import Game\nlet b = 2\n", encoding="utf-8")
        f3.write_text("@preconcurrency import TrainerCore\nlet c = 3\n", encoding="utf-8")
        shimmed = stc._write_harness_shims([f1, f2, f1, f3], shim_dir, [stc.SWIFT_CORE_MODULE, "Game"])
        assert shimmed[0] != shimmed[2], "duplicate basenames should get unique shim paths"
        assert shimmed[1] == f2, "a file importing every module keeps its original path"
        assert shimmed[0].read_text(encoding="utf-8").startswith(
            f"@testable import {stc.SWIFT_CORE_MODULE}\n@testable import Game\nlet a"
        )
        assert shimmed[3].read_text(encoding="utf-8").startswith("@testable import Game\n@preconcurrency")


def test_pruning_honors_active_lease_and_recovers_eviction() -> None:
    """Pruning cannot unlink a module that a later build step or the linker still reads."""
    with tempfile.TemporaryDirectory(prefix="mgt-stc-lease-") as tmp:
        root = Path(tmp)
        generated = root / "GameBinding.generated.swift"
        generated.write_text("package let answer = 42\n", encoding="utf-8")
        harness = root / "Harness.swift"
        harness.write_text("@main struct Main { static func main() { print(answer) } }\n", encoding="utf-8")
        core = stc.SwiftModule(stc.SWIFT_CORE_MODULE, [generated])
        cache = root / "cache"
        output = root / "binary"
        commands: list[list[str]] = []
        entry_dir: list[Path] = []

        def prune_during_link():
            # The leased entry is the oldest candidate. Only its lease
            # should prevent pruning its directory.
            for index in range(stc.MAX_CACHE_ENTRIES + 3):
                extra = cache / f"extra-{index:02d}"
                extra.mkdir(exist_ok=True)
                (extra / "manifest.json").write_text("{}", encoding="utf-8")
            os.utime(entry_dir[0] / "manifest.json", (1, 1))
            stc._prune_cache(cache, keep_name="another-key")
            assert entry_dir[0].exists(), "pruner evicted an in-use Swift module"

        resolve, probe = _mocked_toolchain()
        with resolve, probe, mock.patch.object(stc.subprocess, "run", side_effect=_fake_swiftc(commands)):
            stc.compile_swift_test(modules=[core], harness_sources=[harness], output=output,
                                   cache_dir=cache, environ={})
        entry_dir.extend(p for p in cache.iterdir() if p.is_dir() and not p.name.startswith("."))
        assert len(entry_dir) == 1

        commands.clear()
        resolve, probe = _mocked_toolchain()
        with resolve, probe, mock.patch.object(
            stc.subprocess, "run", side_effect=_fake_swiftc(commands, on_link=prune_during_link)
        ):
            stc.compile_swift_test(modules=[core], harness_sources=[harness], output=output,
                                   cache_dir=cache, environ={})
        assert _built_modules(commands) == [], commands
        assert output.read_bytes() == b"binary-v1"

        # With no live lease, the previously old entry can be evicted.
        stc._prune_cache(cache, keep_name="another-key")
        assert not entry_dir[0].exists()

        # An eviction between a build and its lease is detected and rebuilt,
        # never handed to a later step.
        eviction_cache = root / "eviction"
        commands.clear()
        original_ensure = stc._ensure_module
        first = [True]

        def evict_once(**kwargs):
            result = original_ensure(**kwargs)
            if first[0]:
                first[0] = False
                shutil.rmtree(result)
            return result

        resolve, probe = _mocked_toolchain()
        with resolve, probe, mock.patch.object(
            stc.subprocess, "run", side_effect=_fake_swiftc(commands)
        ), mock.patch.object(stc, "_ensure_module", side_effect=evict_once):
            stc.compile_swift_test(modules=[core], harness_sources=[harness], output=output,
                                   cache_dir=eviction_cache, environ={})
        assert _built_modules(commands) == [stc.SWIFT_CORE_MODULE, stc.SWIFT_CORE_MODULE], commands
        assert output.read_bytes() == b"binary-v1"


def test_harness_layout_is_the_product_layout() -> None:
    """A harness compiles exactly the files the product compiles into each library module."""
    sys.path.insert(0, str(ROOT / "Tools"))
    from product_support import swift_layout, swift_module_sources
    from module_support import load_manifest

    with tempfile.TemporaryDirectory(prefix="mgt-stc-layout-") as tmp:
        generated = Path(tmp) / "harness"
        layout = stc.harness_layout(["hades", "hades2"], generated)
        product = swift_module_sources(
            swift_layout([load_manifest("hades"), load_manifest("hades2")])["modules"], ROOT, generated
        )
        expected = [(module["name"], tuple(sources), tuple(module["dependencies"]))
                    for module, sources in product if module["role"] != "app"]
        assert len(expected) == len(product) - 1, "the harness takes the App module's place"
        assert [(m.name, m.sources, m.dependencies) for m in layout] == expected
        assert [m.name for m in layout] == [stc.SWIFT_CORE_MODULE, "Hades", "Hades2"]
        assert all(path.is_relative_to(ROOT / "Sources/Core") for path in layout[0].sources)
        assert [path.name for path in layout[1].sources if not path.is_relative_to(ROOT)] == [
            "GameBinding.generated.swift"
        ]
        core_only = stc.harness_layout([], Path(tmp) / "core")
        assert [m.name for m in core_only] == [stc.SWIFT_CORE_MODULE]


def test_clt_sdk_shim_ignored_for_xcode_discovery() -> None:
    """CommandLineTools SDKROOT injected by /usr/bin/python3 must not shadow Xcode SDK."""
    clt_sdk = f"{stc._CLT_SDK_PREFIX}SDKs/MacOSX.sdk"
    xcode_sdk = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX27.2.sdk"
    seen_envs: list[tuple[list[str], dict[str, str]]] = []

    def fake_check_output(cmd: list[str], **kwargs):
        seen_envs.append((list(cmd), dict(kwargs.get("env") or {})))
        if cmd[:2] == ["/usr/bin/swiftc", "--version"]:
            return "Apple Swift version 6.3\n"
        if cmd[:2] == ["xcrun", "--find"]:
            return "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc\n"
        if cmd[:3] == ["xcrun", "--sdk", "macosx"] and "--show-sdk-path" in cmd:
            return xcode_sdk + "\n"
        if "--show-sdk-version" in cmd:
            return "27.2\n"
        raise AssertionError(f"unexpected check_output: {cmd}")

    stc.probe_toolchain.cache_clear()
    try:
        fake_uname = os.uname_result(("Darwin", "host", "26.0.0", "Darwin", "arm64"))
        with mock.patch.dict(os.environ, {"SDKROOT": clt_sdk}, clear=False), mock.patch.object(
            stc.os, "uname", return_value=fake_uname
        ), mock.patch.object(stc.subprocess, "check_output", side_effect=fake_check_output):
            tc = stc.probe_toolchain("/usr/bin/swiftc", sdk_root=clt_sdk)
    finally:
        stc.probe_toolchain.cache_clear()

    assert tc["sdk_path"] == xcode_sdk, tc
    assert tc["sdk_version"] == "27.2", tc
    for cmd, passed_env in seen_envs:
        assert "SDKROOT" not in passed_env, (cmd, passed_env.get("SDKROOT"))
    assert stc._subprocess_env({"SDKROOT": clt_sdk}, tc)["SDKROOT"] == xcode_sdk
    assert "SDKROOT" not in stc._subprocess_env({"SDKROOT": clt_sdk}, {"sdk_path": ""})

    # Custom environ must not leak os.environ DEVELOPER_DIR/SDKROOT, and changing
    # os.environ DEVELOPER_DIR must miss the cached probe instead of reusing stale values.
    stc.probe_toolchain.cache_clear()
    try:
        seen_envs.clear()
        with mock.patch.dict(
            os.environ,
            {"DEVELOPER_DIR": "/Applications/Xcode_Old.app/Contents/Developer", "SDKROOT": "/Old.sdk"},
            clear=False,
        ), mock.patch.object(stc.os, "uname", return_value=fake_uname), mock.patch.object(
            stc.subprocess, "check_output", side_effect=fake_check_output
        ):
            isolated = stc.probe_toolchain("/usr/bin/swiftc", environ={})
            assert isolated["developer_dir"] == "", isolated
            for _, passed_env in seen_envs:
                assert "DEVELOPER_DIR" not in passed_env, passed_env
                assert "SDKROOT" not in passed_env, passed_env

            tc_old = stc.probe_toolchain("/usr/bin/swiftc")
            assert tc_old["developer_dir"] == "/Applications/Xcode_Old.app/Contents/Developer"

        with mock.patch.dict(
            os.environ,
            {"DEVELOPER_DIR": "/Applications/Xcode_New.app/Contents/Developer", "SDKROOT": "/New.sdk"},
            clear=False,
        ), mock.patch.object(stc.os, "uname", return_value=fake_uname), mock.patch.object(
            stc.subprocess, "check_output", side_effect=fake_check_output
        ):
            tc_new = stc.probe_toolchain("/usr/bin/swiftc")
            assert tc_new["developer_dir"] == "/Applications/Xcode_New.app/Contents/Developer"
            assert tc_new["sdk_path"] == "/New.sdk"
    finally:
        stc.probe_toolchain.cache_clear()


def test_real_darwin_equivalence_and_cache_hit() -> None:
    """When run on macOS with swiftc, cached cold/warm builds match direct MGT_SWIFT_TEST_CACHE=0."""
    swiftc = shutil.which("swiftc")
    if sys.platform != "darwin" or not swiftc:
        return

    with tempfile.TemporaryDirectory(prefix="mgt-stc-darwin-") as tmp:
        work = Path(tmp)
        cache_dir = work / "cache"
        harness = work / "EquivalenceHarness.swift"
        harness.write_text(
            """
import Foundation

@main
struct EquivalenceHarness {
    static func main() {
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        localization.language = .en
        let enTitle = localization.string("hades2.chaosGate.title")
        let patch = Hades2StatePatch(["chaosGateProbability": 25.5])
        print("eq_ok|\\(Hades2GameModule.presentation.headerTitle)|\\(enTitle)|\\(patch.chaosGateProbability.value ?? -1)|\\(Hades2GameModuleBinding.descriptor.id)")
    }
}
""",
            encoding="utf-8",
        )
        direct_bin = work / "direct"
        cold_bin = work / "cold"
        warm_bin = work / "warm"

        # Keep this equivalence check valid if the repository itself was
        # checked out below /tmp; only the generated bindings are temporary.
        def compile_from_checkout(**kwargs):
            original = stc._is_temp_path
            with mock.patch.object(
                stc, "_is_temp_path",
                side_effect=lambda p: False if Path(p).resolve().is_relative_to(ROOT.resolve()) else original(p),
            ):
                return stc.compile_swift_test(**kwargs)

        compile_from_checkout(
            games=("hades2",),
            harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", harness],
            output=direct_bin,
            swiftc=swiftc,
            cwd=ROOT,
            cache_dir=cache_dir,
            environ={stc.CACHE_ENV_VAR: "0"},
        )
        assert not cache_dir.exists()

        compile_from_checkout(
            games=("hades2",),
            harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", harness],
            output=cold_bin,
            swiftc=swiftc,
            cwd=ROOT,
            cache_dir=cache_dir,
            environ={},
        )
        entries = [p for p in cache_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
        assert len(entries) == 2, "TrainerCore and Hades2 cache separately"

        compile_from_checkout(
            games=("hades2",),
            harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", harness],
            output=warm_bin,
            swiftc=swiftc,
            cwd=ROOT,
            cache_dir=cache_dir,
            environ={},
        )

        # Ensure cache hit also survives #filePath presentation lookups & runtime behavior identically.
        home = work / "home"
        home.mkdir()
        run_env = {**os.environ, "HOME": str(home), "CFFIXED_USER_HOME": str(home)}
        outputs = [
            subprocess.run([str(binary)], cwd=ROOT, env=run_env, check=True, text=True, capture_output=True).stdout
            for binary in (direct_bin, cold_bin, warm_bin)
        ]
        assert outputs[0] == outputs[1] == outputs[2], outputs
        assert outputs[0].startswith("eq_ok|HADES II|Chaos Gate|25.5|hades2"), outputs[0]


if __name__ == "__main__":
    test_support_key_sensitivity_and_filepath_safety()
    test_cache_hit_miss_corruption_recovery_and_opt_out()
    test_pruning_honors_active_lease_and_recovers_eviction()
    test_harness_layout_is_the_product_layout()
    test_clt_sdk_shim_ignored_for_xcode_discovery()
    test_real_darwin_equivalence_and_cache_hit()
    print("swift_test_compiler_ok")
