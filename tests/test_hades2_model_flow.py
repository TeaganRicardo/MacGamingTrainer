"""Hades II model/typed API/real Host-session behavior without foreground activation."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from macos_fixture_policy import launch_fixture

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 live-trait model flow test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, pathlib, sys
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
log_path=pathlib.Path(__file__).with_suffix('.commands.jsonl')
ready_path=pathlib.Path(__file__).with_suffix('.ready')
ready_path.write_text('ready', encoding='utf-8')
for raw in sys.stdin:
    req=json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\n')
    observation = pathlib.Path(__file__).with_suffix('.observation.json')
    result = json.loads(observation.read_text()) if observation.exists() else {'connected':True}
    if req['command'] == 'set_desired':
        feature = req['params']['feature']; value = req['params']['value']
        if feature == 'gameSpeed': result['gameSpeed'] = value
        else:
            result.setdefault('desiredFeatures', {})[feature] = value
            result.setdefault('activeFeatures', {})[feature] = value
        if observation.exists(): observation.write_text(json.dumps(result))
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':__MGT_MODULE_PROTOCOL__,'gameID':args.game,'ok':True,
        'result':result,
    }), flush=True)
'''

harness = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fail(message) }
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func commands(at url: URL) -> [[String: Any]] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return text.split(separator: "\n").compactMap {
        try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
    }
}

func makeBoon(
    id: String,
    group: String,
    kind: String = "trait",
    sourceID: String = "Artemis",
    nativeChoice: Bool = false,
    acquisitionMode: String = "",
    targetID: String? = nil,
    rarities: [String] = [],
    supportsLevel: Bool = false
) -> BoonOption {
    BoonOption(
        id: id,
        name: id,
        englishName: id,
        category: group == "exact" ? "角色奖励" : "Character Rewards",
        englishCategory: "Character Rewards",
        kind: kind,
        group: group,
        targetID: targetID ?? (id.hasPrefix("trait:") ? String(id.dropFirst("trait:".count)) : id),
        officialName: true,
        sectionTitle: sourceID,
        englishSectionTitle: sourceID,
        sourceId: sourceID,
        sourceName: sourceID,
        sourceEnglishName: sourceID,
        nativeChoice: nativeChoice,
        nativeChoiceTitle: nativeChoice ? "奖励选择" : "",
        nativeChoiceEnglishTitle: nativeChoice ? "Reward Choice" : "",
        acquisitionMode: acquisitionMode,
        rarities: rarities,
        supportsLevel: supportsLevel,
        sortSection: group == "exact" ? 25 : 30,
        sortGroup: 1,
        sortOrder: 1
    )
}

func makeTrait(
    family: String = "directSpecial",
    lifecycleState: String = "",
    linkedTrait: String = "",
    linkedDisplayName: String = "",
    linkedEnglishName: String = "",
    canAdvanceLifecycle: Bool = false,
    canSetRemainingUses: Bool = false,
    canExpire: Bool = false,
    levelCapability: TraitLevelCapability = .increaseOne,
    rarityCapability: TraitRarityCapability = .setExact,
    removalCapability: TraitRemovalCapability = .singleInstanceForce
) -> CurrentRunTrait {
    CurrentRunTrait(
        generationID: "generation-55",
        runID: "run-table-1",
        instanceID: "4242",
        name: "OmegaExplodeBoon",
        displayName: "爆裂欧米伽",
        englishName: "Omega Explosion",
        family: family,
        sourceID: "Icarus",
        sourceName: "伊卡洛斯",
        sourceEnglishName: "Icarus",
        level: 2,
        rarity: "Rare",
        availableRarities: ["Common", "Rare", "Epic", "Heroic"],
        sameNameCount: 1,
        remainingUses: nil,
        lifecycleState: lifecycleState,
        linkedTrait: linkedTrait,
        linkedDisplayName: linkedDisplayName,
        linkedEnglishName: linkedEnglishName,
        canAdvanceLifecycle: canAdvanceLifecycle,
        canSetRemainingUses: canSetRemainingUses,
        canExpire: canExpire,
        levelCapability: levelCapability,
        levelReason: "",
        rarityCapability: rarityCapability,
        rarityReason: "",
        removalCapability: removalCapability,
        removalReason: "",
        removalScopeAllMatching: false,
        deferredIssue: nil
    )
}

func requireTargetParams(
    _ command: [String: Any],
    expectedFamily: String = "directSpecial",
    expectedTargetLevel: Int? = nil,
    expectedRarity: String? = nil
) {
    guard let params = command["params"] as? [String: Any] else {
        fail("missing params: \(command)")
    }
    check(params["generationId"] as? String == "generation-55", "generation snapshot lost")
    check(params["runId"] as? String == "run-table-1", "run snapshot lost")
    check(params["instanceId"] as? String == "4242", "instance snapshot lost")
    check(params["trait"] as? String == "OmegaExplodeBoon", "trait identity lost")
    check(params["family"] as? String == expectedFamily, "family identity lost")
    check(params["expectedLevel"] as? Int == 2, "expected level lost")
    check(params["expectedRarity"] as? String == "Rare", "expected rarity lost")
    check(params["expectedSameNameCount"] as? Int == 1, "same-name snapshot lost")
    if let expectedTargetLevel {
        check(params["targetLevel"] as? Int == expectedTargetLevel, "requested target level lost")
    } else {
        check(params["targetLevel"] == nil, "unexpected target-level parameter")
    }
    if let expectedRarity {
        check(params["rarity"] as? String == expectedRarity, "requested rarity lost")
    } else {
        check(params["rarity"] == nil, "unexpected rarity parameter")
    }
}

@main
struct Main {
    @MainActor
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 3 else { fail("expected python + worker") }
        let python = URL(fileURLWithPath: args[1])
        let worker = URL(fileURLWithPath: args[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
        try? FileManager.default.removeItem(at: commandLog)

        func waitForWorkerReady(_ url: URL, timeout: TimeInterval = 4.0) {
            let deadline = Date().addingTimeInterval(timeout)
            while Date() < deadline {
                if FileManager.default.fileExists(atPath: url.path) { return }
                pump(0.02)
            }
            fail("backend worker did not become ready before timeout")
        }

        func waitForCommandCount(_ expected: Int, timeout: TimeInterval = 4.0) {
            let deadline = Date().addingTimeInterval(timeout)
            while Date() < deadline {
                if commands(at: commandLog).count >= expected { return }
                pump(0.02)
            }
            fail("backend worker did not receive expected command count \(expected): \(commands(at: commandLog))")
        }

        func withModel(expectedNewCommands: Int, _ body: (Hades2TrainerModel) -> Void) throws {
            let ready = worker.deletingPathExtension().appendingPathExtension("ready")
            try? FileManager.default.removeItem(at: ready)
            let before = commands(at: commandLog).count
            let process = BackendProcess(
                executableURL: python,
                argumentsPrefix: ["-u"],
                forceKillDelay: 0.10
            )
            let session = TrainerBackendSession(client: BackendClient(process: process))
            try session.start(
                descriptor: Hades2GameModule.descriptor,
                backendScriptURL: worker,
                applyPayload: { _ in },
                resetGameState: {},
                log: { _ in },
                onStatusChange: { _ in }
            )
            waitForWorkerReady(ready)
            let model = Hades2TrainerModel(
                session: session,
                logSink: TrainerLogSink(gameID: Hades2GameModule.descriptor.id),
                shortcutDefaults: InMemoryDefaults()
            )
            model.connected = true
            model.status = "ready"
            model.scene = "run"
            model.capabilities["traitMutation"] = true
            body(model)

            let expectedTotal = before + expectedNewCommands
            if expectedNewCommands > 0 {
                waitForCommandCount(expectedTotal)
            } else {
                // The worker is already proven ready, so this window checks that
                // capability/model guards do not enqueue a command at all.
                pump(0.20)
            }
            check(
                commands(at: commandLog).count == expectedTotal,
                "model flow emitted wrong command count: expected \(expectedTotal), got \(commands(at: commandLog))"
            )
            session.stop()
            pump(0.15)
        }

        let trait = makeTrait()
        let chaosTrait = makeTrait(
            family: "chaos",
            lifecycleState: "curse",
            linkedTrait: "ChaosHealthBlessing",
            linkedDisplayName: "丰盛",
            linkedEnglishName: "Affluence",
            canAdvanceLifecycle: true
        )
        try withModel(expectedNewCommands: 1) { $0.setTraitLevel(trait, targetLevel: "5") }
        try withModel(expectedNewCommands: 1) { $0.setTraitRarity(trait, rarity: "Epic") }
        try withModel(expectedNewCommands: 1) { $0.removeTrait(trait) }
        try withModel(expectedNewCommands: 1) { $0.advanceTraitLifecycle(chaosTrait) }

        let sent = commands(at: commandLog)
        check(sent.count == 4, "expected exactly four live-trait commands, got \(sent)")
        check(sent[0]["command"] as? String == "set_trait_level", "wrong level command")
        check(sent[1]["command"] as? String == "set_trait_rarity", "wrong rarity command")
        check(sent[2]["command"] as? String == "remove_trait", "wrong removal command")
        check(sent[3]["command"] as? String == "advance_trait_lifecycle", "wrong Chaos lifecycle command")
        requireTargetParams(sent[0], expectedTargetLevel: 5)
        requireTargetParams(sent[1], expectedRarity: "Epic")
        requireTargetParams(sent[2])
        requireTargetParams(sent[3], expectedFamily: "chaos")

        // Trait-specific capability and row semantics fail closed before the
        // backend transport boundary. Presentation scene is deliberately not
        // an independent native-action gate.
        try withModel(expectedNewCommands: 0) { model in
            let blocked = makeTrait(
                levelCapability: .none,
                rarityCapability: .none,
                removalCapability: .none
            )
            model.setTraitLevel(blocked, targetLevel: "5")
            model.setTraitRarity(blocked, rarity: "Epic")
            model.removeTrait(blocked)
            model.advanceTraitLifecycle(blocked)
            model.capabilities["traitMutation"] = false
            model.scene = "loading"
            model.setTraitLevel(trait, targetLevel: "5")
            model.setTraitRarity(trait, rarity: "Heroic")
            model.removeTrait(trait)
            model.advanceTraitLifecycle(chaosTrait)
            model.capabilities["traitMutation"] = true
            model.scene = "run"
            model.setTraitLevel(trait, targetLevel: "2")
            model.setTraitLevel(trait, targetLevel: "1")
            model.setTraitLevel(trait, targetLevel: "not-a-level")
        }
        check(commands(at: commandLog).count == 4, "guarded trait operation reached backend transport")

        // Exact acquisition is a separate catalog surface. Individual exact
        // targets do not leak back into Character Rewards, but their source can
        // still synthesize the native choice entry point.
        let exact = makeBoon(
            id: "trait:CritBonusBoon",
            group: "exact",
            nativeChoice: true,
            acquisitionMode: "direct",
            rarities: ["Common", "Rare", "Epic", "Heroic"],
            supportsLevel: true
        )
        let special = makeBoon(id: "TalentDrop", group: "special", kind: "consumable", sourceID: "Selene")
        try withModel(expectedNewCommands: 1) { model in
            model.capabilities["acquireExactReward"] = true
            model.capabilities["spawnReward"] = false
            model.boons = [exact, special]
            check(model.exactBoonOptions.map(\.id) == [exact.id], "exact catalog projection is wrong")
            check(!model.specialRewardOptions.contains { $0.id == exact.id }, "exact trait leaked into Character Rewards")
            check(model.specialRewardOptions.contains { $0.id == special.id }, "non-boon character reward disappeared")
            check(model.specialRewardOptions.contains { $0.id == "native-choice:Artemis" }, "native character choice entry disappeared")
            model.selectedExactBoon = exact.id
            model.acquisitionLevel = "3"
            check(model.acquireExactBoon(exact.id), "exact acquisition was rejected")
        }
        let afterExact = commands(at: commandLog)
        check(afterExact.count == 5, "exact acquisition did not emit one command: \(afterExact)")
        check(afterExact[4]["command"] as? String == "spawn_reward", "exact acquisition used the wrong command")
        guard let exactParams = afterExact[4]["params"] as? [String: Any] else { fail("exact acquisition params missing") }
        check(exactParams["reward"] as? String == exact.id, "exact acquisition lost reward identity")
        check(exactParams["rarity"] as? String == "Heroic" && exactParams["level"] as? Int == 3,
              "exact acquisition did not forward independent rarity and stack level")

        // Deterministic Chaos acquisition carries both native TraitData identities
        // in one one-shot request; row ids and localized labels never cross the
        // typed Hades request boundary.
        let chaosBlessing = makeBoon(
            id: "chaos:blessing:ChaosHealthBlessing",
            group: "exact",
            sourceID: "Chaos",
            acquisitionMode: "chaosBlessing",
            targetID: "ChaosHealthBlessing",
            rarities: ["Common", "Rare", "Epic"],
            supportsLevel: false
        )
        let chaosCurse = makeBoon(
            id: "chaos:curse:ChaosDamageCurse",
            group: "exact",
            sourceID: "Chaos",
            acquisitionMode: "chaosCurse",
            targetID: "ChaosDamageCurse"
        )
        try withModel(expectedNewCommands: 1) { model in
            model.capabilities["acquireChaosPair"] = true
            model.boons = [chaosBlessing, chaosCurse]
            model.selectedChaosBlessing = chaosBlessing.id
            model.selectedChaosCurse = chaosCurse.id
            model.acquisitionRarity = "Epic"
            check(model.acquireChaosPair(
                blessingReward: chaosBlessing.id,
                curseReward: chaosCurse.id
            ), "Chaos pair acquisition was rejected")
        }
        let afterChaosPair = commands(at: commandLog)
        check(afterChaosPair.count == 6, "Chaos pair acquisition did not emit one command: \(afterChaosPair)")
        check(afterChaosPair[5]["command"] as? String == "acquire_chaos_pair", "Chaos pair used the wrong command")
        guard let chaosParams = afterChaosPair[5]["params"] as? [String: Any] else {
            fail("Chaos pair acquisition params missing")
        }
        check(chaosParams["blessing"] as? String == "ChaosHealthBlessing", "Chaos blessing identity drifted")
        check(chaosParams["curse"] as? String == "ChaosDamageCurse", "Chaos curse identity drifted")
        check(chaosParams["rarity"] as? String == "Epic", "Chaos pair lost selected rarity")
        check(chaosParams["level"] == nil, "nonstackable Chaos pair forwarded a level")

        // The same Core level editor serves multiple native targets. A target
        // change resets its draft; unchanged observations retain the draft.
        try withModel(expectedNewCommands: 0) { model in
            model.boons = [exact, chaosBlessing, chaosCurse]
            model.selectedExactBoon = exact.id
            check(model.activateAcquisition(.exact), "exact target could not activate")
            model.acquisitionLevel = "7"
            model.selectedChaosBlessing = chaosBlessing.id
            model.selectedChaosCurse = chaosCurse.id
            check(model.activateAcquisition(.chaos), "Chaos target could not activate")
            check(model.acquisitionLevel == "1", "Hades II retained another target's draft level")
            model.acquisitionLevel = "4"
            check(model.activateAcquisition(.chaos), "unchanged Chaos target lost its selection")
            check(model.acquisitionLevel == "4", "unchanged Chaos target reset the level draft")
            check(model.activateAcquisition(.exact), "return to exact target refused")
            check(model.acquisitionLevel == "1", "returning to exact reused the Chaos level draft")
        }

        // The shipped model owns decoding and completion on this path. No
        // native view, field editor, window or foreground activation is used.
        let observation = worker.deletingPathExtension().appendingPathExtension("observation.json")
        func writeObservation(speed: Double) throws {
            let value: [String: Any] = ["connected": true, "status": "ready", "scene": "run",
                "gameSpeed": speed, "capabilities": ["setFeature": true],
                "featureSupport": ["gameSpeed": true, "invincibility": true],
                "desiredFeatures": ["invincibility": false], "activeFeatures": ["invincibility": false]]
            try JSONSerialization.data(withJSONObject: value).write(to: observation)
        }
        try writeObservation(speed: 1.0)
        let observedSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python)))
        let observedModel = Hades2TrainerModel(session: observedSession,
            logSink: TrainerLogSink(gameID: Hades2GameModule.descriptor.id), backendScriptURL: worker,
            shortcutDefaults: InMemoryDefaults())
        observedModel.hostTargetLifetimeChanged(observation: TrainerTargetObservation(isRunning: false, launchGeneration: 0, processIdentifier: nil))
        func waitFor(_ description: String, _ predicate: () -> Bool) {
            let deadline = Date().addingTimeInterval(10)
            while !predicate() && Date() < deadline { pump(0.01) }
            check(predicate(), description)
        }
        waitFor("model failed initial observation") { observedModel.backendAvailable && observedModel.connected && !observedModel.busy }
        let beforeCommit = commands(at: commandLog).count
        let commit = observedModel.completeTextEdit(.gameSpeed, text: "1.7", generation: observedModel.editGeneration)
        check(commit == "1.7", "explicit numeric commit was not normalized")
        waitFor("explicit commit did not finish") { commands(at: commandLog).count == beforeCommit + 1 && !observedModel.busy }
        check(observedModel.gameSpeed == 1.7, "committed observation was not projected")
        let featureBefore = commands(at: commandLog).count
        var featureDone: Bool? = nil
        observedModel.feature(.invincibility, value: true, completion: { featureDone = $0 })
        waitFor("desired/active feature receipt was not delivered") { featureDone != nil && !observedModel.busy }
        check(featureDone == true && observedModel.invincibility && observedModel.activeFeatures["invincibility"] == true,
              "desired state and runtime observation diverged")
        check(commands(at: commandLog).count == featureBefore + 1, "feature intent was replayed")
        try writeObservation(speed: 2.3)
        observedModel.refreshFromHost()
        waitFor("external observation did not refresh") { observedModel.gameSpeed == 2.3 && !observedModel.busy }
        let beforeInvalid = commands(at: commandLog).count
        let rejected = observedModel.completeTextEdit(.gameSpeed, text: "invalid", generation: observedModel.editGeneration)
        check(rejected == "2.3" && observedModel.feedbackNotice != nil,
              "invalid explicit edit did not restore observed value and feedback")
        check(commands(at: commandLog).count == beforeInvalid, "invalid edit crossed the transport boundary")
        observedSession.stop()
        print("hades2_live_trait_model_flow_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-live-trait-model-flow-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "live_trait_model_flow"
    home = td / "home"
    home.mkdir()
    worker_path.write_text(textwrap.dedent(worker.replace("__MGT_MODULE_PROTOCOL__", str(json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["protocolVersion"]))), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")

    generated = td / "ActiveGame.generated.swift"
    subprocess.run(
        [PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
        check=True,
        cwd=ROOT,
    )
    # This harness drives the live-trait model only; it never builds a
    # TrainerLocalizationStore, so it does not need the in-memory defaults.
    sources = (
        sorted((ROOT / "Sources/Core").rglob("*.swift"))
        + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
        + [ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", generated, main_path]
    )
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CFFIXED_USER_HOME"] = str(home)
    proc = launch_fixture(
        [str(binary), PYTHON, str(worker_path)],
        journey="hades2.live_trait_flow",
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_live_trait_model_flow_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
