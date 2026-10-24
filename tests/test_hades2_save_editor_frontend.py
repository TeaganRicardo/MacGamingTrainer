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

view_source = (ROOT / "Sources/Hades2/Views/Hades2SaveEditorView.swift").read_text(encoding="utf-8")
if "coldApplyNotice" in view_source:
    raise SystemExit("Save Editor still exposes the stopped-only apply notice")
for locale in ("hades2.en.json", "hades2.zh-CN.json"):
    localization = (ROOT / "Sources/Hades2/Presentation/Localization" / locale).read_text(encoding="utf-8")
    if '"hades2.saveEditor.applyOutcome.title"' not in localization:
        raise SystemExit(f"missing Save Editor apply outcome localization: {locale}")

worker = r'''
import argparse, json, pathlib, sys, time
p = argparse.ArgumentParser(); p.add_argument('--game', required=True); args = p.parse_args()
log_path = pathlib.Path(__file__).with_suffix('.commands.jsonl')
resource_value = 123
pending_value = None
pending_entry_id = None
pending_operation = None
opened_summary = None
workspace_number = 0
omit_first_target = False
manual_inventory_count = 0
apply_count = 0
detail_counts = {}
refused_recovery_review = False

def staged_result():
    if pending_value is None or pending_entry_id is None or pending_operation is None:
        return {
            'count': 0, 'changes': [],
            'actionCount': 0, 'effectCount': 0, 'physicalChangeCount': 0,
            'actions': [],
        }
    change = {
        'id': pending_entry_id,
        'domain': 'resources',
        'rawId': 'MetaCurrency',
        'operation': pending_operation,
        'before': resource_value,
        'after': pending_value,
    }
    return {
        'count': 1,
        'changes': [change],
        'actionCount': 1,
        'effectCount': 0,
        'physicalChangeCount': 1,
        'actions': [{
            'id': pending_entry_id,
            'entryId': pending_entry_id,
            'entityId': 'entry:' + pending_entry_id,
            'entityName': 'Ashes',
            'domain': 'resources',
            'rawId': 'MetaCurrency',
            'name': 'Ashes',
            'englishName': 'Ashes',
            'operation': pending_operation,
            'before': resource_value,
            'after': pending_value,
            'valueType': 'integer',
            'mutationKinds': ['set'],
            'constraints': {'min': 0, 'max': 999999, 'integer': True},
            'choices': [],
            'choiceNames': {},
            'effects': [],
        }],
    }

for raw in sys.stdin:
    req = json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\\n')
    command = req['command']
    if command == 'save_editor_inventory':
        backup = req['params'].get('snapshotId') is not None
        sources = [
            {'rootId': 'main', 'relativePath': path, 'profile': 'Profile2' if backup else 'Profile1', 'variant': variant}
            for path, variant in ([('Profile2_Temp.sav', 'temp'), ('Profile2_Archive.sav', 'variant')]
                if backup else [('Profile1.sav', 'profile'), ('Profile3.sav', 'profile')])
        ]
        manual_selection = req['params'].get('snapshotId') == 'manual-selection'
        if manual_selection:
            manual_inventory_count += 1
            if manual_inventory_count > 1:
                sources = sources[:1] + [
                    {'rootId': 'main', 'relativePath': 'Profile2_New.sav', 'profile': 'Profile2', 'variant': 'profile'},
                ]
        result = {
            'sources': sources,
            'targets': [
                {'rootId': 'main', 'relativePath': path, 'profile': profile, 'variant': 'profile'}
                for path, profile in [('Profile1.sav', 'Profile1'), ('Profile2.sav', 'Profile2')]
                if not ((omit_first_target or (manual_selection and manual_inventory_count > 1))
                        and path == 'Profile1.sav')
            ],
            'defaultSource': None if manual_selection else {key: sources[0][key] for key in ('rootId', 'relativePath')},
        }
    elif command == 'save_editor_open':
        workspace_number += 1
        snapshot = req['params'].get('snapshotId')
        source = dict(req['params']['source'])
        if source.get('relativePath') == 'Profile3.sav':
            time.sleep(0.25)
        source['kind'] = 'managedBackup' if snapshot else 'currentFile'
        if snapshot:
            source['snapshotId'] = snapshot
            resource_value = 901 if source['relativePath'].endswith('_Temp.sav') else 902
        pending_value = None
        result = {
            'profile': 'Profile2' if snapshot else 'Profile1',
            'workspaceId': 'fixture-workspace' if workspace_number == 1 else 'fixture-workspace-' + str(workspace_number),
            'relativePath': req['params'].get('target', source)['relativePath'],
            'source': source,
            'sourceSHA256': ('a' if source['relativePath'].endswith('_Temp.sav') else 'b') * 64 if snapshot else '0' * 64,
            'target': req['params'].get('target'),
            'domains': [
                'entities', 'overview', 'discover', 'resources', 'playerStats', 'progression',
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
        opened_summary = result
    elif command == 'save_editor_target':
        opened_summary['target'] = req['params']['target']
        opened_summary['relativePath'] = req['params']['target']['relativePath']
        opened_summary['pendingCount'] = int(pending_value is not None)
        result = opened_summary
        if opened_summary['source'].get('snapshotId') not in (None, 'manual-selection'):
            omit_first_target = True
    elif command == 'save_editor_query':
        domain = req['params']['domain']
        path = req['params']['path']
        if domain == 'entities' and req['params'].get('search') == 'detail-race':
            time.sleep(0.25)
        if domain == 'entities':
            scope = req['params'].get('scope', 'all')
            term = req['params']['search'].lower()
            items = []
            if scope in ('all', 'resources') and (not term or 'ash' in term or term == 'invalid-offset'):
                items = [{
                    'id': 'resource:MetaCurrency', 'domain': 'resources',
                    'rawId': 'MetaCurrency',
                    'path': ['GameState', 'Resources', 'MetaCurrency'],
                    'name': 'Ashes', 'englishName': 'Ashes',
                    'value': resource_value, 'valueType': 'integer',
                    'editable': True, 'mutationKinds': ['set'],
                    'constraints': {'min': 0, 'max': 999999, 'integer': True},
                    'state': 'observed', 'reasonCode': 'editable',
                }]
                if not term:
                    items.append({
                        'id': 'resource:GiftPoints', 'domain': 'resources',
                        'rawId': 'GiftPoints',
                        'path': ['GameState', 'Resources', 'GiftPoints'],
                        'name': 'Nectar', 'englishName': 'Nectar',
                        'value': 7, 'valueType': 'integer',
                        'editable': True, 'mutationKinds': ['set'],
                        'constraints': {'min': 0, 'max': 999999, 'integer': True},
                        'state': 'observed', 'reasonCode': 'editable',
                    })
            elif scope in ('all', 'story') and ('nemesis' in term or '复仇' in term):
                items = [{
                    'id': 'interaction:NPC_Nemesis_01', 'domain': 'relationships',
                    'rawId': 'NPC_Nemesis_01',
                    'path': ['GameState', 'NPCInteractions', 'NPC_Nemesis_01'],
                    'name': 'Interactions · Nemesis', 'englishName': 'Interactions · Nemesis',
                    'entityId': 'person:Nemesis', 'entityName': 'Nemesis',
                    'value': 3, 'valueType': 'integer',
                    'editable': True, 'mutationKinds': ['set'],
                    'constraints': {'min': 0, 'max': 9999, 'integer': True},
                }, {
                    'id': 'investigate:NemesisPostTrueEnding01', 'domain': 'investigate',
                    'rawId': 'NemesisPostTrueEnding01',
                    'path': ['GameState', 'TextLinesRecord', 'NemesisPostTrueEnding01'],
                    'name': 'Nemesis · NemesisPostTrueEnding01',
                    'englishName': 'Nemesis · NemesisPostTrueEnding01',
                    'entityId': 'person:Nemesis', 'entityName': 'Nemesis',
                    'value': True, 'valueType': 'boolean',
                    'editable': False, 'mutationKinds': [],
                    'status': 'recorded', 'sourceStatus': 'available',
                    'snippet': 'I still remember',
                }]
            elif scope in ('all', 'growth') and ('sorceress' in term or '女巫' in term):
                items = [{
                    'id': 'card:ChanneledCast:Level', 'domain': 'progression',
                    'rawId': 'ChanneledCast',
                    'path': ['GameState', 'MetaUpgradeState', 'ChanneledCast', 'Level'],
                    'name': 'Sorceress · Level', 'englishName': 'Sorceress · Level',
                    'entityId': 'arcana:ChanneledCast', 'entityName': 'Sorceress',
                    'value': 2, 'valueType': 'integer',
                    'editable': True, 'mutationKinds': ['set'],
                    'constraints': {'min': 1, 'max': 3, 'integer': True},
                }, {
                    'id': 'card:ChanneledCast:Unlocked', 'domain': 'progression',
                    'rawId': 'ChanneledCast',
                    'path': ['GameState', 'MetaUpgradeState', 'ChanneledCast', 'Unlocked'],
                    'name': 'Sorceress · Unlocked', 'englishName': 'Sorceress · Unlocked',
                    'entityId': 'arcana:ChanneledCast', 'entityName': 'Sorceress',
                    'value': True, 'valueType': 'boolean',
                    'editable': True, 'mutationKinds': ['set'],
                }]
            elif scope == 'records':
                items = [{
                    'id': 'playerStat:GameplayTime', 'domain': 'playerStats',
                    'rawId': 'GameplayTime',
                    'path': ['GameState', 'GameplayTime'],
                    'name': 'Gameplay Time (seconds)', 'englishName': 'Gameplay Time (seconds)',
                    'value': 900.5, 'valueType': 'number',
                    'editable': True, 'mutationKinds': ['set'],
                    'constraints': {'min': 0, 'integer': False},
                }]
        elif domain == 'discover':
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
                'name': name + (' · 当前形态' if req['params']['language'] == 'zh-CN' else ' · Selected aspect'),
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
        groups = {}
        if domain == 'entities':
            for row in items:
                key = row.get('entityId') or 'entry:' + row['id']
                if key not in groups:
                    groups[key] = {'id': key, 'name': row.get('entityName') or row['name'],
                                   'items': []}
                groups[key]['items'].append(row)
        result = {
            'profile': 'Profile1',
            'relativePath': 'Profile1.sav',
            'domain': domain,
            'offset': True if req['params']['search'] == 'invalid-offset' else req['params']['offset'],
            'limit': req['params']['limit'],
            'total': 201 if req['params']['search'] == 'pagination-fixture' else (len(groups) if domain == 'entities' else len(items)),
            'items': [] if domain == 'entities' else items,
            'entities': list(groups.values()) if domain == 'entities' else [],
            'sourceStatus': 'available' if domain == 'investigate' else None,
        }
        if domain == 'entities':
            result['scope'] = req['params']['scope']
    elif command == 'save_editor_detail':
        scene = req['params']['entryId'].removeprefix('investigate:')
        detail_counts[scene] = detail_counts.get(scene, 0) + 1
        if scene == 'DetailRace':
            time.sleep(0.20)
            line_text = 'detail reply ' + str(detail_counts[scene])
        else:
            line_text = 'I still remember'
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
                'en': [line_text], 'zhCN': ['我从未忘记'],
            }],
        }
    elif command == 'save_editor_stage':
        if req['params']['value'] == 445:
            print(json.dumps({
                'type': 'result',
                'id': req['id'],
                'protocolVersion': 6,
                'moduleProtocolVersion': 17,
                'gameID': args.game,
                'ok': False,
                'error': {
                    'code': 'invalid_request',
                    'presentation': 'hades2.saveEditor.error.invalidMutation',
                    'arguments': [],
                },
            }), flush=True)
            continue
        pending_entry_id = req['params']['entryId']
        pending_operation = req['params']['operation']
        pending_value = req['params']['value']
        result = staged_result()
    elif command == 'save_editor_unstage':
        if req['params']['entryId'] == pending_entry_id:
            pending_value = None
            pending_entry_id = None
            pending_operation = None
        result = staged_result()
    elif command == 'save_editor_review':
        if pending_value == 600 and not refused_recovery_review:
            refused_recovery_review = True
            print(json.dumps({
                'type': 'result', 'id': req['id'], 'protocolVersion': 6,
                'moduleProtocolVersion': 17, 'gameID': args.game, 'ok': False,
                'error': {'code': 'invalid_request',
                          'presentation': 'hades2.saveEditor.error.invalidResponse', 'arguments': []},
            }), flush=True)
            continue
        result = staged_result()
    elif command == 'save_editor_cancel':
        pending_value = None
        pending_entry_id = None
        pending_operation = None
        result = staged_result()
    elif command == 'save_editor_apply':
        apply_count += 1
        if pending_value == 600:
            print(json.dumps({
                'type': 'result',
                'id': req['id'],
                'protocolVersion': 6,
                'moduleProtocolVersion': 17,
                'gameID': args.game,
                'ok': False,
                'error': {
                    'code': 'rollback_failed',
                    'presentation': 'host.save.error.rollbackFailed',
                    'arguments': ['/tmp/mgt-recovery/save-600'],
                    'recoveryPath': '/tmp/mgt-recovery/save-600',
                },
            }), flush=True)
            continue
        resource_value = pending_value
        pending_value = None
        pending_entry_id = None
        pending_operation = None
        result = {
            'applied': True,
            'changeCount': 1,
            'fileCount': 1,
            'relativePath': 'Profile1.sav',
            'hot': apply_count == 1,
            'runtimeReloaded': False,
            'previousSnapshotId': 'snapshot-hot' if apply_count == 1 else 'snapshot-cold',
        }
    else:
        result = {}
    print(json.dumps({
        'type': 'result',
        'id': req['id'],
        'protocolVersion': 6,
        'moduleProtocolVersion': 17,
        'gameID': args.game,
        'ok': True,
        'result': result,
    }), flush=True)
'''

harness = r'''
import Foundation
import SwiftUI
import AppKit

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

func fields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

final class SaveUnstageAction: NSObject {
    let model: Hades2SaveEditorModel
    let entryID: String
    var presses = 0

    init(model: Hades2SaveEditorModel, entryID: String) {
        self.model = model
        self.entryID = entryID
    }

    @objc(removeClicked:) func clicked(_ sender: Any?) {
        presses += 1
        model.unstage(entryID: entryID)
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
                   group: "Character interactions",
                   entityID: "person:Nemesis", entityName: "Nemesis"),
            sample("gift:Nemesis:Nectar", "relationships", "Nemesis / Nectar", "Nemesis · Nectar",
                   group: "Gift quantities",
                   entityID: "person:Nemesis", entityName: "Nemesis"),
            sample("investigate:NemesisPostTrueEnding01", "investigate",
                   "NemesisPostTrueEnding01", "Nemesis · NemesisPostTrueEnding01",
                   group: "Dialogue",
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
        let sections = Hades2SaveEditorEntityGrouping.sections(from: grouped)
        if sections.map(\.id) != ["characters", "resources", "arcana"]
            || sections[0].entities.map(\.id) != ["person:Nemesis"]
            || Hades2SaveEditorEntityGrouping.fields(in: grouped[0]).map(\.title)
                != ["Character interactions", "Gift quantities", "Dialogue"] {
            fail("Save Editor headings mixed categories or physical field owners")
        }
        var hub = sample("interaction:NPC_Artemis_01", "relationships", "NPC_Artemis_01",
                         "Conversations · Artemis", entityID: "person:Artemis", entityName: "Artemis")
        hub.hostID = "NPC_Artemis_01"; hub.hostName = "Crossroads"
        var field = sample("interaction:NPC_Artemis_Field_01", "relationships", "NPC_Artemis_Field_01",
                           "Conversations · Artemis", entityID: "person:Artemis", entityName: "Artemis")
        field.hostID = "NPC_Artemis_Field_01"; field.hostName = "Boon encounter"
        let hostGroups = Hades2SaveEditorEntityGrouping.fields(in:
            Hades2SaveEditorEntityGrouping.entities(from: [hub, field])[0])
        if hostGroups.count != 2 || hostGroups[0].id == hostGroups[1].id
            || hostGroups.map(\.title) != ["Crossroads", "Boon encounter"] {
            fail("native hosts with identical labels have no distinct context headings")
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
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        enableNativeAccessibility()
        let toolWindows = TrainerToolWindowStore()
        let window = toolWindows.open(id: "save-editor", title: "Save Editor", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) {
                Hades2SaveEditorView(model: model)
            }
        }
        pumpUntil {
            model.profile == "Profile1" && model.items.count == 1
        }

        if model.profile != "Profile1" {
            fail("Save Editor independent window did not mount the editor model")
        }
        if model.relativePath != "Profile1.sav" { fail("relative path was not decoded") }
        if model.availableDomains != Hades2SaveEditorDomain.allCases {
            fail("Save Editor domain contract was not preserved: \(model.availableDomains)")
        }
        if model.selectedDomain != .entities { fail("Save Editor did not open on entity results") }
        if model.total != 2 || model.items.count != 2 || model.entityResults.count != 2 { fail("initial entity page was not loaded") }
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

        // Primary Save editing must be possible directly from the first result.
        // No category expansion, entity selection or inspector activation is needed.
        func inlineField(_ value: String) -> NSTextField? {
            NSApp.windows.compactMap(\.contentView).flatMap(fields).first { field in
                field.isEditable && field.isEnabled && field.stringValue == value
            }
        }
        func inlineValueField() -> NSTextField? { inlineField("123") }
        pumpUntil(timeout: 2.0) { inlineValueField() != nil }
        if inlineValueField() == nil {
            fail("The initial Save result requires an extra entity selection before editing")
        }
        if inlineValueField()?.accessibilityLabel() != "Ashes" {
            fail("The inline Save input is named only by its generic value placeholder")
        }

        let sent = commands(at: commandLog)
        if sent.map({ $0["command"] as? String }) != ["save_editor_inventory", "save_editor_open", "save_editor_query"] {
            fail("unexpected command sequence: \(sent)")
        }
        guard let params = sent.last?["params"] as? [String: Any] else { fail("missing query params") }
        if params["workspaceId"] as? String != "fixture-workspace" {
            fail("query was not bound to the opened document")
        }
        if params["domain"] as? String != "entities" || params["scope"] as? String != "all" || params["language"] as? String != "en" {
            fail("query did not use initial unified discovery domain / live language")
        }
        if params["offset"] as? Int != 0 || params["limit"] as? Int != 100 {
            fail("query page contract drifted")
        }

        var draft = "123"
        let entry = model.items[0]
        let fieldHost = NSHostingView(rootView: TrainerTextField(
            title: "Value", text: Binding(get: { draft }, set: { draft = $0 }), onCommit: { edit in
                model.completeTextEdit(entry, text: edit.text, changed: edit.changed)
            }
        ))
        let editorWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 240, height: 40),
                                    styleMask: [.titled], backing: .buffered, defer: false)
        editorWindow.contentView = fieldHost; fieldHost.layoutSubtreeIfNeeded(); pump(0.1)
        guard let field = fields(fieldHost).first(where: { $0.isEditable }),
              editorWindow.makeFirstResponder(field), let fieldEditor = field.currentEditor() as? NSTextView else {
            fail("could not focus the shared staged Save Editor field")
        }
        fieldEditor.selectAll(nil); fieldEditor.insertText("3.5", replacementRange: fieldEditor.selectedRange())
        editorWindow.makeFirstResponder(nil); pump(0.1)
        if model.pendingCount != 0 || model.editFailures[entry.id]?.key != "hades2.saveEditor.invalidDraft" || draft != "3.5" {
            fail("invalid Save draft was truncated/staged or lost its correction feedback")
        }
        guard editorWindow.makeFirstResponder(field), let fieldEditor = field.currentEditor() as? NSTextView else {
            fail("could not refocus the shared staged Save Editor field")
        }
        fieldEditor.selectAll(nil); fieldEditor.insertText("500", replacementRange: fieldEditor.selectedRange())
        pump(0.4)
        if commands(at: commandLog).contains(where: { $0["command"] as? String == "save_editor_stage" }) {
            fail("Save Editor typing staged an unfinished draft")
        }
        editorWindow.makeFirstResponder(nil)
        pumpUntil { model.pendingCount == 1 && !model.busy }
        editorWindow.close()
        if model.pendingCount != 1 || model.pendingActions.count != 1 {
            fail("staged action was not projected into review state")
        }
        if model.editFailures[entry.id] != nil {
            fail("Correcting a Save field left its earlier rejection attached")
        }
        let action = model.pendingActions[0]
        if action.name != "Ashes" {
            fail("review lost the semantic name for a staged action")
        }
        if action.entryID != "resource:MetaCurrency"
            || action.rawID != "MetaCurrency"
            || action.operation != "set"
            || action.before != AnyHashable(123)
            || action.after != AnyHashable(500) {
            fail("staged before/after action was decoded incorrectly: \(action)")
        }
        if model.items[0].value != AnyHashable(123) {
            fail("staging mutated the loaded source row before Apply")
        }

        let stagedCommands = commands(at: commandLog)
        if stagedCommands.map({ $0["command"] as? String }) != [
            "save_editor_inventory", "save_editor_open", "save_editor_query", "save_editor_stage"
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
        if model.pendingCount != 1 || model.pendingActions.first?.after != AnyHashable(500) {
            fail("explicit review did not restore authoritative pending action")
        }
        let reviewedCommands = commands(at: commandLog)
        if reviewedCommands.last?["command"] as? String != "save_editor_review" {
            fail("review did not cross the Save Editor Host command seam")
        }

        model.cancel()
        pump(0.20)
        if model.pendingCount != 0 || !model.pendingActions.isEmpty {
            fail("cancel did not clear the authoritative pending batch")
        }
        if commands(at: commandLog).last?["command"] as? String != "save_editor_cancel" {
            fail("cancel did not cross the Save Editor Host command seam")
        }

        // Keep an unrelated invalid draft in a second actual Save row. Removing
        // the last staged action below must preserve this correction in place.
        guard let unrelatedDraftField = inlineField("7"),
              let unrelatedDraftWindow = unrelatedDraftField.window,
              unrelatedDraftWindow.makeFirstResponder(unrelatedDraftField),
              let unrelatedDraftEditor = unrelatedDraftField.currentEditor() as? NSTextView else {
            fail("Could not edit the unrelated Save field")
        }
        unrelatedDraftEditor.selectAll(nil)
        unrelatedDraftEditor.insertText("3.5", replacementRange: unrelatedDraftEditor.selectedRange())
        unrelatedDraftWindow.makeFirstResponder(nil)
        pump(0.15)
        if model.pendingCount != 0
            || model.editFailures["resource:GiftPoints"]?.key != "hades2.saveEditor.invalidDraft"
            || unrelatedDraftField.stringValue != "3.5" {
            fail("Unrelated invalid draft was not retained before per-item removal")
        }
        let nectarCorrection = "Nectar: " + Hades2GameModule.resolveText(
            key: "hades2.saveEditor.invalidDraft", localization: localization
        )
        if namedNativeControl(window.contentView!, role: "AXStaticText", name: nectarCorrection) == nil {
            let observed = nativeAccessibilityControls(window.contentView!).filter {
                $0.text?.contains("Nectar") == true || $0.text?.contains("valid") == true
            }.map { "\($0.role ?? "nil"): \($0.text ?? "nil")" }
            fail("The invalid Save draft has no correction feedback at its owning control: \(observed)")
        }

        // Edit the actual initially rendered Save result, not a detached
        // field harness. Blur alone must stage the change; no entity selection
        // or additional per-field button is involved.
        guard let inPlace = inlineValueField(), let sheet = inPlace.window,
              sheet.makeFirstResponder(inPlace),
              let editor = inPlace.currentEditor() as? NSTextView else {
            fail("Could not directly edit the first Save result in its sheet")
        }
        editor.selectAll(nil)
        editor.insertText("430", replacementRange: editor.selectedRange())
        sheet.makeFirstResponder(nil)
        pumpUntil { model.pendingActions.first?.after == AnyHashable(430) && !model.busy }
        if model.pendingActions.first?.after != AnyHashable(430) ||
            commands(at: commandLog).last?["command"] as? String != "save_editor_stage" {
            fail("Direct Save result editing did not stage on blur")
        }
        if namedNativeControl(window.contentView!, role: "AXStaticText", name: nectarCorrection) == nil {
            fail("An unrelated successful Save edit cleared the retained invalid draft's correction feedback")
        }

        // A backend-refused but syntactically valid edit must not strand the
        // real inline field on an unacknowledged local value.
        guard sheet.makeFirstResponder(inPlace),
              let rejectedEditor = inPlace.currentEditor() as? NSTextView else {
            fail("Could not refocus inline Save field for stage-refusal coverage")
        }
        rejectedEditor.selectAll(nil)
        rejectedEditor.insertText("445", replacementRange: rejectedEditor.selectedRange())
        sheet.makeFirstResponder(nil)
        pumpUntil {
            !model.busy
                && model.editFailures[entry.id]?.key == "hades2.saveEditor.error.invalidMutation"
                && inPlace.stringValue == "430"
        }
        if model.pendingActions.first?.after != AnyHashable(430)
            || inPlace.stringValue != "430" {
            fail("Rejected stage left a misleading inline value or changed pending intent")
        }

        // Exercise the same basket action data through real native controls.
        // TrainerTextField owns edit completion; NSButton owns the explicit
        // per-action removal click, and both cross the Host command seam.
        guard let basketAction = model.pendingActions.first else {
            fail("Changes basket did not expose the staged action")
        }
        var basketDraft = String(describing: basketAction.after?.base ?? "")
        let basketHost = NSHostingView(rootView: TrainerTextField(
            title: "Value",
            text: Binding(
                get: { basketDraft },
                set: { basketDraft = $0 }
            ),
            onCommit: { edit in
                model.completeTextEdit(
                    basketAction.editorEntry,
                    text: edit.text,
                    changed: edit.changed
                )
            }
        ))
        let basketWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 260, height: 80),
            styleMask: [.titled],
            backing: .buffered,
            defer: false
        )
        basketWindow.contentView = basketHost
        basketWindow.orderFront(nil)
        pumpUntil { fields(basketHost).first?.stringValue == "430" }
        guard let basketField = fields(basketHost).first,
              basketWindow.makeFirstResponder(basketField),
              let basketEditor = basketField.currentEditor() as? NSTextView else {
            fail("Staged action was not editable through the native basket field")
        }
        basketEditor.selectAll(nil)
        basketEditor.insertText("440", replacementRange: basketEditor.selectedRange())
        basketWindow.makeFirstResponder(nil)
        pumpUntil {
            model.pendingActions.first?.after == AnyHashable(440) && !model.busy
        }
        basketWindow.close()
        if model.pendingActions.first?.after != AnyHashable(440)
            || commands(at: commandLog).last?["command"] as? String != "save_editor_stage" {
            fail("Native basket field did not revise the authoritative staged action")
        }

        let removeTarget = SaveUnstageAction(
            model: model,
            entryID: "resource:MetaCurrency"
        )
        let removeButton = NSButton(
            title: "Remove change",
            target: removeTarget,
            action: NSSelectorFromString("removeClicked:")
        )
        removeButton.performClick(nil)
        pumpUntil { model.pendingCount == 0 && !model.busy }
        if removeTarget.presses != 1
            || !model.pendingActions.isEmpty
            || commands(at: commandLog).last?["command"] as? String != "save_editor_unstage" {
            fail("Native per-action remove control did not unstage exactly one action")
        }
        pump(0.15)
        if inlineField("3.5") == nil {
            fail("Removing the last staged action discarded an unrelated invalid field draft")
        }
        if namedNativeControl(window.contentView!, role: "AXStaticText", name: nectarCorrection) == nil {
            fail("Removing an unrelated action cleared the invalid draft's correction feedback")
        }

        model.stage(entryID: "resource:MetaCurrency", operation: "set", value: 500)
        pumpUntil { !model.busy && model.pendingCount == 1 }
        guard let sameActionDraft = fields(window.contentView!).first(where: {
            $0.isEditable && $0.accessibilityLabel() == "Ashes"
        }), window.makeFirstResponder(sameActionDraft),
              let sameActionEditor = sameActionDraft.currentEditor() as? NSTextView else {
            fail("Could not retain a later invalid draft on an acknowledged action's field")
        }
        sameActionEditor.selectAll(nil)
        sameActionEditor.insertText("3.5", replacementRange: sameActionEditor.selectedRange())
        window.makeFirstResponder(nil); pump(0.10)
        model.apply()
        pump(0.35)
        if model.pendingCount != 0 || !model.pendingActions.isEmpty {
            fail("successful Apply did not clear the committed batch")
        }
        if model.items.first?.value != AnyHashable(500) {
            fail("successful Apply did not reload the installed page")
        }
        if inlineField("3.5") == nil
            || namedNativeControl(window.contentView!, role: "AXStaticText", name: nectarCorrection) == nil {
            fail("Applying unrelated acknowledged changes discarded an invalid Save draft or its correction feedback")
        }
        if model.editFailures["resource:MetaCurrency"]?.key != "hades2.saveEditor.invalidDraft"
            || !fields(window.contentView!).contains(where: {
                $0.isEditable && $0.accessibilityLabel() == "Ashes" && $0.stringValue == "3.5"
            }) {
            fail("Applying an acknowledged action erased a later invalid draft on the same field")
        }
        guard let hotReceipt = model.lastApplyReceipt else {
            fail("hot Apply did not expose its backend receipt")
        }
        if hotReceipt.source != "main/Profile1.sav"
            || hotReceipt.target != "main/Profile1.sav"
            || !hotReceipt.hot
            || hotReceipt.runtimeReloaded
            || hotReceipt.previousSnapshotID != "snapshot-hot"
            || hotReceipt.fileCount != 1 {
            fail("hot Apply receipt was not decoded faithfully: \(hotReceipt)")
        }
        let appliedCommands = commands(at: commandLog)
        if appliedCommands.suffix(2).compactMap({ $0["command"] as? String }) != [
            "save_editor_apply", "save_editor_query"
        ] {
            fail("Apply did not verify by re-querying the installed workspace: \(appliedCommands)")
        }

        model.stage(entryID: "resource:MetaCurrency", operation: "set", value: 550)
        pumpUntil { !model.busy && model.pendingCount == 1 }
        model.apply()
        pump(0.35)
        guard let coldReceipt = model.lastApplyReceipt else {
            fail("cold Apply did not expose its backend receipt")
        }
        if coldReceipt.hot
            || coldReceipt.runtimeReloaded
            || coldReceipt.previousSnapshotID != "snapshot-cold"
            || coldReceipt.source != "main/Profile1.sav"
            || coldReceipt.target != "main/Profile1.sav" {
            fail("cold Apply receipt was not decoded faithfully: \(coldReceipt)")
        }
        if model.items.first?.value != AnyHashable(550) {
            fail("cold Apply did not reload the installed page")
        }

        model.stage(entryID: "resource:MetaCurrency", operation: "set", value: 600)
        pumpUntil { !model.busy && model.pendingCount == 1 }
        model.apply()
        pump(0.20)
        if model.pendingCount != 1
            || model.operationFailures[.saveEditorApply]?.key != "host.save.error.rollbackFailed"
            || model.operationFailures[.saveEditorApply]?.arguments != ["/tmp/mgt-recovery/save-600"] {
            fail("Save Editor lost rollback failure/recovery context")
        }
        model.review()
        pump(0.20)
        if model.operationFailures[.saveEditorReview]?.key != "hades2.saveEditor.error.invalidResponse"
            || model.operationFailures[.saveEditorApply]?.arguments != ["/tmp/mgt-recovery/save-600"] {
            fail("A second failed operation replaced Apply recovery evidence")
        }
        model.review()
        pump(0.20)
        if model.operationFailures[.saveEditorReview] != nil
            || model.operationFailures[.saveEditorApply]?.key != "host.save.error.rollbackFailed"
            || model.operationFailures[.saveEditorApply]?.arguments != ["/tmp/mgt-recovery/save-600"] {
            fail("An unrelated successful Changes refresh cleared Apply recovery evidence")
        }
        model.selectTarget("main/Profile2.sav")
        pumpUntil { !model.busy && model.selectedTargetID == "main/Profile2.sav" }
        guard let recovery = model.operationFailures[.saveEditorApply],
              namedNativeControl(window.contentView!, role: "AXStaticText", name: localization.string(recovery)) != nil else {
            fail("A successful target change hid the native Apply recovery notice")
        }
        model.selectTarget("main/Profile1.sav")
        pumpUntil { !model.busy && model.selectedTargetID == "main/Profile1.sav" }
        model.cancel()
        pumpUntil { model.pendingCount == 0 && !model.busy }
        if !model.editFailures.isEmpty || inlineField("3.5") != nil {
            fail("Explicitly discarding Save changes retained an abandoned draft or its correction feedback")
        }
        if model.operationFailures[.saveEditorApply]?.arguments != ["/tmp/mgt-recovery/save-600"] {
            fail("Discarding requested edits erased a failed disk transaction's recovery path")
        }

        model.selectScope("all")
        pump(0.20)
        model.search = "Nemesis"
        model.submitSearch()
        pumpUntil { model.entityResults.first?.entries.count == 2 && !model.querying }
        guard let nemesis = model.entityResults.first,
              nemesis.id == "person:Nemesis",
              nemesis.entries.count == 2,
              nemesis.entries.contains(where: { $0.id == "interaction:NPC_Nemesis_01" }),
              nemesis.entries.contains(where: { $0.id == "investigate:NemesisPostTrueEnding01" }) else {
            fail("Entity lookup split Nemesis interaction from native dialogue context")
        }
        model.selectScope("story")
        pumpUntil { model.selectedScope == "story" && !model.querying }
        if model.search != "Nemesis" || model.entityResults.first?.id != "person:Nemesis" {
            fail("Scope switch lost the typed search or semantic entity identity")
        }
        model.inspect(nemesis.entries[1])
        pumpUntil { model.investigationDetail != nil }
        if model.investigationDetail?.scene != "NemesisPostTrueEnding01" {
            fail("Entity-native authored details did not open on demand")
        }
        model.search = "Sorceress"
        model.selectScope("growth")
        pumpUntil { model.entityResults.first?.id == "arcana:ChanneledCast" && !model.querying }
        if model.entityResults.first?.entries.count != 2
            || model.entityResults.first?.entries.filter({ $0.editable }).count != 2 {
            fail("Arcana was not a complete, immediately editable multi-field entity")
        }
        pump(0.10)
        guard let content = window.contentView,
              let unlocked = model.items.first(where: { $0.valueType == "boolean" }),
              namedNativeControl(content, role: "AXCheckBox", name: unlocked.displayName) != nil else {
            fail("The actual inline Save switch has no owning field name")
        }
        model.selectScope("all")
        pumpUntil { !model.querying }
        if model.search != "Sorceress" {
            fail("Global scope cleared search")
        }

        model.search = "ash"
        model.submitSearch()
        pump(0.20)
        guard let searchParams = commands(at: commandLog).last?["params"] as? [String: Any],
              searchParams["search"] as? String == "ash" else {
            fail("search was not delegated to the backend query")
        }

        // Raw/unknown data is an explicit read-only diagnostic fallback.
        model.selectDomain(.discover)
        pump(0.20)
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

        if Hades2SaveWorkbenchSection.growth.rawValue != "growth"
            || Hades2SaveWorkbenchSection.story.rawValue != "story" {
            fail("Workbench navigation resolves the wrong entity browse scope")
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
        pump(0.10)
        if namedNativeControl(content, role: "AXPopUpButton", name: selector.displayName) == nil {
            fail("The actual Save enum control is named only by its generic value label")
        }
        model.setLanguage(.en)
        pump(0.25)
        let localizedWeapon = Hades2SaveEditorEntityGrouping.entities(from: model.items).first
        if chosenWeaponID != "weapon:WeaponDagger"
            || localizedWeapon?.id != chosenWeaponID
            || chineseWeaponName == localizedWeapon?.title
            || localizedWeapon?.title != "Sister Blades" {
            fail("Selection did not survive a real model language reload")
        }
        pump(0.10)
        if namedNativeControl(content, role: "AXPopUpButton", name: model.items[0].displayName) == nil {
            fail("The Save enum control kept its old native name after a language reload")
        }

        model.search = "pagination-fixture"
        model.submitSearch()
        pumpUntil { !model.querying && model.total == 201 }
        for language in [TrainerPresentationLanguage.en, .zhCN] {
            localization.language = language
            pumpUntil { !model.querying && model.total == 201 }
            pump(0.10)
            let previousName = Hades2GameModule.resolveText(key: "hades2.saveEditor.previousPage", localization: localization)
            let nextName = Hades2GameModule.resolveText(key: "hades2.saveEditor.nextPage", localization: localization)
            guard let next = namedNativeControl(content, role: "AXButton", name: nextName),
                  let previous = namedNativeControl(content, role: "AXButton", name: previousName),
                  next.enabled, !previous.enabled,
                  next.help == nextName,
                  previous.help == previousName,
                  next.press() else {
                fail("Save page actions have missing names/help or incorrect initial availability")
            }
            pumpUntil { !model.querying && model.offset == 100 }
            guard let currentPrevious = namedNativeControl(content, role: "AXButton", name: previousName),
                  currentPrevious.enabled,
                  currentPrevious.press() else {
                fail("The named previous-page action did not become available")
            }
            pumpUntil { !model.querying && model.offset == 0 }
        }
        localization.language = .en
        model.search = "ash"
        model.submitSearch()
        pumpUntil { !model.querying }

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
        if model.queryFailure == nil {
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

        // Non-occupying detail reads must remain owned by the exact request,
        // language and workspace that started them.
        model.selectScope("all")
        model.setLanguage(.en)
        pumpUntil(timeout: 1.0) { !model.querying && !model.busy }
        let raceDetail = sample(
            "investigate:DetailRace", "investigate", "DetailRace", "Detail race"
        )

        model.inspect(raceDetail)
        model.inspect(raceDetail)
        pump(0.24)
        if model.investigationDetail != nil {
            fail("Superseded detail reply was accepted before the newer request completed")
        }
        pumpUntil(timeout: 1.0) {
            model.investigationDetail?.lines.first?.english == ["detail reply 2"]
        }
        if model.investigationDetail?.lines.first?.english != ["detail reply 2"] {
            fail("Newest detail request did not win after an overlapping request")
        }

        model.search = "detail-race"
        model.inspect(raceDetail)
        model.setLanguage(.zhCN)
        pump(0.24)
        if model.investigationDetail != nil {
            fail("Old-language detail reply was accepted after language changed")
        }
        pumpUntil(timeout: 1.2) { !model.querying }
        model.setLanguage(.en)
        model.search = ""
        model.submitSearch()
        pumpUntil(timeout: 1.0) { !model.querying }

        model.inspect(raceDetail)
        model.selectedSourceID = "main/Profile3.sav"
        pump(0.24)
        if model.investigationDetail != nil {
            fail("Old-workspace detail reply was accepted during source transition")
        }
        pumpUntil(timeout: 1.5) {
            model.sourceRelativePath == "Profile3.sav" && !model.busy && !model.querying
        }
        model.selectedSourceID = "main/Profile1.sav"
        pumpUntil(timeout: 1.5) {
            model.sourceRelativePath == "Profile1.sav" && !model.busy && !model.querying
        }

        // The visible source picker loads a new source in one selection when
        // no changes are staged. The pinned target remains independent.
        pumpUntil { !model.busy }
        let oldWorkspace = model.workspaceID
        model.selectedSourceID = "main/Profile3.sav"
        pumpUntil(timeout: 2.0) {
            model.workspaceID != oldWorkspace && model.sourceRelativePath == "Profile3.sav"
                && !model.busy && !model.querying
        }
        guard model.workspaceID != oldWorkspace,
              model.sourceRelativePath == "Profile3.sav",
              model.selectedTargetID == "main/Profile1.sav",
              let sourceRead = commands(at: commandLog).last(where: {
                  $0["command"] as? String == "save_editor_open"
              }),
              let readParams = sourceRead["params"] as? [String: Any],
              let readSource = readParams["source"] as? [String: String],
              readSource["relativePath"] == "Profile3.sav" else {
            fail("A source selection did not load the pinned document in one action")
        }

        // An inventory can offer selectable files without a default profile.
        // This must open through the mounted workbench's first source change,
        // while the ordinary default above still opens exactly once.
        let manualModel = Hades2SaveEditorModel(session: session, snapshotID: "manual-selection")
        let beforeManual = commands(at: commandLog).count
        let manualWindow = toolWindows.open(id: "manual-editor", title: "Manual", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { !manualModel.busy }, onClose: manualModel.close) {
                Hades2SaveEditorView(model: manualModel)
            }
        }
        pumpUntil {
            !manualModel.busy && manualModel.sourceFiles.count == 2
        }
        if manualModel.workspaceID != nil || manualModel.selectedSourceID != ""
            || manualModel.sourceFiles.count != 2 {
            fail("No-default inventory implicitly opened or selected a source")
        }
        let initialManualCommands = Array(commands(at: commandLog).dropFirst(beforeManual))
        if initialManualCommands.compactMap({ $0["command"] as? String }) != ["save_editor_inventory"] {
            fail("No-default inventory issued an unexpected open: \(initialManualCommands)")
        }

        manualModel.selectedSourceID = "main/Profile2_Archive.sav"
        pumpUntil {
            manualModel.workspaceID != nil && !manualModel.busy && manualModel.items.count == 1
        }
        guard let manualWorkspace = manualModel.workspaceID,
              manualModel.sourceRelativePath == "Profile2_Archive.sav",
              commands(at: commandLog).dropFirst(beforeManual).filter({
                  $0["command"] as? String == "save_editor_open"
              }).count == 1 else {
            fail("First visible source selection did not open the selected file exactly once")
        }

        // Inventory refresh must leave the loaded bytes and selected write
        // destination pinned, even when neither is returned by the new list.
        manualModel.selectTarget("main/Profile1.sav")
        pumpUntil { !manualModel.busy && manualModel.hasWriteTarget }
        let beforeInventoryRefresh = commands(at: commandLog).count
        manualModel.refreshFiles()
        pumpUntil {
            !manualModel.busy && commands(at: commandLog).count > beforeInventoryRefresh
        }
        let refreshCommands = Array(commands(at: commandLog).dropFirst(beforeInventoryRefresh))
        if refreshCommands.compactMap({ $0["command"] as? String }) != ["save_editor_inventory"]
            || manualModel.workspaceID != manualWorkspace
            || manualModel.sourceRelativePath != "Profile2_Archive.sav"
            || manualModel.selectedSourceID != "main/Profile2_Archive.sav"
            || manualModel.selectedTargetID != "main/Profile1.sav"
            || manualModel.sourceFiles.contains(where: { $0.id == manualModel.selectedSourceID })
            || !manualModel.sourceFiles.contains(where: { $0.id == "main/Profile2_New.sav" })
            || manualModel.writeTargets.contains(where: { $0.id == manualModel.selectedTargetID }) {
            fail("Inventory refresh re-opened the document or lost missing pinned identities")
        }
        manualWindow.close()
        pumpUntil {
            commands(at: commandLog).contains { row in
                row["command"] as? String == "save_editor_close"
                    && (row["params"] as? [String: Any])?["workspaceId"] as? String == manualWorkspace
            }
        }

        // A managed backup uses the same session and semantic model. Source
        // selection remains an explicit proposal in an unmounted model; targets
        // are independent.
        let backupModel = Hades2SaveEditorModel(session: session, snapshotID: "verified-backup")
        let beforeBackup = commands(at: commandLog).count
        backupModel.open(language: .en)
        pumpUntil { !backupModel.busy && backupModel.items.count == 1 }
        guard let backupWorkspace = backupModel.workspaceID else { fail("backup workbench did not open") }
        if backupModel.sourceRootID != "main" || backupModel.sourceRelativePath != "Profile2_Temp.sav"
            || backupModel.sourceSHA256 != String(repeating: "a", count: 64)
            || backupModel.items.first?.value != AnyHashable(901)
            || backupModel.hasWriteTarget {
            fail("backup source identity, supported Temp bytes or independent target was lost")
        }
        let backupCommands = Array(commands(at: commandLog).dropFirst(beforeBackup))
        if backupCommands.compactMap({ $0["command"] as? String }) != [
            "save_editor_inventory", "save_editor_open", "save_editor_query"
        ] || (backupCommands[1]["params"] as? [String: Any])?["snapshotId"] as? String != "verified-backup" {
            fail("backup entry bypassed the shared backend session/workbench")
        }
        backupModel.stage(entryID: "resource:MetaCurrency", operation: "set", value: 800)
        pumpUntil { !backupModel.busy && backupModel.pendingCount == 1 }
        let beforeNoTarget = commands(at: commandLog).count
        backupModel.apply()
        pump(0.05)
        if commands(at: commandLog).count != beforeNoTarget { fail("Apply ran without a selected target") }
        backupModel.selectTarget("main/Profile1.sav")
        pumpUntil { !backupModel.busy && backupModel.hasWriteTarget }
        if backupModel.workspaceID != backupWorkspace || backupModel.selectedTargetID != "main/Profile1.sav"
            || backupModel.sourceRelativePath != "Profile2_Temp.sav" || backupModel.pendingCount != 1
            || backupModel.items.first?.value != AnyHashable(901) {
            fail("target selection replaced the source document or cleared staging")
        }
        backupModel.refreshFiles()
        pumpUntil { !backupModel.busy }
        if backupModel.writeTargets.contains(where: { $0.id == "main/Profile1.sav" })
            || backupModel.selectedTargetID != "main/Profile1.sav"
            || backupModel.workspaceID != backupWorkspace || backupModel.pendingCount != 1 {
            fail("inventory refresh changed the captured source/target owner")
        }
        let beforeSourceProposal = commands(at: commandLog).count
        backupModel.selectedSourceID = "main/Profile2_Archive.sav"
        pump(0.05)
        if commands(at: commandLog).count != beforeSourceProposal
            || backupModel.sourceRelativePath != "Profile2_Temp.sav" || backupModel.pendingCount != 1 {
            fail("choosing a source silently read/rebased the loaded document")
        }
        backupModel.openSelection()
        pumpUntil { !backupModel.busy && backupModel.workspaceID != backupWorkspace }
        guard let reRead = commands(at: commandLog).last(where: { $0["command"] as? String == "save_editor_open" }),
              let reReadParams = reRead["params"] as? [String: Any],
              let reReadTarget = reReadParams["target"] as? [String: String],
              reReadTarget == ["rootId": "main", "relativePath": "Profile1.sav"] else {
            fail("missing inventory target silently fell back to the source path")
        }
        if backupModel.pendingCount != 0 || backupModel.sourceRelativePath != "Profile2_Archive.sav"
            || backupModel.sourceSHA256 != String(repeating: "b", count: 64)
            || backupModel.items.first?.value != AnyHashable(902) {
            fail("explicit read did not replace the document and reset its staged batch")
        }

        let finalWorkspace = model.workspaceID
        let backupOwnerBeforeClose = backupModel.workspaceID
        let beforeFocus = commands(at: commandLog).count
        let reused = toolWindows.open(id: "save-editor", title: "Save Editor", localization: localization, theme: .standard) {
            fail("opening an existing editor recreated its model")
        }
        pump(0.05)
        if reused !== window || commands(at: commandLog).count != beforeFocus {
            fail("focusing an existing editor re-read its document")
        }
        window.performClose(nil)
        pumpUntil {
            commands(at: commandLog).contains { row in
                row["command"] as? String == "save_editor_close"
                    && (row["params"] as? [String: Any])?["workspaceId"] as? String == finalWorkspace
            }
        }
        if model.workspaceID != nil || backupModel.workspaceID != backupOwnerBeforeClose {
            fail("closing one editor released another document")
        }
        backupModel.close()
        pump(0.05)
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
        + [ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", ROOT / "tests/fixtures/swift/NativeAccessibility.swift", generated, main_path]
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
