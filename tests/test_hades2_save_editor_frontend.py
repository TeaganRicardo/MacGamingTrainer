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
                'overview', 'discover', 'resources', 'playerStats', 'progression',
                'quests', 'arcana', 'investigate', 'dialogue',
                'flags', 'relationships', 'weapons', 'advanced',
            ],
            'pendingCount': 0,
            'coverage': [
                {'id': 'resources', 'discoverability': 'supported', 'understanding': 'supported', 'write': 'supported', 'reasonCode': 'verifiedDescriptors'},
                {'id': 'playerHistory', 'discoverability': 'partial', 'understanding': 'partial', 'write': 'partial', 'reasonCode': 'playerHistoryPartial'},
                {'id': 'narrative', 'discoverability': 'supported', 'understanding': 'partial', 'write': 'partial', 'reasonCode': 'narrativePartial'},
                {'id': 'relationships', 'discoverability': 'supported', 'understanding': 'partial', 'write': 'partial', 'reasonCode': 'relationshipsPartial'},
                {'id': 'progression', 'discoverability': 'supported', 'understanding': 'partial', 'write': 'partial', 'reasonCode': 'progressionPartial'},
                {'id': 'equipment', 'discoverability': 'supported', 'understanding': 'partial', 'write': 'partial', 'reasonCode': 'equipmentPartial'},
                {'id': 'unknown', 'discoverability': 'supported', 'understanding': 'readOnly', 'write': 'readOnly', 'reasonCode': 'unknownReadOnly'},
            ],
        }
    elif command == 'save_editor_query':
        domain = req['params']['domain']
        path = req['params']['path']
        if domain == 'discover':
            if req['params']['search'] == 'MysteryCounter':
                items = [{
                    'id': 'advanced:["GameState","UnknownFutureField","MysteryCounter"]:0',
                    'domain': 'advanced',
                    'rawId': 'MysteryCounter',
                    'path': ['GameState', 'UnknownFutureField', 'MysteryCounter'],
                    'name': 'MysteryCounter',
                    'englishName': 'MysteryCounter',
                    'value': 7,
                    'valueType': 'number',
                    'editable': False,
                    'mutationKinds': [],
                    'state': 'unknown',
                    'reasonCode': 'unknownRaw',
                    'reason': 'Unknown save data is preserved and available read-only in Advanced.',
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
                    'state': 'observed',
                    'reasonCode': 'editable',
                    'reason': 'Observed with verified native ownership; supported for editing.',
                }]
        elif domain == 'quests':
            items = [{
                'id': 'quest:QuestHelpDora', 'domain': 'progression',
                'rawId': 'QuestHelpDora',
                'path': ['GameState', 'QuestStatus', 'QuestHelpDora'],
                'name': 'Dora quest', 'englishName': 'Dora quest',
                'value': 'Complete', 'valueType': 'enum',
                'editable': False, 'mutationKinds': [],
            }]
        elif domain == 'arcana':
            items = [{
                'id': 'card:ChanneledCast:Level', 'domain': 'progression',
                'rawId': 'ChanneledCast',
                'path': ['GameState', 'MetaUpgradeState', 'ChanneledCast', 'Level'],
                'name': 'Sorceress', 'englishName': 'Sorceress',
                'entityId': 'arcana:ChanneledCast', 'entityName': 'Sorceress',
                'value': 2, 'valueType': 'integer',
                'editable': True, 'mutationKinds': ['set'],
                'constraints': {'min': 1, 'max': 3, 'integer': True},
            }]
        elif domain == 'investigate':
            lang = req['params']['language']
            items = [{
                'id': 'investigate:NemesisPostTrueEnding01',
                'domain': 'investigate',
                'rawId': 'NemesisPostTrueEnding01',
                'path': ['GameState', 'TextLinesRecord', 'NemesisPostTrueEnding01'],
                'name': 'Nemesis · NemesisPostTrueEnding01',
                'englishName': 'Nemesis · NemesisPostTrueEnding01',
                'value': True,
                'valueType': 'boolean',
                'editable': False,
                'mutationKinds': [],
                'status': 'recorded',
                'sourceStatus': 'available',
                'snippet': '我从未忘记' if lang == 'zh-CN' else 'I still remember',
            }]
        elif domain == 'weapons':
            name = '姊妹双刃' if req['params']['language'] == 'zh-CN' else 'Sister Blades'
            items = [{
                'id': 'aspectSelection:WeaponDagger',
                'domain': 'weapons',
                'rawId': 'WeaponDagger',
                'path': ['GameState', 'LastWeaponUpgradeName', 'WeaponDagger'],
                'name': name + ' · Selected aspect',
                'englishName': 'Sister Blades · Selected aspect',
                'entityId': 'weapon:WeaponDagger',
                'entityName': name,
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
            if path == ['GameState', 'UnknownFutureField']:
                items = [{
                    'id': 'advanced:unknown/MysteryCounter',
                    'domain': 'advanced',
                    'rawId': 'MysteryCounter',
                    'path': ['GameState', 'UnknownFutureField', 'MysteryCounter'],
                    'name': 'MysteryCounter',
                    'englishName': 'MysteryCounter',
                    'value': 7,
                    'valueType': 'number',
                    'editable': False,
                    'mutationKinds': [],
                }]
            elif path == ['GameState', 'Resources']:
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
            'sourceStatus': 'available' if domain == 'investigate' else None,
        }
    elif command == 'save_editor_detail':
        scene = req['params']['entryId'].removeprefix('investigate:')
        result = {
            'scene': scene, 'status': 'recorded', 'sourceStatus': 'available',
            'reason': 'Recorded; owner verified.', 'canStage': True,
            'stageID': 'dialogue:' + scene, 'character': 'Nemesis',
            'sourceResolution': 'resolved', 'futureEligibility': 'unknown',
            'definitions': [{
                'file': 'NPCData_Nemesis.lua', 'line': 42, 'partner': False,
                'requirements': [{
                    'line': 43, 'scope': 'scene',
                    'tree': {'kind': 'and', 'text': 'AND', 'evidence': 'unknown', 'children': [
                        {'kind': 'path', 'text': 'CurrentRun.TextLinesRecord.TrueEndingFinale01',
                         'evidence': 'unknown', 'children': []},
                    ]},
                }],
                'cueIDs': ['Nemesis_0407'],
            }],
            'lines': [{
                'cueId': 'Nemesis_0407', 'speaker': 'Nemesis', 'events': [scene],
                'en': ['I still remember'], 'zhCN': ['我从未忘记'],
            }],
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
import SwiftUI
import AppKit

struct SaveEditorPresentationHarness: View {
    let model: Hades2SaveEditorModel
    @State private var presentation: Hades2SaveEditorPresentation? = nil

    var body: some View {
        Text("host")
            .frame(width: 600, height: 400)
            .hades2SaveEditorSheet($presentation)
            .onAppear {
                presentation = Hades2SaveEditorPresentation(model: model)
            }
    }
}

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\\n", stderr)
    exit(1)
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func pumpUntil(timeout: TimeInterval = 2.0, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline {
        RunLoop.current.run(until: min(deadline, Date().addingTimeInterval(0.02)))
    }
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

        // The workbench groups known linked native owners without creating a
        // parallel edit identity; each original descriptor remains selectable.
        func sample(
            _ id: String, _ domain: String, _ rawID: String, _ name: String,
            group: String? = nil, entityID: String? = nil,
            entityName: String? = nil
        ) -> Hades2SaveEditorEntry {
            Hades2SaveEditorEntry(
                id: id, domain: domain, rawID: rawID, path: [],
                displayName: name, englishName: name, value: AnyHashable(1),
                valueType: "integer", editable: true, mutationKinds: ["set"],
                group: group, entityID: entityID, entityName: entityName,
                choices: [], choiceNames: [:], constraints: nil,
                childCount: nil, pathAmbiguous: false, investigationStatus: nil,
                investigationSnippet: nil, investigationSourceStatus: nil,
                investigationReason: nil, discoveryState: nil,
                discoveryReasonCode: nil, discoveryReason: nil
            )
        }
        let grouped = Hades2SaveEditorEntityGrouping.entities(from: [
            sample("interaction:Nemesis", "relationships", "Nemesis", "Interactions · Nemesis",
                   entityID: "person:Nemesis", entityName: "Nemesis"),
            sample("gift:Nemesis:Nectar", "relationships", "Nemesis / Nectar", "Nemesis · Nectar",
                   entityID: "person:Nemesis", entityName: "Nemesis"),
            sample("investigate:NemesisPostTrueEnding01", "investigate",
                   "NemesisPostTrueEnding01", "Nemesis · NemesisPostTrueEnding01",
                   entityID: "person:Nemesis", entityName: "Nemesis"),
            sample("card:ChanneledCast:Unlocked", "progression", "ChanneledCast",
                   "Sorceress · Unlocked", entityID: "arcana:ChanneledCast", entityName: "Sorceress"),
            sample("card:ChanneledCast:Level", "progression", "ChanneledCast",
                   "Sorceress · Level", entityID: "arcana:ChanneledCast", entityName: "Sorceress"),
            sample("card:ManaOverTime:Unlocked", "progression", "ManaOverTime",
                   "Arcana · ManaOverTime · Unlocked",
                   entityID: "arcana:ManaOverTime", entityName: "Arcana · ManaOverTime"),
            sample("card:ManaOverTime:Level", "progression", "ManaOverTime",
                   "Arcana · ManaOverTime · Level",
                   entityID: "arcana:ManaOverTime", entityName: "Arcana · ManaOverTime"),
            sample("resource:MetaCurrency", "resources", "MetaCurrency", "Ashes"),
        ])
        if grouped.count != 4
            || grouped[0].title != "Nemesis" || grouped[0].entries.count != 3
            || grouped[1].title != "Sorceress" || grouped[1].entries.count != 2
            || grouped[2].title != "Arcana · ManaOverTime" || grouped[2].entries.count != 2
            || grouped[3].title != "Ashes" || grouped[3].entries.count != 1 {
            fail("Save Editor entity grouping lost physical edit descriptors")
        }
        let englishWeapons = Hades2SaveEditorEntityGrouping.entities(from: [
            sample("weapon:WeaponDagger", "weapons", "WeaponDagger", "Sister Blades",
                   entityID: "weapon:WeaponDagger", entityName: "Sister Blades"),
            sample("aspect:DaggerBackstabAspect", "weapons", "DaggerBackstabAspect",
                   "Sister Blades · Aspect of Melinoe · Rank",
                   entityID: "weapon:WeaponDagger", entityName: "Sister Blades"),
            sample("weapon:WeaponTorch", "weapons", "WeaponTorch", "Sister Blades",
                   entityID: "weapon:WeaponTorch", entityName: "Sister Blades"),
        ])
        let chineseWeapons = Hades2SaveEditorEntityGrouping.entities(from: [
            sample("weapon:WeaponDagger", "weapons", "WeaponDagger", "姊妹双刃",
                   entityID: "weapon:WeaponDagger", entityName: "姊妹双刃"),
            sample("aspect:DaggerBackstabAspect", "weapons", "DaggerBackstabAspect",
                   "姊妹双刃 · 墨利诺厄形态 · 等级",
                   entityID: "weapon:WeaponDagger", entityName: "姊妹双刃"),
            sample("weapon:WeaponTorch", "weapons", "WeaponTorch", "姊妹双刃",
                   entityID: "weapon:WeaponTorch", entityName: "姊妹双刃"),
        ])
        let selectedWeaponID = englishWeapons[0].id
        if englishWeapons.count != 2 || chineseWeapons.count != 2
            || englishWeapons[0].entries.count != 2
            || !chineseWeapons.contains(where: { $0.id == selectedWeaponID })
            || englishWeapons[0].title == chineseWeapons[0].title {
            fail("Weapon selection changed identity across language or collided on a label")
        }
        let defaults = InMemoryDefaults()
        defaults.set(
            TrainerPresentationLanguage.en.rawValue,
            forKey: TrainerLocalizationStore.userDefaultsKey
        )
        let localization = TrainerLocalizationStore(defaults: defaults)
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        let root = SaveEditorPresentationHarness(model: model)
            .environmentObject(localization)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 800, height: 600),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.contentView = NSHostingView(rootView: root)
        window.orderFront(nil)
        pumpUntil {
            model.profile == "Profile1" && model.items.count == 1
        }

        if model.profile != "Profile1" {
            fail("Save Editor sheet did not mount the editor model")
        }
        if model.relativePath != "Profile1.sav" { fail("relative path was not decoded") }
        if model.availableDomains != Hades2SaveEditorDomain.allCases {
            fail("Save Editor domain contract was not preserved: \(model.availableDomains)")
        }
        if model.selectedDomain != .discover { fail("Save Editor did not open on unified discovery") }
        if model.total != 1 || model.items.count != 1 { fail("initial discovery page was not loaded") }
        if model.items[0].rawID != "MetaCurrency" || model.items[0].displayName != "Ashes" {
            fail("discovery resource row was not decoded")
        }
        if model.items[0].discoveryState != "observed"
            || model.items[0].discoveryReasonCode != "editable" {
            fail("discovery state/reason was not decoded")
        }
        if model.coverage.count != 7
            || model.coverage.first(where: { $0.id == "playerHistory" })?.write != "partial" {
            fail("Save Editor coverage map was not decoded")
        }

        let sent = commands(at: commandLog)
        if sent.map({ $0["command"] as? String }) != ["save_editor_open", "save_editor_query"] {
            fail("unexpected command sequence: \(sent)")
        }
        guard let params = sent.last?["params"] as? [String: Any] else { fail("missing query params") }
        if params["domain"] as? String != "discover" || params["language"] as? String != "en" {
            fail("query did not use initial unified discovery domain / live language")
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

        model.search = "MysteryCounter"
        model.submitSearch()
        pump(0.20)
        guard let unknown = model.items.first,
              unknown.domain == "advanced",
              unknown.discoveryState == "unknown",
              unknown.discoveryReasonCode == "unknownRaw" else {
            fail("unknown raw discovery row was not decoded")
        }
        model.openDiscoveryEntry(unknown)
        pump(0.20)
        if model.selectedDomain != .advanced
            || model.advancedPath != [.string("GameState"), .string("UnknownFutureField")]
            || model.search != "MysteryCounter" {
            fail("discovery result did not navigate to its Advanced owner")
        }

        model.selectDomain(.discover)
        pump(0.20)
        model.setDiscoveryFilter("absent")
        pump(0.20)
        guard let discoveryFilterCommand = commands(at: commandLog).last(where: {
                  $0["command"] as? String == "save_editor_query"
              }),
              let discoveryFilterParams = discoveryFilterCommand["params"] as? [String: Any],
              discoveryFilterParams["domain"] as? String == "discover",
              discoveryFilterParams["stateFilter"] as? String == "absent" else {
            fail("discovery state filter did not reach Save Workspace")
        }
        model.setDiscoveryFilter("unsupported")
        pump(0.20)
        guard let unsupportedFilterCommand = commands(at: commandLog).last(where: {
                  $0["command"] as? String == "save_editor_query"
              }),
              let unsupportedFilterParams = unsupportedFilterCommand["params"] as? [String: Any],
              unsupportedFilterParams["stateFilter"] as? String == "unsupported" else {
            fail("unsupported discovery filter did not reach Save Workspace")
        }

        model.selectDomain(.investigate)
        pump(0.25)
        if model.items.count != 1 || model.items[0].investigationStatus != "recorded"
            || model.items[0].investigationSnippet != "I still remember" {
            fail("searchable narrative entry was not projected to the player model")
        }
        model.inspect(model.items[0])
        pump(0.25)
        guard let nativeDetail = model.investigationDetail else {
            fail("on-demand narrative detail did not cross Host command boundary")
        }
        if nativeDetail.scene != "NemesisPostTrueEnding01"
            || nativeDetail.definitions.count != 1
            || nativeDetail.definitions.first?.requirements.count != 1
            || nativeDetail.definitions.first?.requirements.first?.tree.children.first?.evidence != "unknown"
            || nativeDetail.lines.first?.chinese != ["我从未忘记"]
            || nativeDetail.futureEligibility != "unknown" {
            fail("native source, bilingual line or future-eligibility evidence was lost")
        }
        model.setInvestigationFilter("notRecorded")
        pump(0.25)
        guard let filtering = commands(at: commandLog).last(where: { $0["command"] as? String == "save_editor_query" }),
              let filteringParams = filtering["params"] as? [String: Any],
              filteringParams["stateFilter"] as? String == "notRecorded" else {
            fail("narrative filter did not reach Save Workspace")
        }
        model.setLanguage(.zhCN)
        pump(0.25)
        if model.items.first?.investigationSnippet != "我从未忘记" {
            fail("narrative evidence did not follow active UI language")
        }

        model.selectDomain(.playerStats)
        pump(0.20)
        if model.items.first?.id != "playerStat:GameplayTime"
            || model.items.first?.valueType != "number"
            || model.items.first?.constraints?.minimum != 0
            || model.items.first?.constraints?.integer != false {
            fail("playerStats descriptor row was not decoded")
        }

        if Hades2SaveWorkbenchSection.growth.domain != .arcana
            || Hades2SaveWorkbenchSection.story.domain != .investigate {
            fail("Workbench navigation resolves the wrong source domain")
        }
        model.selectDomain(.quests)
        pump(0.20)
        if model.items.map(\.id) != ["quest:QuestHelpDora"] {
            fail("Quest navigation included unrelated progression data")
        }
        model.selectDomain(.arcana)
        pump(0.20)
        if model.items.map(\.id) != ["card:ChanneledCast:Level"] {
            fail("Growth navigation included unrelated quest progress")
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
        let chosenWeaponID = Hades2SaveEditorEntityGrouping.entities(from: model.items).first?.id
        let chineseWeaponName = model.items.first?.entityName
        model.setLanguage(.en)
        pump(0.25)
        let localizedWeapon = Hades2SaveEditorEntityGrouping.entities(from: model.items).first
        if chosenWeaponID != "weapon:WeaponDagger"
            || localizedWeapon?.id != chosenWeaponID
            || chineseWeaponName == localizedWeapon?.title
            || localizedWeapon?.title != "Sister Blades" {
            fail("Selection did not survive a real model language reload")
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

        // A scene found by the all-content search must open authored details
        // directly, without bouncing through a separate investigation mode.
        model.selectDomain(.discover)
        pump(0.20)
        let discoveredScene = sample(
            "investigate:NemesisPostTrueEnding01", "investigate",
            "NemesisPostTrueEnding01", "Nemesis"
        )
        model.inspect(discoveredScene)
        pump(0.30)
        if model.investigationDetail?.scene != "NemesisPostTrueEnding01" {
            fail("All-content discovery could not inspect narrative evidence")
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
