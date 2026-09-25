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

        defaults.set("fr", forKey: TrainerLocalizationStore.userDefaultsKey)
        let invalidValue = TrainerLocalizationStore(defaults: defaults)
        precondition(invalidValue.language == .zhCN, "invalid preference must fall back to zh-CN")

        var emitted: [TrainerPresentationLanguage] = []
        let subscription = missingValue.$language.sink { emitted.append($0) }
        missingValue.language = .en
        precondition(defaults.string(forKey: TrainerLocalizationStore.userDefaultsKey) == "en", "selection must persist")
        precondition(missingValue.localized("host.gameLibrary") == "Game Library", "live selection must update lookup")
        precondition(missingValue.localized("host.language") == "Language", "live language menu must update")
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
        [SWIFT, "-parse-as-library", str(ROOT / "Sources/Core/Host/TrainerLocalization.swift"), str(harness_path), "-o", str(executable)],
        check=True,
    )
    result = subprocess.run([str(executable)], check=True, text=True, capture_output=True)
    assert "host_localization_behavior_ok" in result.stdout

print("host_localization_runtime_behavior_ok")
