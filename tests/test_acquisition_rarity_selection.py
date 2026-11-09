"""Portable Swift contract for issue #706's native rarity reconciliation."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if SWIFTC is None:
    print("acquisition_rarity_swiftc_unavailable")
    raise SystemExit(0)

SOURCE = ROOT / "Sources/Core/UI/TrainerAcquisitionRarity.swift"
HARNESS = r"""
import Foundation

@main struct CheckRarity {
    static func main() {
        let order = ["Common", "Rare", "Epic", "Heroic", "Duo", "Legendary", "Perfect"]
        typealias Adjustment = TrainerAcquisitionRarityResolution.Adjustment
        func check(_ previous: String?, _ supported: [String], expected: String?, change: Adjustment) {
            let result = TrainerAcquisitionRarity.resolve(
                previous: previous, supported: supported, nativeOrder: order
            )
            precondition(result.rarity == expected,
                "bad rarity fallback for \(String(describing: previous)) -> \(supported)")
            precondition(result.adjustment == change, "bad adjustment state")
        }
        check("Heroic", ["Common", "Rare", "Epic"], expected: "Epic", change: .targetRestricted)
        check("Heroic", ["Common", "Legendary"], expected: "Common", change: .targetRestricted)
        check("Rare", ["Common", "Legendary"], expected: "Common", change: .targetRestricted)
        check("Common", ["Legendary"], expected: "Legendary", change: .targetRestricted)
        check("Epic", ["Epic"], expected: "Epic", change: .none)
        check(nil, ["Perfect", "Epic"], expected: "Epic", change: .targetRestricted)
        check("Heroic", [], expected: nil, change: .gameControlled)
        check(nil, [], expected: nil, change: .none)
        let defined = TrainerAcquisitionRarity.resolve(
            previous: "Heroic", supported: ["Common", "Legendary"],
            nativeOrder: order, declaredDefault: "Legendary"
        )
        precondition(defined.rarity == "Legendary" && defined.requiresVisibleConfirmation)
        let unknown = TrainerAcquisitionRarity.resolve(
            previous: "Heroic", supported: ["NativeOnly"], nativeOrder: order
        )
        precondition(unknown.rarity == "NativeOnly")
        let repeated = TrainerAcquisitionRarity.resolve(
            previous: "Rare", supported: ["Common", "Rare", "Rare"], nativeOrder: order
        )
        precondition(repeated.rarity == "Rare" && !repeated.requiresVisibleConfirmation)
        print("acquisition_rarity_contract_ok")
    }
}
"""
with tempfile.TemporaryDirectory(prefix="mgt-706-rarity-") as directory:
    folder = Path(directory)
    harness = folder / "main.swift"
    output = folder / "smoke"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run([SWIFTC, str(SOURCE), str(harness), "-o", str(output)], check=True, cwd=ROOT)
    subprocess.run([str(output)], check=True, cwd=ROOT)
