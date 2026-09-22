from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
swiftc = shutil.which("swiftc")
if not swiftc:
    print("hades2_feature_identity_skipped_no_swiftc")
    raise SystemExit(0)

harness = r'''
import Foundation

let expected = Set([
    "godMode", "infiniteHealth", "infiniteMana", "damageEnabled", "instantCastCooldown",
    "hexAlwaysReady", "infiniteAmmo", "autoMiniGames", "gardenQoL", "boonRarityEnabled",
    "moneyMultiplierEnabled", "resourceMultiplierEnabled",
])
precondition(Set(Hades2FeatureKey.allCases.map(\.rawValue)) == expected)

precondition(ShortcutAction.godMode.featureKey == .godMode)
precondition(ShortcutAction.infiniteHealth.featureKey == .infiniteHealth)
precondition(ShortcutAction.boonRarityEnabled.featureKey == .boonRarityEnabled)
precondition(ShortcutAction.moneyMultiplierEnabled.featureKey == .moneyMultiplierEnabled)
precondition(ShortcutAction.resourceMultiplierEnabled.featureKey == .resourceMultiplierEnabled)
precondition(ShortcutAction.forceLegendary.featureKey == nil)
precondition(ShortcutAction.spawnOlympian.featureKey == nil)
precondition(ShortcutAction.disableAll.featureKey == nil)

let patch = Hades2StatePatch([
    "desiredFeatures": [
        "godMode": true,
        "gardenQoL": false,
        "unknownFeature": true,
    ],
    "activeFeatures": [
        "godMode": true,
        "gameSpeed": true,
    ],
])
precondition(patch.desiredFeatures?[.godMode] == true)
precondition(patch.desiredFeatures?[.gardenQoL] == false)
precondition(patch.desiredFeatures?.count == 2)
precondition(patch.activeFeatures?["godMode"] == true)
precondition(patch.activeFeatures?["gameSpeed"] == true)

print("hades2_feature_identity_ok")
'''

with tempfile.TemporaryDirectory(prefix="mgt-feature-identity-") as td:
    main = Path(td) / "main.swift"
    main.write_text(harness, encoding="utf-8")
    binary = Path(td) / "feature-identity-test"
    subprocess.run([
        swiftc,
        str(ROOT / "Sources/Hades2/Hades2Types.swift"),
        str(ROOT / "Sources/Hades2/Hades2BackendState.swift"),
        str(main),
        "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
