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

        gen_a = Path(gen_dir_a) / "ActiveGame.generated.swift"
        gen_b = Path(gen_dir_b) / "ActiveGame.generated.swift"
        gen_a.write_text("// generated\nlet activeGameID = \"hades2\"\n", encoding="utf-8")
        gen_b.write_text("// generated\nlet activeGameID = \"hades2\"\n", encoding="utf-8")

        records_a, cacheable_a = stable_repo_records([real_core, real_defaults, gen_a])
        records_b, cacheable_b = stable_repo_records([real_core, real_defaults, gen_b])
        assert cacheable_a and cacheable_b, (cacheable_a, cacheable_b)
        assert records_a == records_b, "identical ActiveGame.generated.swift bytes must share cache across temp dirs"

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


def test_cache_hit_miss_corruption_recovery_and_opt_out() -> None:
    """Mocked compiler verifies hit reuse, corrupt artifact rebuilds, LRU prune, and bypass."""
    with tempfile.TemporaryDirectory(prefix="mgt-stc-cache-") as tmp:
        root = Path(tmp)
        support_dir = root / "gen"
        support_dir.mkdir()
        generated = support_dir / "ActiveGame.generated.swift"
        generated.write_text("internal let greeting = \"ok\"\n", encoding="utf-8")
        harness = root / "Harness.swift"
        harness.write_text("@main struct Main { static func main() { print(greeting) } }\n", encoding="utf-8")
        cache_dir = root / "cache"
        out_bin = root / "bin"

        commands: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs):
            commands.append(list(cmd))
            if "-emit-module-path" in cmd:
                mod_path = Path(cmd[cmd.index("-emit-module-path") + 1])
                lib_path = Path(cmd[cmd.index("-o") + 1])
                mod_path.write_bytes(b"swiftmodule-v1")
                lib_path.write_bytes(b"staticlib-v1")
            else:
                out = Path(cmd[cmd.index("-o") + 1])
                out.write_bytes(b"binary-v1")
            return subprocess.CompletedProcess(cmd, 0)

        tc = _make_toolchain()
        with mock.patch.object(stc, "resolve_swiftc", return_value="/usr/bin/swiftc"), mock.patch.object(
            stc, "probe_toolchain", return_value=tc
        ), mock.patch.object(stc.subprocess, "run", side_effect=fake_run):
            # 1. Cold build: compiles support module + links harness (2 swiftc invocations).
            stc.compile_swift_test(
                support_sources=[generated],
                harness_sources=[harness],
                output=out_bin,
                cache_dir=cache_dir,
                environ={},
            )
            assert len(commands) == 2, commands
            assert "-emit-module" in commands[0]
            assert f"-l{stc.MODULE_NAME}" in commands[1]

            # Locate created cache entry.
            entries = [p for p in cache_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
            assert len(entries) == 1, entries
            entry = entries[0]

            # 2. Warm hit: only links harness (1 swiftc invocation).
            commands.clear()
            stc.compile_swift_test(
                support_sources=[generated],
                harness_sources=[harness],
                output=out_bin,
                cache_dir=cache_dir,
                environ={},
            )
            assert len(commands) == 1, commands
            assert "-emit-module" not in commands[0]

            # 3. Corrupt libMGTTestSupport.a -> automatic rebuild without failing or reusing corrupt bits.
            (entry / f"lib{stc.MODULE_NAME}.a").write_bytes(b"corrupted!")
            commands.clear()
            stc.compile_swift_test(
                support_sources=[generated],
                harness_sources=[harness],
                output=out_bin,
                cache_dir=cache_dir,
                environ={},
            )
            assert len(commands) == 2, ("corrupt lib should trigger rebuild", commands)
            assert (entry / f"lib{stc.MODULE_NAME}.a").read_bytes() == b"staticlib-v1"

            # 4. Corrupt manifest JSON -> automatic rebuild.
            (entry / "manifest.json").write_text("{bad json", encoding="utf-8")
            commands.clear()
            stc.compile_swift_test(
                support_sources=[generated],
                harness_sources=[harness],
                output=out_bin,
                cache_dir=cache_dir,
                environ={},
            )
            assert len(commands) == 2, ("corrupt manifest should trigger rebuild", commands)

            # 5. MGT_SWIFT_TEST_CACHE=0 -> direct single build bypassing cache.
            commands.clear()
            stc.compile_swift_test(
                support_sources=[generated],
                harness_sources=[harness],
                output=out_bin,
                cache_dir=cache_dir,
                environ={stc.CACHE_ENV_VAR: "0"},
            )
            assert len(commands) == 1, commands
            assert f"-l{stc.MODULE_NAME}" not in commands[0]

            # 6. Ephemeral non-generated support file -> direct WMO build honoring script flags.
            ephemeral = support_dir / "Patched.swift"
            ephemeral.write_text("let patched = 1\n", encoding="utf-8")
            commands.clear()
            stc.compile_swift_test(
                support_sources=[ephemeral],
                harness_sources=[harness],
                output=out_bin,
                flags=(),
                cache_dir=cache_dir,
                environ={},
            )
            assert len(commands) == 1, commands
            assert "-whole-module-optimization" in commands[0]
            assert "-parse-as-library" not in commands[0]
            assert "-enable-testing" not in commands[0]

        # 7. LRU pruning bounds directory count at MAX_CACHE_ENTRIES.
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

        # 8. Harness shimming does not duplicate imports and disambiguates duplicate names.
        h1_dir = root / "d1"
        h2_dir = root / "d2"
        shim_dir = root / "shims"
        h1_dir.mkdir()
        h2_dir.mkdir()
        f1 = h1_dir / "Same.swift"
        f2 = h2_dir / "Same.swift"
        f1.write_text("let a = 1\n", encoding="utf-8")
        f2.write_text(f"@testable import {stc.MODULE_NAME}\nlet b = 2\n", encoding="utf-8")
        shimmed = stc._write_harness_shims([f1, f2, f1], shim_dir)
        assert shimmed[0] != shimmed[2], "duplicate basenames should get unique shim paths"
        assert shimmed[1] == f2, "existing import should keep original path"
        assert shimmed[0].read_text(encoding="utf-8").startswith(f"@testable import {stc.MODULE_NAME}\n")


def test_pruning_honors_active_link_lease_and_recovers_eviction() -> None:
    """Parallel cache builds cannot unlink a module used by an active linker."""
    with tempfile.TemporaryDirectory(prefix="mgt-stc-lease-") as tmp:
        root = Path(tmp)
        generated = root / "ActiveGame.generated.swift"
        generated.write_text("internal let answer = 42\n", encoding="utf-8")
        harness = root / "Harness.swift"
        harness.write_text("@main struct Main { static func main() { print(answer) } }\n", encoding="utf-8")
        cache = root / "cache"
        output = root / "binary"
        builds = []
        trigger_prune = False
        entry_dir = None

        def fake_run(cmd: list[str], **kwargs):
            if "-emit-module-path" in cmd:
                builds.append("support")
                Path(cmd[cmd.index("-emit-module-path") + 1]).write_bytes(b"swiftmodule")
                Path(cmd[cmd.index("-o") + 1]).write_bytes(b"static library")
            else:
                if trigger_prune:
                    # The current manifest is the oldest candidate. Only a
                    # held link lease should prevent pruning its directory.
                    for index in range(stc.MAX_CACHE_ENTRIES + 3):
                        extra = cache / f"extra-{index:02d}"
                        extra.mkdir(exist_ok=True)
                        (extra / "manifest.json").write_text("{}", encoding="utf-8")
                    assert entry_dir is not None
                    os.utime(entry_dir / "manifest.json", (1, 1))
                    stc._prune_cache(cache, keep_name="another-key")
                    assert entry_dir.exists(), "pruner evicted an in-use Swift module"
                Path(cmd[cmd.index("-o") + 1]).write_bytes(b"linked binary")
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(stc, "resolve_swiftc", return_value="/usr/bin/swiftc"), mock.patch.object(
            stc, "probe_toolchain", return_value=_make_toolchain()
        ), mock.patch.object(stc.subprocess, "run", side_effect=fake_run):
            stc.compile_swift_test(
                support_sources=[generated], harness_sources=[harness],
                output=output, cache_dir=cache, environ={},
            )
            entries = [p for p in cache.iterdir() if p.is_dir() and not p.name.startswith(".")]
            assert len(entries) == 1
            entry_dir = entries[0]
            trigger_prune = True
            stc.compile_swift_test(
                support_sources=[generated], harness_sources=[harness],
                output=output, cache_dir=cache, environ={},
            )
            assert builds == ["support"], builds
            assert output.read_bytes() == b"linked binary"

        # With no live linker lease, the previously old entry can be evicted.
        stc._prune_cache(cache, keep_name="another-key")
        assert entry_dir is not None and not entry_dir.exists()

        # An eviction between build completion and acquiring a link lease is
        # detected and rebuilt, never passed through to the linker.
        eviction_cache = root / "eviction"
        builds.clear()
        original_ensure = stc._ensure_support_module
        first = [True]

        def evict_once(**kwargs):
            result = original_ensure(**kwargs)
            if first[0]:
                first[0] = False
                shutil.rmtree(result)
            return result

        with mock.patch.object(stc, "resolve_swiftc", return_value="/usr/bin/swiftc"), mock.patch.object(
            stc, "probe_toolchain", return_value=_make_toolchain()
        ), mock.patch.object(stc.subprocess, "run", side_effect=fake_run), mock.patch.object(
            stc, "_ensure_support_module", side_effect=evict_once
        ):
            trigger_prune = False
            stc.compile_swift_test(
                support_sources=[generated], harness_sources=[harness],
                output=output, cache_dir=eviction_cache, environ={},
            )
            assert builds == ["support", "support"], builds
            assert output.read_bytes() == b"linked binary"


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
        generated = work / "ActiveGame.generated.swift"
        subprocess.run(
            [sys.executable, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
            cwd=ROOT,
            check=True,
        )
        support = [
            *sorted((ROOT / "Sources/Core").rglob("*.swift")),
            *sorted((ROOT / "Sources/Hades2").rglob("*.swift")),
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            generated,
        ]
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
        print("eq_ok|\\(Hades2GameModule.presentation.headerTitle)|\\(enTitle)|\\(patch.chaosGateProbability.value ?? -1)")
    }
}
""",
            encoding="utf-8",
        )
        direct_bin = work / "direct"
        cold_bin = work / "cold"
        warm_bin = work / "warm"

        # Keep this equivalence check valid if the repository itself was
        # checked out below /tmp; only the generated binding is ephemeral.
        def compile_from_checkout(**kwargs):
            original = stc._is_temp_path
            with mock.patch.object(
                stc, "_is_temp_path",
                side_effect=lambda p: False if Path(p).resolve().is_relative_to(ROOT.resolve()) else original(p),
            ):
                return stc.compile_swift_test(**kwargs)

        compile_from_checkout(
            support_sources=support,
            harness_sources=[harness],
            output=direct_bin,
            swiftc=swiftc,
            cwd=ROOT,
            cache_dir=cache_dir,
            environ={stc.CACHE_ENV_VAR: "0"},
        )
        assert not cache_dir.exists()

        compile_from_checkout(
            support_sources=support,
            harness_sources=[harness],
            output=cold_bin,
            swiftc=swiftc,
            cwd=ROOT,
            cache_dir=cache_dir,
            environ={},
        )
        entries = [p for p in cache_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
        assert len(entries) == 1

        compile_from_checkout(
            support_sources=support,
            harness_sources=[harness],
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
        assert outputs[0].startswith("eq_ok|HADES II|Chaos Gate|"), outputs[0]


if __name__ == "__main__":
    test_support_key_sensitivity_and_filepath_safety()
    test_cache_hit_miss_corruption_recovery_and_opt_out()
    test_pruning_honors_active_link_lease_and_recovers_eviction()
    test_clt_sdk_shim_ignored_for_xcode_discovery()
    test_real_darwin_equivalence_and_cache_hit()
    print("swift_test_compiler_ok")
