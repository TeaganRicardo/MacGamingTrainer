"""Portable Swift contract for issue #706's native rarity reconciliation."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if SWIFTC is None:
    print("acquisition_rarity_swiftc_unavailable")
    raise SystemExit(0)

SOURCE = ROOT / "Sources/Core/UI/TrainerOrderedOptionReconciler.swift"
HARNESS = r"""
import Foundation

@main struct CheckRarity {
    static func main() {
        let order = ["Common", "Rare", "Epic", "Heroic", "Duo", "Legendary", "Perfect"]
        typealias Adjustment = TrainerOrderedOptionResolution.Adjustment
        func check(_ previous: String?, _ supported: [String], expected: String?, change: Adjustment) {
            let result = TrainerOrderedOptionReconciler.resolve(
                previous: previous, supported: supported, preferredOrder: order
            )
            precondition(result.option == expected,
                "bad option fallback for \(String(describing: previous)) -> \(supported)")
            precondition(result.adjustment == change, "bad adjustment state")
        }
        check("Heroic", ["Common", "Rare", "Epic"], expected: "Epic", change: .constrainedToSupported)
        check("Heroic", ["Common", "Legendary"], expected: "Common", change: .constrainedToSupported)
        check("Rare", ["Common", "Legendary"], expected: "Common", change: .constrainedToSupported)
        check("Common", ["Legendary"], expected: "Legendary", change: .constrainedToSupported)
        check("Epic", ["Epic"], expected: "Epic", change: .none)
        check(nil, ["Perfect", "Epic"], expected: "Epic", change: .constrainedToSupported)
        check("Heroic", [], expected: nil, change: .externallyControlled)
        check(nil, [], expected: nil, change: .none)
        let defined = TrainerOrderedOptionReconciler.resolve(
            previous: "Heroic", supported: ["Common", "Legendary"],
            preferredOrder: order, declaredDefault: "Legendary"
        )
        precondition(defined.option == "Legendary" && defined.requiresVisibleConfirmation)
        let unknown = TrainerOrderedOptionReconciler.resolve(
            previous: "Heroic", supported: ["NativeOnly"], preferredOrder: order
        )
        precondition(unknown.option == "NativeOnly")
        let repeated = TrainerOrderedOptionReconciler.resolve(
            previous: "Rare", supported: ["Common", "Rare", "Rare"], preferredOrder: order
        )
        precondition(repeated.option == "Rare" && !repeated.requiresVisibleConfirmation)
        print("acquisition_rarity_contract_ok")
    }
}
"""
with tempfile.TemporaryDirectory(prefix="mgt-706-rarity-") as directory:
    folder = Path(directory)
    harness = folder / "main.swift"
    output = folder / "smoke"
    harness.write_text(HARNESS, encoding="utf-8")
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only this
    # Foundation-level file.
    compile_swift_test(
        modules=[SwiftModule(SWIFT_CORE_MODULE, [SOURCE])],
        harness_sources=[harness], output=output, swiftc=SWIFTC, cwd=ROOT,
    )
    subprocess.run([str(output)], check=True, cwd=ROOT)
