import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 SwiftUI state-flow test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, pathlib, sys
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
log_path=pathlib.Path(__file__).with_suffix('.commands.jsonl')
for raw in sys.stdin:
    req=json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\n')
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,
        'result':{'connected':True},
    }), flush=True)
'''

harness = r'''
import AppKit
import Foundation
import SwiftUI

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
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

@main
struct Main {
    @MainActor
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 3 else { fail("expected python + worker") }
        let python = URL(fileURLWithPath: args[1])
        let worker = URL(fileURLWithPath: args[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")

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

        let model = Hades2GameModule.makeModel(session: session)
        // InMemoryDefaults (tests/fixtures/swift) keeps this harness off the
        // real preferences directory; a real suite there cannot be cleaned up
        // afterwards.
        let localizationDefaults = InMemoryDefaults()
        let localization = TrainerLocalizationStore(defaults: localizationDefaults)
        let host = NSHostingView(
            rootView: Hades2TrainerView(model: model)
                .environmentObject(localization)
        )
        host.frame = NSRect(x: 0, y: 0, width: 1200, height: 900)
        host.layoutSubtreeIfNeeded()
        pump(0.10)

        try? FileManager.default.removeItem(at: commandLog)

        model.connected = true
        model.capabilities = [
            "setVitals": true,
            "setResource": true,
            "setStats": true,
            "setElements": true,
        ]
        model.statSupport = ["dodge": true]
        model.statAvailable = ["dodge": true]
        model.health = 99.5
        model.maxHealth = 120.5
        model.mana = 44.5
        model.maxMana = 60.5
        model.armor = 7.5
        model.spellCharge = 12.5
        model.money = 123.5
        model.rerolls = 3.5
        model.dodgeValue = 12.345
        model.dodgeLocked = true
        model.damageMultiplier = 2.75
        model.moneyMultiplier = 3.5
        model.resourceMultiplier = 4.25
        model.boonRarityMultiplier = 135.5
        model.gameSpeed = 1.3
        model.elements = [ElementCount(id: "Fire", name: "火", count: 4.5, locked: false)]

        host.layoutSubtreeIfNeeded()
        pump(0.80)

        let passiveMutations = commands(at: commandLog).filter {
            guard let command = $0["command"] as? String else { return false }
            return command.hasPrefix("set_") || command.hasPrefix("lock_")
        }
        if !passiveMutations.isEmpty {
            fail("passive model projection emitted mutations: \(passiveMutations)")
        }

        // Model-level delayed-lock contract: unlocking a stat must cancel only
        // its own stale relock and leave the immediate unlock as the final intent.
        try? FileManager.default.removeItem(at: commandLog)
        model.setStat("dodge", text: "33.3", locked: true)
        model.setStat("dodge", text: "33.3", locked: false)
        pump(0.60)
        let statCommands = commands(at: commandLog).filter { ($0["command"] as? String) == "set_stat" }
        if statCommands.count != 1 { fail("unlock/relock emitted wrong set_stat count: \(statCommands)") }
        let params = statCommands[0]["params"] as? [String: Any]
        if params?["stat"] as? String != "dodge" || params?["locked"] as? Bool != false {
            fail("stale locked=true mutation survived unlock: \(statCommands)")
        }

        let editGeneration = model.editGeneration
        model.toggleConnectionFromHost()
        if model.editGeneration == editGeneration {
            fail("disconnect barrier did not invalidate editor drafts")
        }
        pump(0.20)

        session.stop()
        pump(0.20)
        print("hades2_view_state_flow_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-view-state-flow-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "view_state_flow"
    home = td / "home"
    home.mkdir()
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")

    generated = td / "ActiveGame.generated.swift"
    subprocess.run(
        [PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
        check=True,
        cwd=ROOT,
    )
    sources = (
        sorted((ROOT / "Sources/Core").rglob("*.swift"))
        + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
        + [
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            generated,
            main_path,
        ]
    )
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    proc = subprocess.run(
        [str(binary), PYTHON, str(worker_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())

# Live-trait Model -> API -> BackendSession transport coverage belongs to the
# existing Hades view/model state-flow owner rather than a standalone regression file.
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

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
for raw in sys.stdin:
    req=json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\n')
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,
        'result':{'connected':True},
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
    acquisitionMode: String = ""
) -> BoonOption {
    BoonOption(
        id: id,
        name: id,
        englishName: id,
        category: group == "exact" ? "角色奖励" : "Character Rewards",
        englishCategory: "Character Rewards",
        kind: kind,
        group: group,
        targetID: id.hasPrefix("trait:") ? String(id.dropFirst("trait:".count)) : id,
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
        sortSection: group == "exact" ? 25 : 30,
        sortGroup: 1,
        sortOrder: 1
    )
}

func makeTrait(
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
        family: "directSpecial",
        sourceID: "Icarus",
        sourceName: "伊卡洛斯",
        sourceEnglishName: "Icarus",
        level: 2,
        rarity: "Rare",
        availableRarities: ["Common", "Rare", "Epic", "Heroic"],
        sameNameCount: 1,
        remainingUses: nil,
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

func requireTargetParams(_ command: [String: Any], expectedRarity: String? = nil) {
    guard let params = command["params"] as? [String: Any] else {
        fail("missing params: \(command)")
    }
    check(params["generationId"] as? String == "generation-55", "generation snapshot lost")
    check(params["runId"] as? String == "run-table-1", "run snapshot lost")
    check(params["instanceId"] as? String == "4242", "instance snapshot lost")
    check(params["trait"] as? String == "OmegaExplodeBoon", "trait identity lost")
    check(params["family"] as? String == "directSpecial", "family identity lost")
    check(params["expectedLevel"] as? Int == 2, "expected level lost")
    check(params["expectedRarity"] as? String == "Rare", "expected rarity lost")
    check(params["expectedSameNameCount"] as? Int == 1, "same-name snapshot lost")
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

        func withModel(_ body: (Hades2TrainerModel) -> Void) throws {
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
            let model = Hades2GameModule.makeModel(session: session)
            pump(0.10)
            model.connected = true
            model.status = "ready"
            model.scene = "run"
            body(model)
            pump(0.35)
            session.stop()
            pump(0.15)
        }

        let trait = makeTrait()
        try withModel { $0.increaseTraitLevel(trait) }
        try withModel { $0.setTraitRarity(trait, rarity: "Epic") }
        try withModel { $0.removeTrait(trait) }

        let sent = commands(at: commandLog)
        check(sent.count == 3, "expected exactly three live-trait commands, got \(sent)")
        check(sent[0]["command"] as? String == "set_trait_level", "wrong level command")
        check(sent[1]["command"] as? String == "set_trait_rarity", "wrong rarity command")
        check(sent[2]["command"] as? String == "remove_trait", "wrong removal command")
        requireTargetParams(sent[0])
        requireTargetParams(sent[1], expectedRarity: "Epic")
        requireTargetParams(sent[2])

        // Model capability guards and non-run state fail closed before the
        // backend transport boundary.
        try withModel { model in
            let blocked = makeTrait(
                levelCapability: .none,
                rarityCapability: .none,
                removalCapability: .none
            )
            model.increaseTraitLevel(blocked)
            model.setTraitRarity(blocked, rarity: "Epic")
            model.removeTrait(blocked)
            model.scene = "loading"
            model.increaseTraitLevel(trait)
            model.setTraitRarity(trait, rarity: "Heroic")
            model.removeTrait(trait)
        }
        check(commands(at: commandLog).count == 3, "guarded trait operation reached backend transport")

        // Exact acquisition is a separate catalog surface. Individual exact
        // targets do not leak back into Character Rewards, but their source can
        // still synthesize the native choice entry point.
        let exact = makeBoon(
            id: "trait:CritBonusBoon",
            group: "exact",
            nativeChoice: true,
            acquisitionMode: "direct"
        )
        let special = makeBoon(id: "TalentDrop", group: "special", kind: "consumable", sourceID: "Selene")
        try withModel { model in
            model.capabilities["spawnReward"] = true
            model.boons = [exact, special]
            check(model.exactBoonOptions.map(\.id) == [exact.id], "exact catalog projection is wrong")
            check(!model.specialRewardOptions.contains { $0.id == exact.id }, "exact trait leaked into Character Rewards")
            check(model.specialRewardOptions.contains { $0.id == special.id }, "non-boon character reward disappeared")
            check(model.specialRewardOptions.contains { $0.id == "native-choice:Artemis" }, "native character choice entry disappeared")
            model.acquireExactBoon(exact.id)
        }
        let afterExact = commands(at: commandLog)
        check(afterExact.count == 4, "exact acquisition did not emit one command: \(afterExact)")
        check(afterExact[3]["command"] as? String == "spawn_reward", "exact acquisition used the wrong command")
        guard let exactParams = afterExact[3]["params"] as? [String: Any] else { fail("exact acquisition params missing") }
        check(exactParams["reward"] as? String == exact.id, "exact acquisition lost reward identity")

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
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
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
        + [generated, main_path]
    )
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    proc = subprocess.run(
        [str(binary), PYTHON, str(worker_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "hades2_live_trait_model_flow_ok" in proc.stdout, proc.stdout
    print(proc.stdout.strip())
