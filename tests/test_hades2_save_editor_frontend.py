import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 Save Editor frontend test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = sys.executable
if not SWIFTC:
    raise SystemExit("swiftc required")

worker = r'''
import argparse, json, pathlib, sys
p = argparse.ArgumentParser(); p.add_argument('--game', required=True); args = p.parse_args()
log_path = pathlib.Path(__file__).with_suffix('.commands.jsonl')
resource_value = 123
pending_value = None
for raw in sys.stdin:
    req = json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\\n')
    command = req['command']
    if command == 'save_editor_open':
        result = {
            'profile': 'Profile1',
            'relativePath': 'Profile1.sav',
            'domains': [
                'overview', 'resources', 'playerStats', 'progression', 'dialogue',
                'flags', 'relationships', 'weapons', 'advanced',
            ],
            'pendingCount': 0,
        }
    elif command == 'save_editor_query':
        domain = req['params']['domain']
        path = req['params']['path']
        if domain == 'weapons':
            items = [{
                'id': 'aspectSelection:WeaponDagger',
                'domain': 'weapons',
                'rawId': 'WeaponDagger',
                'path': ['GameState', 'LastWeaponUpgradeName', 'WeaponDagger'],
                'name': 'Sister Blades · Selected aspect',
                'englishName': 'Sister Blades · Selected aspect',
                'value': '',
                'valueType': 'enum',
                'editable': True,
                'mutationKinds': ['setEnum'],
                'group': 'Weapon aspects',
                'choices': ['', 'DaggerBlockAspect'],
                'choiceNames': {
                    '': 'Default aspect',
                    'DaggerBlockAspect': 'Aspect of Artemis',
                },
            }]
        elif domain == 'playerStats':
            items = [{
                'id': 'playerStat:GameplayTime',
                'domain': 'playerStats',
                'rawId': 'GameplayTime',
                'path': ['GameState', 'GameplayTime'],
                'name': 'Gameplay Time (seconds)',
                'englishName': 'Gameplay Time (seconds)',
                'value': 900.5,
                'valueType': 'number',
                'editable': True,
                'mutationKinds': ['set'],
                'constraints': {'min': 0, 'integer': False},
            }]
        elif domain == 'advanced':
            if path == ['GameState', 'Resources']:
                items = [{
                    'id': 'advanced:GameState/Resources/1',
                    'domain': 'advanced',
                    'rawId': '1',
                    'path': ['GameState', 'Resources', 1],
                    'name': '1',
                    'englishName': '1',
                    'value': None,
                    'valueType': 'table',
                    'editable': False,
                    'mutationKinds': [],
                    'childCount': 1,
                }]
            elif path == []:
                items = [{
                    'id': 'advanced:GameState',
                    'domain': 'advanced',
                    'rawId': 'GameState',
                    'path': ['GameState'],
                    'name': 'GameState',
                    'englishName': 'GameState',
                    'value': None,
                    'valueType': 'table',
                    'editable': False,
                    'mutationKinds': [],
                    'childCount': 2,
                }]
            else:
                items = [{
                    'id': 'advanced:GameState/Resources',
                    'domain': 'advanced',
                    'rawId': 'Resources',
                    'path': ['GameState', 'Resources'],
                    'name': 'Resources',
                    'englishName': 'Resources',
                    'value': None,
                    'valueType': 'table',
                    'editable': False,
                    'mutationKinds': [],
                    'childCount': 1,
                }]
        else:
            items = [{
                'id': 'resource:MetaCurrency',
                'domain': 'resources',
                'rawId': 'MetaCurrency',
                'path': ['GameState', 'Resources', 'MetaCurrency'],
                'name': 'Ashes',
                'englishName': 'Ashes',
                'value': resource_value,
                'valueType': 'integer',
                'editable': True,
                'mutationKinds': ['set'],
                'constraints': {'min': 0, 'max': 999999, 'integer': True},
            }, {
                'id': 'resource:GiftPoints',
                'domain': 'resources',
                'rawId': 'GiftPoints',
                'path': ['GameState', 'Resources', 'GiftPoints'],
                'name': 'Zero resource',
                'englishName': 'Zero resource',
                'value': 0,
                'valueType': 'integer',
                'editable': True,
                'mutationKinds': ['set'],
                'constraints': {'min': 0, 'max': 999999, 'integer': True},
            }, {
                'id': 'resource:CardUpgradePoints',
                'domain': 'resources',
                'rawId': 'CardUpgradePoints',
                'path': ['GameState', 'Resources', 'CardUpgradePoints'],
                'name': 'One resource',
                'englishName': 'One resource',
                'value': 1,
                'valueType': 'integer',
                'editable': True,
                'mutationKinds': ['set'],
                'constraints': {'min': 0, 'max': 999999, 'integer': True},
            }]
        result = {
            'profile': 'Profile1',
            'relativePath': 'Profile1.sav',
            'domain': domain,
            'offset': True if req['params']['search'] == 'invalid-offset' else req['params']['offset'],
            'limit': req['params']['limit'],
            'total': len(items),
            'items': items,
        }
    elif command == 'save_editor_stage':
        pending_value = req['params']['value']
        result = {
            'count': 1,
            'changes': [{
                'id': req['params']['entryId'],
                'domain': 'resources',
                'rawId': 'MetaCurrency',
                'operation': req['params']['operation'],
                'before': resource_value,
                'after': pending_value,
            }],
        }
    elif command == 'save_editor_review':
        result = {
            'count': 1,
            'changes': [{
                'id': 'resource:MetaCurrency',
                'domain': 'resources',
                'rawId': 'MetaCurrency',
                'operation': 'set',
                'before': 123,
                'after': 500,
            }],
        }
    elif command == 'save_editor_cancel':
        pending_value = None
        result = {'count': 0, 'changes': []}
    elif command == 'save_editor_apply':
        resource_value = pending_value
        pending_value = None
        result = {'applied': True, 'changeCount': 1, 'previousSnapshotId': 'snapshot-1'}
    else:
        result = {}
    print(json.dumps({
        'type': 'result',
        'id': req['id'],
        'protocolVersion': 6,
        'moduleProtocolVersion': 13,
        'gameID': args.game,
        'ok': True,
        'result': result,
    }), flush=True)
'''

harness = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\\n", stderr)
    exit(1)
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func commands(at url: URL) -> [[String: Any]] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return text.split(separator: "\\n").compactMap {
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

        let process = BackendProcess(executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)
        let session = TrainerBackendSession(client: BackendClient(process: process))
        try session.start(
            descriptor: Hades2GameModule.descriptor,
            backendScriptURL: worker,
            applyPayload: { _ in },
            resetGameState: {},
            log: { _ in },
            onStatusChange: { _ in }
        )

        let model = Hades2SaveEditorModel(session: session)
        model.open(language: .en)
        pump(0.50)

        if model.profile != "Profile1" { fail("profile was not decoded") }
        if model.relativePath != "Profile1.sav" { fail("relative path was not decoded") }
        if model.availableDomains != Hades2SaveEditorDomain.allCases {
            fail("Save Editor domain contract was not preserved: \(model.availableDomains)")
        }
        if model.total != 3 || model.items.count != 3 { fail("initial resources page was not loaded") }
        if model.items[0].rawID != "MetaCurrency" || model.items[0].displayName != "Ashes" {
            fail("resource row was not decoded")
        }
        for (index, expected) in [(1, 0), (2, 1)] {
            guard let value = model.items[index].value else { fail("missing numeric resource") }
            if !(value.base is Int) || value.base is Bool || value != AnyHashable(expected) {
                fail("JSON integer \(expected) was decoded as a boolean")
            }
        }

        let sent = commands(at: commandLog)
        if sent.map({ $0["command"] as? String }) != ["save_editor_open", "save_editor_query"] {
            fail("unexpected command sequence: \(sent)")
        }
        guard let params = sent.last?["params"] as? [String: Any] else { fail("missing query params") }
        if params["domain"] as? String != "resources" || params["language"] as? String != "en" {
            fail("query did not use initial Resources domain / live language")
        }
        if params["offset"] as? Int != 0 || params["limit"] as? Int != 100 {
            fail("query page contract drifted")
        }

        model.stage(entryID: "resource:MetaCurrency", operation: "set", value: 500)
        pump(0.25)
        if model.pendingCount != 1 || model.pendingChanges.count != 1 {
            fail("staged change was not projected into review state")
        }
        let change = model.pendingChanges[0]
        if model.displayName(for: change) != "Ashes" {
            fail("review lost the semantic name for a staged entry")
        }
        if change.entryID != "resource:MetaCurrency"
            || change.rawID != "MetaCurrency"
            || change.operation != "set"
            || change.before != AnyHashable(123)
            || change.after != AnyHashable(500) {
            fail("staged before/after change was decoded incorrectly: \(change)")
        }
        if model.items[0].value != AnyHashable(123) {
            fail("staging mutated the loaded source row before Apply")
        }

        let stagedCommands = commands(at: commandLog)
        if stagedCommands.map({ $0["command"] as? String }) != [
            "save_editor_open", "save_editor_query", "save_editor_stage"
        ] {
            fail("unexpected stage command sequence: \(stagedCommands)")
        }
        guard let stageParams = stagedCommands.last?["params"] as? [String: Any] else {
            fail("missing stage params")
        }
        if stageParams["entryId"] as? String != "resource:MetaCurrency"
            || stageParams["operation"] as? String != "set"
            || stageParams["value"] as? Int != 500 {
            fail("stage params drifted: \(stageParams)")
        }

        model.review()
        pump(0.20)
        if model.pendingCount != 1 || model.pendingChanges.first?.after != AnyHashable(500) {
            fail("explicit review did not restore authoritative pending changes")
        }
        let reviewedCommands = commands(at: commandLog)
        if reviewedCommands.last?["command"] as? String != "save_editor_review" {
            fail("review did not cross the Save Editor Host command seam")
        }

        model.cancel()
        pump(0.20)
        if model.pendingCount != 0 || !model.pendingChanges.isEmpty {
            fail("cancel did not clear the authoritative pending batch")
        }
        if commands(at: commandLog).last?["command"] as? String != "save_editor_cancel" {
            fail("cancel did not cross the Save Editor Host command seam")
        }

        model.stage(entryID: "resource:MetaCurrency", operation: "set", value: 500)
        pump(0.20)
        model.apply()
        pump(0.35)
        if model.pendingCount != 0 || !model.pendingChanges.isEmpty {
            fail("successful Apply did not clear the committed batch")
        }
        if model.items.first?.value != AnyHashable(500) {
            fail("successful Apply did not reload the installed page")
        }
        let appliedCommands = commands(at: commandLog)
        if appliedCommands.suffix(2).compactMap({ $0["command"] as? String }) != [
            "save_editor_apply", "save_editor_query"
        ] {
            fail("Apply did not verify by re-querying the installed workspace: \(appliedCommands)")
        }

        model.search = "ash"
        model.submitSearch()
        pump(0.20)
        guard let searchParams = commands(at: commandLog).last?["params"] as? [String: Any],
              searchParams["search"] as? String == "ash" else {
            fail("search was not delegated to the backend query")
        }

        model.selectDomain(.playerStats)
        pump(0.20)
        if model.items.first?.id != "playerStat:GameplayTime"
            || model.items.first?.valueType != "number"
            || model.items.first?.constraints?.minimum != 0
            || model.items.first?.constraints?.integer != false {
            fail("playerStats descriptor row was not decoded")
        }

        model.selectDomain(.weapons)
        pump(0.20)
        guard let selector = model.items.first else { fail("equipment selector is missing") }
        if selector.id != "aspectSelection:WeaponDagger"
            || selector.valueType != "enum"
            || selector.value != AnyHashable("")
            || selector.choices != ["", "DaggerBlockAspect"]
            || selector.choiceNames[""] != "Default aspect"
            || selector.choiceNames["DaggerBlockAspect"] != "Aspect of Artemis"
            || selector.group != "Weapon aspects" {
            fail("localized equipment selection contract was not decoded")
        }

        model.selectDomain(.advanced)
        pump(0.20)
        if model.advancedPath != [] || model.items.first?.rawID != "GameState"
            || model.items.first?.editable != false || model.items.first?.childCount != 2 {
            fail("Advanced root did not load as a lazy read-only page")
        }
        guard let advancedRoot = model.items.first else { fail("Advanced root row missing") }
        model.enterAdvanced(advancedRoot)
        pump(0.20)
        if model.advancedPath != [.string("GameState")] || model.items.first?.rawID != "Resources" {
            fail("Advanced navigation did not load only the requested child path")
        }
        guard let advancedParams = commands(at: commandLog).last?["params"] as? [String: Any],
              let advancedPath = advancedParams["path"] as? [String],
              advancedPath == ["GameState"] else {
            fail("Advanced query did not carry the lazy path")
        }
        guard let resourcesNode = model.items.first else { fail("Advanced resource table missing") }
        model.enterAdvanced(resourcesNode)
        pump(0.20)
        guard let numericNode = model.items.first else { fail("Advanced numeric key missing") }
        if numericNode.path.last != .integer(1) {
            fail("Advanced numeric key 1 was decoded as a boolean")
        }
        model.enterAdvanced(numericNode)
        pump(0.20)
        let rawCommands = try String(contentsOf: commandLog, encoding: .utf8)
        if !rawCommands.contains(#""path": ["GameState", "Resources", 1]"#) {
            fail("Advanced numeric key 1 was sent to the backend as a boolean")
        }

        model.search = "invalid-offset"
        model.submitSearch()
        pump(0.20)
        if model.failure == nil {
            fail("A boolean query offset was accepted as a numeric offset")
        }

        session.stop()
        pump(0.10)
        print("hades2_save_editor_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-save-editor-frontend-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "save_editor_frontend"
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
        + [ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", generated, main_path]
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
