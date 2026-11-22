"""Compile and exercise Host localization on macOS with real Bundle tables."""

MGT_PLATFORM = "macos"
MGT_INPUTS = ("Resources/Localization/", ".github/workflows/build2-macos.yml")

from pathlib import Path
import shutil
import subprocess
import tempfile
from swift_test_compiler import compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
SWIFT = shutil.which("swiftc")
assert SWIFT, "swiftc is required for the macOS localization behavior test"

harness = r'''import Foundation
import Combine
import SwiftUI

@MainActor
@main
struct LocalizationBehaviorTest {
    static func main() {
        // InMemoryDefaults (tests/fixtures/swift) keeps this harness off the
        // real preferences directory; a real suite there cannot be cleaned up
        // afterwards.
        let defaults = InMemoryDefaults()

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
        let registered = missingValue.registerModulePresentation(prefix: "fixture.") { key, arguments, language in
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
        precondition(registered, "valid non-overlapping module prefix must register")
        // Reject invalid, Host-overlapping and mutually overlapping prefixes.
        for badPrefix in ["", ".", "fixture", "fix", "h", "ho", "host", "host.", "host.ext.", "fixture.", "fixture.sub."] {
            let accepted = missingValue.registerModulePresentation(prefix: badPrefix) { key, _, _ in
                "HIJACK[\(badPrefix):\(key)]"
            }
            precondition(!accepted, "invalid or overlapping prefix must be rejected: \(badPrefix)")
        }
        precondition(missingValue.string(TrainerTextToken(key: "host.gameLibrary")) == "游戏库",
                     "rejected overlapping prefix must not hijack Host keys")
        precondition(missingValue.string(TrainerTextToken(key: "fixture.sub.item")) == "fixture.sub.item",
                     "rejected sub-prefix must not override the owning module")
        precondition(missingValue.string(TrainerTextToken(key: "host.ext.item")) == "host.ext.item",
                     "rejected host sub-prefix must not claim host namespace")
        precondition(missingValue.string(TrainerTextToken(key: "hades2.vital.health")) != "HIJACK[fixture:hades2.vital.health]"
                     && missingValue.registerModulePresentation(prefix: "hades.") { _, _, _ in "HADES" },
                     "disjoint sibling dot-terminated prefixes must still be allowed")
        precondition(missingValue.registerModulePresentation(prefix: "hades2.") { _, _, _ in "HADES2" },
                     "prefix validation must distinguish hades. from hades2.")
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
        // Search reads both shipped languages without changing the selected
        // presentation language or persisting a transient lookup preference.
        precondition(missingValue.localized("host.gameLibrary", language: .en) == "Game Library")
        precondition(missingValue.string("host.save.fileCount", arguments: ["3"], language: .en) == "3 files")
        precondition(missingValue.string("fixture.count", arguments: ["4"], language: .en) == "4 Items")
        precondition(missingValue.string("fixture.ready", language: .zhCN) == "夹具就绪")
        precondition(missingValue.string("unowned {0} {1}", arguments: ["value"], language: .en) == "unowned value ")
        precondition(missingValue.language == .zhCN, "explicit lookups must preserve the selection")
        precondition(defaults.string(forKey: TrainerLocalizationStore.userDefaultsKey) == nil,
                     "explicit lookups must not persist a language change")

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
        // An empty or reserved prefix must fail closed even when ignored.
        let emptyPrefix = TrainerLocalizationStore(defaults: defaults)
        precondition(
            !emptyPrefix.registerModulePresentation(prefix: "") { key, _, _ in "MODULE[\(key)]" },
            "empty module prefix must return false"
        )
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

        // Building contexts via TrainerApplicationCoordinator registers every
        // module's presentation immediately without waiting for TrainerHostView.onAppear.
        struct AlphaModule: TrainerGameModule {
            final class Model: TrainerHostModel {
                var connected: Bool { false }
                var statusTitle: TrainerTextToken { .init(key: "alpha.ready") }
                var connectionDetailText: TrainerTextToken { .init(key: "alpha.ready") }
                var hostActionsEnabled: Bool { true }
                func connectFromHost(reason: TrainerHostConnectReason) {}
                func disconnectFromHost() {}
                func refreshFromHost() {}
                func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
            }
            static let descriptor = GameModuleDescriptor(
                id: "alpha", displayName: "Alpha", targetProcessName: "MGTAlphaNone", targetBundleIdentifier: "test.alpha",
                expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 1, supportsSaveManagement: false
            )
            static let presentation = TrainerGamePresentation(sidebarIconSystemName: "circle")
            static let presentationKeyPrefix = "alpha."
            @MainActor static func makeModel(services: TrainerModuleServices) -> Model { Model() }
            @MainActor static func makeContent(model: Model) -> some View { EmptyView() }
            @MainActor static func makeSidebarActions(model: Model) -> some View { EmptyView() }
            @MainActor static func makeHeaderActions(model: Model) -> some View { EmptyView() }
            @MainActor static func makeManagementCommands(model: Model, localization: TrainerLocalizationStore) -> TrainerEmptyCommands { .init() }
            static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
                if key == "alpha.ready" { return language == .en ? "Alpha Ready" : "甲就绪" }
                return key
            }
        }
        struct BetaModule: TrainerGameModule {
            final class Model: TrainerHostModel {
                var connected: Bool { false }
                var statusTitle: TrainerTextToken { .init(key: "beta.ready") }
                var connectionDetailText: TrainerTextToken { .init(key: "beta.ready") }
                var hostActionsEnabled: Bool { true }
                func connectFromHost(reason: TrainerHostConnectReason) {}
                func disconnectFromHost() {}
                func refreshFromHost() {}
                func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
            }
            static let descriptor = GameModuleDescriptor(
                id: "beta", displayName: "Beta", targetProcessName: "MGTBetaNone", targetBundleIdentifier: "test.beta",
                expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 1, supportsSaveManagement: false
            )
            static let presentation = TrainerGamePresentation(sidebarIconSystemName: "square")
            static let presentationKeyPrefix = "beta."
            @MainActor static func makeModel(services: TrainerModuleServices) -> Model { Model() }
            @MainActor static func makeContent(model: Model) -> some View { EmptyView() }
            @MainActor static func makeSidebarActions(model: Model) -> some View { EmptyView() }
            @MainActor static func makeHeaderActions(model: Model) -> some View { EmptyView() }
            @MainActor static func makeManagementCommands(model: Model, localization: TrainerLocalizationStore) -> TrainerEmptyCommands { .init() }
            static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
                if key == "beta.ready" { return language == .en ? "Beta Ready" : "乙就绪" }
                return key
            }
        }
        let coordinatorLocalization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        coordinatorLocalization.language = .en
        let alphaContext = TrainerGameContext<AlphaModule>(session: TrainerBackendSession(),
            backendScriptURL: FileManager.default.temporaryDirectory.appendingPathComponent("missing-alpha.py"),
            logSink: TrainerLogSink(gameID: "alpha", homeDirectory: FileManager.default.temporaryDirectory))
        let betaContext = TrainerGameContext<BetaModule>(session: TrainerBackendSession(),
            backendScriptURL: FileManager.default.temporaryDirectory.appendingPathComponent("missing-beta.py"),
            logSink: TrainerLogSink(gameID: "beta", homeDirectory: FileManager.default.temporaryDirectory))
        defer {
            alphaContext.session.stop(suppressTerminationError: true)
            betaContext.session.stop(suppressTerminationError: true)
        }
        let coordinator = TrainerApplicationCoordinator(
            contexts: [AnyTrainerGameContext(alphaContext), AnyTrainerGameContext(betaContext)],
            localization: coordinatorLocalization
        )
        precondition(coordinator.selectedGameID == "alpha", "coordinator selects initial module")
        precondition(coordinatorLocalization.string(TrainerTextToken(key: "alpha.ready")) == "Alpha Ready",
                     "selected context presentation must register before any view appears")
        precondition(coordinatorLocalization.string(TrainerTextToken(key: "beta.ready")) == "Beta Ready",
                     "unselected context presentation must also register before any view appears")
        precondition(coordinatorLocalization.string(TrainerTextToken(key: "host.save.fileCount", arguments: ["3"])) == "3 files",
                     "registered module prefixes must keep Host key argument resolution intact")
        // Registering a broader parent prefix after a sub-prefix must also fail.
        precondition(missingValue.registerModulePresentation(prefix: "subonly.child.") { _, _, _ in "CHILD" })
        precondition(!missingValue.registerModulePresentation(prefix: "subonly.") { _, _, _ in "PARENT" },
                     "parent prefix overlapping an existing sub-prefix must be rejected")
        precondition(emitted == [.zhCN, .en], "published language must update live observers")
        precondition(TrainerLocalizationStore(defaults: defaults).language == .en, "saved selection must load on next launch")
        missingValue.language = .zhCN
        precondition(defaults.string(forKey: TrainerLocalizationStore.userDefaultsKey) == "zh-CN", "zh-CN selection must persist")
        precondition(TrainerLocalizationStore(defaults: defaults).language == .zhCN, "saved zh-CN selection must load on next launch")
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
    compile_swift_test(
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", harness_path],
        output=executable,
        swiftc=SWIFT,
        cwd=ROOT,
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
