"""Compile and exercise Host localization on macOS with real Bundle tables."""

from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SWIFT = shutil.which("swiftc")
assert SWIFT, "swiftc is required for the macOS localization behavior test"

harness = r'''import Foundation
import Combine

@MainActor
@main
struct LocalizationBehaviorTest {
    static func main() {
        let domain = "HostLocalizationTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: domain)!
        defaults.removePersistentDomain(forName: domain)
        defer { defaults.removePersistentDomain(forName: domain) }

        let missingValue = TrainerLocalizationStore(defaults: defaults)
        precondition(missingValue.language == .zhCN, "missing preference must default to zh-CN")
        precondition(missingValue.localized("host.gameLibrary") == "游戏库", "zh-CN must load from the bundled strings table")
        precondition(missingValue.localized("host.language") == "语言", "zh-CN language menu must load from the bundled table")
        precondition(missingValue.localized("host.save.fileCount", arguments: ["3"]) == "3 个文件", "zh-CN argument substitution must use the shared table")
        precondition(missingValue.presentation("host.connected") == "已连接", "Host key presentation must resolve")
        precondition(
            missingValue.localized("host.timeWarp.error.verifyFailed", arguments: ["2", "1.5"])
                == "Time Warp 设置校验失败（目标 2，实际 1.5）。",
            "zh-CN Time Warp error must resolve through Host.strings with arguments"
        )
        precondition(missingValue.presentation("module-owned copy") == "module-owned copy", "module presentation must remain opaque")

        // A module contributes its own namespace and resolver; Core stores only
        // the closure, so its tokens re-resolve on a language switch.
        missingValue.registerModulePresentation(prefix: "fixture.") { key, arguments, language in
            let tables: [String: [TrainerPresentationLanguage: String]] = [
                "fixture.ready": [.zhCN: "夹具就绪", .en: "Fixture Ready"],
                "fixture.count": [.zhCN: "共 {0} 项", .en: "{0} Items"],
            ]
            guard var value = tables[key]?[language] else { return key }
            for (index, argument) in arguments.enumerated() {
                value = value.replacingOccurrences(of: "{\(index)}", with: argument)
            }
            return value
        }
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.ready")) == "夹具就绪",
            "a registered module namespace must resolve"
        )
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.count", arguments: ["4"])) == "共 4 项",
            "a module token must fill its arguments"
        )
        precondition(
            missingValue.presentation("fixture.ready") == "夹具就绪",
            "module-owned keys must route through the module resolver"
        )
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.missing")) == "fixture.missing",
            "an unknown module key must render as its own identity"
        )

        defaults.set("fr", forKey: TrainerLocalizationStore.userDefaultsKey)
        let invalidValue = TrainerLocalizationStore(defaults: defaults)
        precondition(invalidValue.language == .zhCN, "invalid preference must fall back to zh-CN")

        var emitted: [TrainerPresentationLanguage] = []
        let subscription = missingValue.$language.sink { emitted.append($0) }
        missingValue.language = .en
        precondition(defaults.string(forKey: TrainerLocalizationStore.userDefaultsKey) == "en", "selection must persist")
        precondition(missingValue.localized("host.gameLibrary") == "Game Library", "live selection must update lookup")
        precondition(missingValue.localized("host.language") == "Language", "live language menu must update")
        precondition(missingValue.localized("host.save.fileCount", arguments: ["3"]) == "3 files", "English argument substitution must update live")
        precondition(missingValue.presentation("host.connected") == "Connected", "Host key presentation must update live")
        precondition(
            missingValue.localized("host.timeWarp.error.verifyFailed", arguments: ["2", "1.5"])
                == "Time Warp verification failed (target 2, actual 1.5).",
            "English Time Warp error must update live with arguments"
        )
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.ready")) == "Fixture Ready",
            "a module token must re-resolve on a language switch"
        )
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.count", arguments: ["4"])) == "4 Items",
            "module arguments must re-resolve on a language switch"
        )
        // A module that does not declare its own namespace falls back to the
        // protocol default of "". Every key has that prefix, so the module
        // resolver would swallow Host-owned chrome and replace the whole shell
        // with its own copy. Registering must refuse that.
        let emptyPrefix = TrainerLocalizationStore(defaults: defaults)
        emptyPrefix.registerModulePresentation(prefix: "") { key, _, _ in
            "MODULE[\(key)]"
        }
        precondition(
            emptyPrefix.string(TrainerTextToken(key: "host.gameLibrary")) == "Game Library",
            "an empty module prefix must not hijack Host-owned keys"
        )
        precondition(
            emptyPrefix.presentation("host.disableAll") == "Disable All",
            "an empty module prefix must not hijack Host presentation"
        )
        precondition(
            emptyPrefix.string(TrainerTextToken(key: "unowned.key")) != "MODULE[unowned.key]",
            "an empty module prefix must not claim unowned keys"
        )

        missingValue.removeModulePresentation(prefix: "fixture.")
        precondition(
            missingValue.string(TrainerTextToken(key: "fixture.ready")) == "fixture.ready",
            "removing a module must remove its copy"
        )
        precondition(
            missingValue.localized("host.gameLibrary") == "Game Library",
            "removing a module must not disturb the shared Host table"
        )
        precondition(emitted == [.zhCN, .en], "published language must update live observers")
        precondition(TrainerLocalizationStore(defaults: defaults).language == .en, "saved selection must load on next launch")
        withExtendedLifetime(subscription) { }
        print("host_localization_behavior_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-host-localization-") as temporary:
    temp = Path(temporary)
    for language in ("zh-CN", "en"):
        (temp / f"{language}.lproj").mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", temp / f"{language}.lproj/Host.strings")
    harness_path = temp / "LocalizationBehaviorTest.swift"
    harness_path.write_text(harness, encoding="utf-8")
    executable = temp / "localization-tests"
    subprocess.run(
        [
            SWIFT,
            "-parse-as-library",
            # The token type lives in the Runtime layer, beside the wire identity
            # it travels with, so the Host store alone is no longer compilable.
            str(ROOT / "Sources/Core/Runtime/BackendProcess.swift"),
            str(ROOT / "Sources/Core/Runtime/BackendClient.swift"),
            str(ROOT / "Sources/Core/Host/TrainerLocalization.swift"),
            str(harness_path),
            "-o", str(executable),
        ],
        check=True,
    )
    # No `check=True`. The harness runs the binary and re-raises
    # CalledProcessError when it fails, and that exception's message is only
    # `died with <Signals.SIGTRAP: 5>` -- the diagnostic the child actually
    # printed is captured and then thrown away. So a genuine assertion failure
    # and a genuine crash became indistinguishable from outside, and the gate had
    # to fall back on the bare signal to recognise a Swift catch at all. The
    # signal is not evidence: a force-unwrap nil produces exactly the same one.
    # Asserting on the captured output instead keeps the reason, which is what
    # lets the classifier tell an assertion from a crash.
    result = subprocess.run([str(executable)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "host_localization_behavior_ok" in result.stdout

print("host_localization_runtime_behavior_ok")
