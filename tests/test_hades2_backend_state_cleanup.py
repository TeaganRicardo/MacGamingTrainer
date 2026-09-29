import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 Swift state cleanup test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

harness = r'''
import Darwin
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    guard condition() else {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

@main
struct Main {
    static func main() {
        let session = TrainerBackendSession()
        let model = Hades2TrainerModel(
            session: session,
            logSink: TrainerLogSink(url: URL(fileURLWithPath: "/dev/null"))
        )

        // U-03: a sparse payload cannot clear a warning. Explicit null or an
        // empty warnings array clears it; nonempty values replace it.
        model.warning = "stale warning"
        model.apply([:])
        check(model.warning == "stale warning", "absent warning cleared the prior value")
        model.apply(["warning": NSNull()])
        check(model.warning.isEmpty, "null warning did not clear the prior value")
        model.apply(["warnings": ["current warning"]])
        check(model.warning == "current warning", "present warnings array was not displayed")
        model.apply(["status": "ready"])
        check(model.warning == "current warning", "unrelated status erased the warning")
        model.apply(["warnings": [String]()])
        check(model.warning.isEmpty, "empty warnings array did not clear the prior value")
        model.apply(["warning": "current warning"])
        check(model.warning == "current warning", "present warning string was not displayed")
        model.apply(["warnings": NSNull(), "warning": "stale legacy warning"])
        check(model.warning.isEmpty, "null warnings did not clear or defer to legacy warning")
        model.apply(["warnings": ["array wins"], "warning": "legacy value"])
        check(model.warning == "array wins", "warnings array did not take precedence")

        // A Core-owned feature failure keeps its Host presentation identity and
        // arguments across the untyped backend payload. Legacy runtime-owned
        // featureErrors remain usable beside it rather than forcing either
        // owner into the other's localization table.
        model.apply([
            "featureErrors": ["godMode": "native runtime refusal"],
            "featureErrorPresentations": [
                "gameSpeed": [
                    "presentation": "host.timeWarp.error.setFailed",
                    "arguments": [-7],
                ],
            ],
        ])
        check(model.runtimeIssuePresentations.count == 2,
              "runtime issue owners were not merged")
        let speedIssue = model.runtimeIssuePresentations.first { $0.featureID == "gameSpeed" }
        check(speedIssue?.token.key == "host.timeWarp.error.setFailed",
              "Host feature presentation key was flattened or lost")
        check(speedIssue?.token.arguments == ["-7"],
              "Host feature presentation arguments were lost")
        model.apply(["status": "ready"])
        check(model.runtimeIssuePresentations.count == 2,
              "sparse state update erased runtime issue presentations")

        // Seed both runtime observations and durable desired intent.
        model.godMode = true
        model.gameSpeed = 2.5
        model.damageMultiplier = 3.0
        model.moneyMultiplier = 4.0
        model.resourceMultiplier = 5.0
        model.boonRarityTarget = "Legendary"
        model.boonRarityMultiplier = 175.0
        model.boonForceLegendary = true
        model.boonForceDuo = true
        model.moneyMultiplierEnabled = true
        model.resourceMultiplierEnabled = true
        model.nextRoomReward = "RoomMoneyDrop"

        model.connected = true
        model.pid = 123
        model.version = "1.139672"
        model.scene = "run"
        model.capabilities = ["setVitals": true]
        model.activeFeatures = ["godMode": true]
        model.dormantFeatures = ["infiniteMana": true]
        model.featureSupport = ["godMode": true]
        model.statSupport = ["grasp": true]
        model.statAvailable = ["grasp": true]
        model.health = 99
        model.maxHealth = 120
        model.healthLocked = true
        model.mana = 44
        model.maxMana = 60
        model.manaLocked = false
        model.armor = 7
        model.armorLocked = true
        model.spellCharge = 12
        model.spellChargeCost = 20
        model.money = 321
        model.moneyLocked = true
        model.rerolls = 4
        model.rerollsLocked = true
        model.runCount = 9
        model.graspValue = 30
        model.graspLocked = true
        model.dodgeValue = 12.5
        model.dodgeLocked = false
        model.critValue = 13
        model.chargeSpeedValue = 14
        model.moveSpeedValue = 15
        model.sprintSpeedValue = 16
        model.dashSpeedValue = 17
        model.attackSpeedValue = 18
        model.manaRegenValue = 19
        model.enemyDamageValue = 20
        model.enemyHealthValue = 21
        model.elements = [ElementCount(id: "Fire", name: "火", count: 8, locked: true)]
        model.resources = [MaterialResource(
            id: "Bones", name: "骨头", englishName: "Bones", count: 10, locked: true,
            sectionTitle: "资源", englishSectionTitle: "Resources", sortOrder: 0
        )]
        model.boons = [BoonOption(
            id: "boon", name: "祝福", englishName: "Boon", category: "祝福", englishCategory: "Boon",
            kind: "loot", group: "pickup", sectionTitle: "", englishSectionTitle: "", sourceId: "",
            sourceName: "", sourceEnglishName: "", nativeChoice: false, nativeChoiceTitle: "",
            nativeChoiceEnglishTitle: "", sortSection: 0, sortGroup: 0, sortOrder: 0
        )]
        model.diagnostics = [DiagnosticCheck(name: "check", ok: false, detail: "detail")]
        model.diagnosticsPassed = 0
        model.diagnosticsTotal = 1
        model.warning = "runtime warning"
        model.runtimeIssue = "runtime issue"

        let receipt: [String: Any] = [
            "requestId": "request-1",
            "command": "open_special_choice",
            "outcome": "accepted",
        ]
        // A failed receipt is the case that must not mask a later message.
        let failedReceipt: [String: Any] = [
            "requestId": "request-2",
            "command": "open_special_choice",
            "outcome": "failed",
            "error": "synthetic failure",
        ]
        model.apply(["lastAction": receipt])
        check(!model.noticeText.key.isEmpty, "action receipt was not presented before reset")
        check(model.noticeText.key == "hades2.receipt.accepted", "receipt did not present the accepted copy")

        model.resetAfterBackendTermination()

        // U-04: backend termination must discard only observed/session state.
        check(!model.connected && model.pid == nil, "connection identity survived termination")
        // An undetected version is the empty language-neutral state; the
        // connection detail resolves it to the awaiting-detection key.
        check(model.version.isEmpty, "runtime version survived termination")
        check(model.connectionDetailText.key == "hades2.status.awaitingDetect",
              "awaiting-detection state was not restored")
        check(model.scene == "unknown", "scene survived termination")
        check(model.capabilities.isEmpty && model.activeFeatures.isEmpty && model.dormantFeatures.isEmpty,
              "runtime feature state survived termination")
        check(model.featureSupport.isEmpty && model.statSupport.isEmpty && model.statAvailable.isEmpty,
              "runtime support state survived termination")
        check(model.health == 99 && model.maxHealth == 120 && model.healthLocked,
              "durable locked health target was cleared")
        check(model.mana == nil && model.maxMana == nil && !model.manaLocked,
              "unlocked mana observation survived termination")
        check(model.armor == 7 && model.armorLocked,
              "durable locked armor target was cleared")
        check(model.spellCharge == nil && model.spellChargeCost == nil,
              "spell charge state survived termination")
        check(model.money == 321 && model.moneyLocked && model.rerolls == 4 && model.rerollsLocked,
              "durable locked resource targets were cleared")
        check(model.graspValue == 30 && model.graspLocked && model.dodgeValue == nil && !model.dodgeLocked,
              "stat target or observation termination handling is incorrect")
        check(model.critValue == nil && model.chargeSpeedValue == nil && model.moveSpeedValue == nil
                && model.sprintSpeedValue == nil && model.dashSpeedValue == nil
                && model.attackSpeedValue == nil && model.manaRegenValue == nil
                && model.enemyDamageValue == nil && model.enemyHealthValue == nil,
              "unlocked stat observations survived termination")
        check(model.runCount == nil, "run count survived termination")
        check(model.elements.isEmpty && model.resources.isEmpty && model.boons.isEmpty,
              "runtime collections survived termination")
        check(model.diagnostics.isEmpty && model.diagnosticsPassed == 0 && model.diagnosticsTotal == 0,
              "diagnostics survived termination")
        check(model.warning.isEmpty && model.runtimeIssue.isEmpty,
              "runtime messages survived termination")
        check(model.noticeText.key.isEmpty && model.errorText.key.isEmpty
                && model.runtimeIssueText.key.isEmpty
                && model.runtimeIssuePresentations.isEmpty,
              "presentation tokens survived termination")

        // A Hades-owned token must not outlive a newer Core-owned message.
        // The banner prefers the Hades token, so a stale receipt error would
        // otherwise mask a real Core failure -- and a real success notice.
        model.apply(["lastAction": failedReceipt])
        check(!model.errorText.key.isEmpty, "a failed receipt did not present an error")
        model.error = "host.backend.error.operationFailed"
        check(model.errorText.key.isEmpty,
              "a stale Hades error token masked a newer Core-owned error")
        model.notice = "host.backend.notice.completed"
        check(model.errorText.key.isEmpty && model.noticeText.key.isEmpty,
              "a failed receipt masked a later success notice")
        model.clearPresentedNoticeForTest()
        model.clearPresentedErrorForTest()

        // A failed non-idempotent action must never present as success. The
        // removal path is a runtime mutation wrapped in pcall, so it reports
        // failure through the receipt rather than by raising; if the model
        // missed remove_trait, the player saw a green success while the trait
        // was still owned. Asserted on presented state, not on source text.
        model.clearPresentedNoticeForTest()
        model.clearPresentedErrorForTest()
        model.apply(["lastAction": [
            "requestId": "request-3",
            "command": "remove_trait",
            "outcome": "failed",
            "error": "Trait is not sell-eligible, so no safe removal exists: BoonOfHermes",
        ]])
        check(model.noticeText.key.isEmpty,
              "a failed trait removal presented a success notice")
        check(!model.errorText.key.isEmpty,
              "a failed trait removal presented no error")
        check(model.errorText.key.hasPrefix("hades2."),
              "a failed trait removal did not present Hades-owned copy")

        // The receipt must be forgotten so an identical receipt from a new
        // backend lifetime is presented rather than deduplicated as stale.
        model.apply(["lastAction": receipt])
        check(!model.noticeText.key.isEmpty, "last action receipt was not presented after termination")
        // Deduplication is keyed on receipt identity, not on the presented copy,
        // so the same receipt is suppressed until the copy is cleared.
        model.clearPresentedNoticeForTest()
        model.apply(["lastAction": receipt])
        check(model.noticeText.key.isEmpty, "identical receipt was not deduplicated within one backend lifetime")
        model.resetAfterBackendTermination()
        model.clearPresentedNoticeForTest()
        model.apply(["lastAction": receipt])
        check(!model.noticeText.key.isEmpty, "last action receipt deduplication survived backend termination")

        // Durable desired intent remains available for replay.
        check(model.godMode && model.gameSpeed == 2.5 && model.damageMultiplier == 3.0,
              "durable feature intent was cleared")
        check(model.moneyMultiplier == 4.0 && model.resourceMultiplier == 5.0,
              "durable multiplier intent was cleared")
        check(model.boonRarityTarget == "Legendary" && model.boonRarityMultiplier == 175.0,
              "durable boon rarity intent was cleared")
        check(model.boonForceLegendary && model.boonForceDuo && model.nextRoomReward == "RoomMoneyDrop",
              "durable reward intent was cleared")
        check(model.moneyMultiplierEnabled && model.resourceMultiplierEnabled,
              "durable multiplier toggles were cleared")

        print("hades2_backend_state_cleanup_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-state-cleanup-") as td:
    td = Path(td)
    main_path = td / "main.swift"
    binary = td / "state_cleanup"
    main_path.write_text(harness, encoding="utf-8")

    model_source = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
    model_source = model_source.replace("private func apply(_ payload:", "func apply(_ payload:")
    model_source = model_source.replace("private func resetAfterBackendTermination()", "func resetAfterBackendTermination()")
    # The presented-copy token is private state; expose a clear for the harness
    # so a test can reset what it just consumed.
    model_source = model_source.replace(
        "    @Published private var noticeToken: TrainerTextToken?",
        "    @Published var noticeToken: TrainerTextToken?\n"
        "    func clearPresentedNoticeForTest() { noticeToken = nil }\n"
        "    func clearPresentedErrorForTest() { errorToken = nil }",
    )
    testable_model = td / "Hades2Model.swift"
    testable_model.write_text(model_source, encoding="utf-8")

    generated = td / "ActiveGame.generated.swift"
    subprocess.run(
        [PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
        check=True,
        cwd=ROOT,
    )
    sources = (
        sorted((ROOT / "Sources/Core").rglob("*.swift"))
        + [path for path in sorted((ROOT / "Sources/Hades2").rglob("*.swift")) if path.name != "Hades2Model.swift"]
        + [testable_model, generated, main_path]
    )
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(td / "home")
    (td / "home").mkdir()
    subprocess.run([str(binary)], check=True, cwd=ROOT, env=env)
