from macos_fixture_policy import launch_fixture
from fixture_budgets.core_save import JOURNEY_BUDGETS
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from swift_test_compiler import compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
CLANG = shutil.which("clang")
if not SWIFTC or not PYTHON or not CLANG:
    raise SystemExit("swiftc/python3/clang required for Save Manager behavior tests")

worker = r'''
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
policy={'maxCount':20,'maxBytes':268435456,'policyValid':True,'overBudget':False,'warning':''}
protected=False
apply_staged_calls=0
for raw in sys.stdin:
    req=json.loads(raw)
    command=req.get('command','')
    params=req.get('params',{})
    recovery=pathlib.Path.home()/'Library/Application Support/MacGamingTrainer/test/transactions/.rollback-fixture'
    result={'snapshots': [], 'pendingRestore': {'indeterminate': True, 'indeterminateCount': 1}, 'recoveryPaths': [str(recovery)]}
    if command == 'core.save.set_retention':
        policy.update(params)
    if command == 'core.save.protect':
        assert params['snapshotId'] == 'auto-fixture'
        protected=params['protected']
    result['retention']=dict(policy)
    result['storageUsage']={'snapshotCount':1,'snapshotBytes':4321,'automaticCount':0 if protected else 1,
                            'automaticBytes':0 if protected else 4321,'protectedCount':1 if protected else 0,
                            'protectedBytes':4321 if protected else 0,'recoveryCount':1,'recoveryBytes':55}
    result['snapshots']=[{'id':'auto-fixture','name':'Automatic','origin':'automaticPreEdit','protected':protected,
                          'retentionEligible':True,'storageBytes':4321,'valid':True}]
    if command == 'core.save.list':
        time.sleep(0.10)
    elif command == 'core.save.backup':
        time.sleep(0.55)
        if params.get('name') == 'receipt-only':
            result={'operation': {'id': 'committed-backup'}, 'stateRefreshFailed': True}
        elif params.get('name') == 'provider-invalid':
            result['namingWarning']='provider_invalid'
    elif command == 'core.save.delete':
        snapshot_id=params.get('snapshotId')
        time.sleep(0.45 if snapshot_id == 'b' else 0.05)
        result['operation']={'deleted': True, 'id': snapshot_id}
    elif command == 'core.save.apply_staged':
        apply_staged_calls += 1
        result['operation']={'applied': apply_staged_calls >= 2}
    elif command == 'core.save.restore':
        snapshot_id=params.get('snapshotId')
        if snapshot_id == 'rollback-with-path':
            print(json.dumps({
                'type':'result','id':req['id'],'protocolVersion':6,
                'moduleProtocolVersion':5,'gameID':args.game,'ok':False,
                'error':{
                    'code':'rollback_failed',
                    'presentation':'host.save.error.restoreFailed',
                    'recoveryPath': str(recovery),
                },
            }), flush=True)
            continue
        if snapshot_id == 'rollback-blank-path':
            print(json.dumps({
                'type':'result','id':req['id'],'protocolVersion':6,
                'moduleProtocolVersion':5,'gameID':args.game,'ok':False,
                'error':{
                    'code':'rollback_failed',
                    'presentation':'host.save.error.restoreFailed',
                    'recoveryPath': '   ',
                },
            }), flush=True)
            continue
        assert snapshot_id == 'auto-fixture' and params.get('preserveCurrent') is True
    elif command == 'core.save.open_folder':
        if params.get('snapshotId') == 'error':
            print(json.dumps({
                'type':'result','id':req['id'],'protocolVersion':6,
                'moduleProtocolVersion':5,'gameID':args.game,'ok':False,
                'error':{'code':'save_unsafe','presentation':'后端拒绝显示存档'},
                'result':{'folder':str(pathlib.Path(__file__).parent)},
            }), flush=True)
            continue
        result['folder']=str(pathlib.Path(__file__).parent)
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,'result':result,
    }), flush=True)
'''

lifecycle_harness = r'''
import AppKit
import Foundation
import Combine
import SwiftUI

func fail(_ message: String) -> Never {
    fputs(message, stderr)
    fputc(10, stderr)
    exit(1)
}

func waitUntil(_ seconds: TimeInterval, _ predicate: @escaping () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

final class StubHostModel: ObservableObject, TrainerHostModel {
    @Published var backendAvailable = false
    let busy = false
    let connected = false
    let operation = TrainerTextToken(key: "")
    let statusTitle = TrainerTextToken(key: "")
    let connectionDetailText = TrainerTextToken(key: "")
    let hostActionsEnabled = true
    func toggleConnectionFromHost() {}
    func refreshFromHost() {}
    func restartBackendFromHost() {}
    func prepareForTermination(completion: @escaping () -> Void) { completion() }
}

enum SaveContextConfig {
    nonisolated(unsafe) static var targetSuffix = ""
}

struct SupportedSaveTargetModule: TrainerGameModule {
    static var descriptor: GameModuleDescriptor {
        GameModuleDescriptor(
            id: "save-target",
            displayName: "Save Target",
            targetProcessName: "mgt_save_tgt",
            targetBundleIdentifier: "",
            targetExecutablePathSuffix: SaveContextConfig.targetSuffix,
            expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 5,
            supportsSaveManagement: true
        )
    }
    static let presentation = TrainerGamePresentation(headerTitle: "SAVE TARGET")
    static func makeModel(session: TrainerBackendSession) -> StubHostModel { StubHostModel() }
    static func makeContent(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeSidebarActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubHostModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

struct UnsupportedSaveTargetModule: TrainerGameModule {
    static var descriptor: GameModuleDescriptor {
        GameModuleDescriptor(
            id: "no-save-target",
            displayName: "No Save Target",
            targetProcessName: "mgt_save_tgt",
            targetBundleIdentifier: "",
            targetExecutablePathSuffix: SaveContextConfig.targetSuffix,
            expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 5,
            supportsSaveManagement: false
        )
    }
    static let presentation = TrainerGamePresentation(headerTitle: "NO SAVE TARGET")
    static func makeModel(session: TrainerBackendSession) -> StubHostModel { StubHostModel() }
    static func makeContent(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeSidebarActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubHostModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

struct UnsupportedSaveModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "no-save",
        displayName: "No Save",
        targetProcessName: "MGTNoSuchTarget",
        targetBundleIdentifier: "",
        expectedHostProtocolVersion: 6,
        expectedModuleProtocolVersion: 5,
        supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation(headerTitle: "NO SAVE")
    static func makeModel(session: TrainerBackendSession) -> StubHostModel { StubHostModel() }
    static func makeContent(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeSidebarActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubHostModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

struct SupportedNoTargetModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "save-idle",
        displayName: "Save Idle",
        targetProcessName: "MGTNoSuchTarget",
        targetBundleIdentifier: "",
        expectedHostProtocolVersion: 6,
        expectedModuleProtocolVersion: 5,
        supportsSaveManagement: true
    )
    static let presentation = TrainerGamePresentation(headerTitle: "SAVE IDLE")
    static func makeModel(session: TrainerBackendSession) -> StubHostModel { StubHostModel() }
    static func makeContent(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeSidebarActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubHostModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubHostModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

@main
struct Runner {
    @MainActor
    static func main() throws {
        _ = NSApplication.shared
        let args = CommandLine.arguments
        if args.count != 6 { fail("expected python + worker + recovery fixture + target binary + target suffix") }
        SaveContextConfig.targetSuffix = args[5]
        let process = BackendProcess(
            executableURL: URL(fileURLWithPath: args[1]),
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        let descriptor = GameModuleDescriptor(
            id: "test", displayName: "Test", targetProcessName: "", targetBundleIdentifier: "",
            expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 5, supportsSaveManagement: true
        )
        var dispatchedDeletes = 0
        var dispatchedApplyStaged = 0
        try session.start(
            descriptor: descriptor,
            backendScriptURL: URL(fileURLWithPath: args[2]),
            applyPayload: { _ in },
            resetGameState: {},
            log: { message in
                if message.hasPrefix("请求 core.save.delete ·") { dispatchedDeletes += 1 }
                if message.hasPrefix("请求 core.save.apply_staged ·") { dispatchedApplyStaged += 1 }
            },
            onStatusChange: { _ in }
        )
        let model = TrainerSaveManagerModel(session: session)
        model.refresh()
        model.backup()
        if !model.busy { fail("concurrent Save requests did not enter busy state") }
        RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        if !model.busy { fail("busy cleared while a concurrent Save request was still pending") }
        if !waitUntil(2.0, { !model.busy }) { fail("concurrent Save requests did not finish") }
        let recoveryPath = args[3]
        if model.recoveryPaths != [recoveryPath] { fail("alternate HOME hid a valid recovery copy") }
        if TrainerSavePathValidator.validatedDirectoryURL(for: recoveryPath)?.path != recoveryPath {
            fail("alternate HOME rejected a valid directory reveal")
        }

        if model.pendingRestore?.indeterminate != true || model.pendingRestore?.snapshotID != nil {
            fail("an undecodable interrupted claim did not retain explicit recovery state")
        }
        let observedSnapshots = model.snapshots
        model.backup(name: "receipt-only")
        if !waitUntil(2.0, { !model.busy }) { fail("committed backup did not complete") }
        if !model.error.isEmpty || model.notice != "host.save.notice.created" ||
            model.observationWarning != "host.save.warning.refreshFailed" {
            fail("post-commit observation loss erased successful operation feedback")
        }
        if model.snapshots != observedSnapshots || model.recoveryPaths != [recoveryPath] ||
            model.pendingRestore?.indeterminate != true {
            fail("an absent observation erased retained inventory or recovery state")
        }
        model.refresh()
        if !waitUntil(2.0, { !model.busy }) || !model.observationWarning.isEmpty {
            fail("a successful observation did not clear its warning")
        }
        model.backup(name: "provider-invalid")
        if !waitUntil(2.0, { !model.busy }) || !model.error.isEmpty ||
            model.notice != "host.save.notice.created" || model.observationWarning != "host.save.warning.providerName" {
            fail("invalid automatic naming did not preserve the backup receipt with visible maintenance feedback")
        }
        model.refresh()
        if !waitUntil(2.0, { !model.busy }) || !model.observationWarning.isEmpty {
            fail("a refreshed valid presentation did not clear its maintenance warning")
        }

        if model.retention?.maxCount != 20 || model.storageUsage?.snapshotBytes != 4321 {
            fail("Save retention/actual byte usage did not decode")
        }
        var policySaved = false
        model.configureRetention(maxCount: 2, maxBytes: 1048576) { policySaved = $0 }
        if !waitUntil(2.0, { !model.busy }) || !policySaved || model.retention?.maxCount != 2 || model.retention?.maxBytes != 1048576 {
            fail("Save policy commit did not refresh acknowledged values")
        }
        model.protect(id: "auto-fixture", protected: true)
        if !waitUntil(2.0, { !model.busy }) || model.snapshots.first?.protected != true || model.storageUsage?.protectedBytes != 4321 {
            fail("protecting an automatic snapshot did not refresh inventory/usage")
        }
        let old = TrainerSaveSnapshot(row: ["id": "old", "name": "Unknown"])
        if old?.origin != "unclassified" || old?.protected != true || old?.storageBytes != nil {
            fail("legacy snapshot decode inferred automatic ownership or zero bytes")
        }
        let autoSnap = TrainerSaveSnapshot(row: [
            "id": "auto-1",
            "name": "自动名称",
            "nameDetails": ["默认详情"],
            "automaticName": true,
            "localizedPresentation": ["en": ["name": "Auto Name", "details": ["English detail"]]],
            "hot": true,
            "valid": true,
        ])!
        if autoSnap.displayName(for: "en") != "Auto Name" ||
            autoSnap.displayName(for: "zh-CN") != "自动名称" ||
            autoSnap.displayDetails(for: "en") != ["English detail"] ||
            autoSnap.displayDetails(for: "zh-CN") != ["默认详情"] ||
            !autoSnap.hot || !autoSnap.valid {
            fail("automatic snapshot localization or hot/valid decoding failed")
        }
        let customSnap = TrainerSaveSnapshot(row: [
            "id": "custom-1",
            "name": "Custom Name",
            "automaticName": false,
            "localizedPresentation": ["en": ["name": "Auto Name", "details": ["English detail"]]],
        ])!
        if customSnap.displayName(for: "en") != "Custom Name" ||
            customSnap.displayDetails(for: "en") != ["English detail"] ||
            customSnap.hot || customSnap.valid {
            fail("user-renamed snapshot did not preserve custom name or defaulted hot/valid")
        }
        let omittedAuto = TrainerSaveSnapshot(row: [
            "id": "omitted-auto",
            "name": "Stored Name",
            "localizedPresentation": ["en": ["name": "Localized Name"]],
        ])!
        if omittedAuto.automaticName || omittedAuto.displayName(for: "en") != "Stored Name" {
            fail("snapshot with omitted automaticName defaulted to localized automatic display")
        }
        let stagedPending = TrainerPendingRestore(row: [
            "snapshotId": "snap-1",
            "preserveCurrent": true,
            "stagedAt": "2026-11-19T00:00:00",
        ])!
        if stagedPending.indeterminate {
            fail("pending restore with omitted indeterminate defaulted to indeterminate")
        }
        var invalidFinished = false
        model.configureRetention(maxCount: 0, maxBytes: 1) { invalidFinished = !$0 }
        if !invalidFinished || model.busy { fail("invalid retention input dispatched backend work") }

        var trackingDeleteChain = false
        var prematureIdle = false
        var trackingQueuedRequest = false
        var idleWhileQueued = false
        let observation = model.$busy.sink { value in
            if trackingDeleteChain && !value { prematureIdle = true }
            if trackingQueuedRequest && !value { idleWhileQueued = true }
        }
        trackingDeleteChain = true
        model.delete(ids: Set(["b", "a"]))
        if !waitUntil(1.0, { dispatchedDeletes == 2 }) {
            fail("second delete request did not start")
        }
        if prematureIdle { fail("busy published idle between recursive delete requests") }
        if !model.busy { fail("recursive delete chain became idle before its last request completed") }
        trackingDeleteChain = false
        model.refresh() // Queue another request behind the final delete.
        trackingQueuedRequest = true
        if !waitUntil(2.0, { model.notice == "host.save.notice.deletedMany" && model.noticeArguments == ["2"] }) {
            fail("recursive delete chain did not finish coherently")
        }
        trackingQueuedRequest = false
        if idleWhileQueued { fail("busy published idle while a queued Save request was still pending") }
        if !model.busy { fail("busy cleared while a queued Save request was still pending") }
        if !waitUntil(2.0, { !model.busy }) { fail("queued Save request did not finish") }
        observation.cancel()

        model.reveal(id: "error")
        if !waitUntil(2.0, { !model.busy }) { fail("failed reveal did not finish") }
        if model.error != "host.save.error.unsafe" { fail("failed reveal did not map stable Save error code") }
        model.reveal(id: "unsafe")
        if !waitUntil(2.0, { !model.busy }) { fail("unsafe reveal did not finish") }
        if model.error != "host.save.error.invalidFolder" {
            fail("unsafe backend folder was not rejected")
        }

        model.applyStagedIfPossible()
        if !waitUntil(2.0, { !model.busy }) { fail("applyStaged (unapplied) did not finish") }
        if !model.notice.isEmpty || !model.error.isEmpty {
            fail("unapplied applyStagedIfPossible emitted notice/error: \(model.notice) / \(model.error)")
        }
        model.applyStagedIfPossible()
        if !waitUntil(2.0, { !model.busy }) { fail("applyStaged (applied) did not finish") }
        if model.notice != "host.save.notice.pendingApplied" {
            fail("applied applyStagedIfPossible did not emit notice: \(model.notice)")
        }
        model.restore(id: "auto-fixture", preserveCurrent: true)
        if !waitUntil(2.0, { !model.busy }) || model.notice != "host.save.notice.restoreSubmitted" {
            fail("restore did not emit submitted notice: \(model.notice)")
        }
        model.restore(id: "rollback-with-path", preserveCurrent: true)
        if !waitUntil(2.0, { !model.busy }) ||
            model.error != "host.save.error.rollbackFailed" ||
            model.errorArguments != [recoveryPath] {
            fail("rollback_failed with recoveryPath did not surface arguments: \(model.error) \(model.errorArguments)")
        }
        model.restore(id: "rollback-blank-path", preserveCurrent: true)
        if !waitUntil(2.0, { !model.busy }) ||
            model.error != "host.save.error.restoreFailed" ||
            !model.errorArguments.isEmpty {
            fail("rollback_failed with blank path did not fall back to restoreFailed: \(model.error) \(model.errorArguments)")
        }

        // TrainerGameContext owns event-driven staged restore application on
        // backend availability and target exit only when Save management is enabled.
        do {
            let targetProcess = Process()
            targetProcess.executableURL = URL(fileURLWithPath: args[4])
            targetProcess.standardInput = FileHandle.nullDevice
            targetProcess.standardOutput = FileHandle.nullDevice
            targetProcess.standardError = FileHandle.nullDevice
            try targetProcess.run()
            defer {
                if targetProcess.isRunning {
                    targetProcess.terminate()
                    targetProcess.waitUntilExit()
                }
            }
            let modelA = StubHostModel()
            var contextA: TrainerGameContext<SupportedSaveTargetModule>? = TrainerGameContext(model: modelA, session: session)
            if !waitUntil(1.0, { contextA!.targetMonitor.refresh(); return contextA!.targetMonitor.isRunning }) {
                fail("fixture target process was not observed running")
            }
            let beforeA = dispatchedApplyStaged
            modelA.backendAvailable = true
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
            if dispatchedApplyStaged != beforeA {
                fail("running target allowed staged restore apply on backend availability")
            }
            targetProcess.terminate()
            targetProcess.waitUntilExit()
            contextA!.targetMonitor.refresh()
            if !waitUntil(2.0, { dispatchedApplyStaged == beforeA + 1 }) {
                fail("target exit did not trigger staged restore apply")
            }
            if !waitUntil(2.0, { !contextA!.saveManager.busy }) {
                fail("staged restore apply on target exit did not settle")
            }
            contextA = nil
        }

        do {
            let beforeB = dispatchedApplyStaged
            let modelB = StubHostModel()
            var contextB: TrainerGameContext<UnsupportedSaveModule>? = TrainerGameContext(model: modelB, session: session)
            modelB.backendAvailable = true
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
            if dispatchedApplyStaged != beforeB {
                fail("supportsSaveManagement=false dispatched staged restore apply")
            }
            withExtendedLifetime(contextB) {}
            contextB = nil
        }

        do {
            let beforeC = dispatchedApplyStaged
            let modelC = StubHostModel()
            var contextC: TrainerGameContext<SupportedNoTargetModule>? = TrainerGameContext(model: modelC, session: session)
            modelC.backendAvailable = true
            if !waitUntil(2.0, { dispatchedApplyStaged == beforeC + 1 }) {
                fail("backend availability without target did not trigger staged restore apply")
            }
            if !waitUntil(2.0, { !contextC!.saveManager.busy }) {
                fail("staged restore apply on backend availability did not settle")
            }
            contextC = nil
        }

        // targetChanged(_:) guards: target start while backend available must not apply;
        // target exit with supportsSaveManagement=false or backendAvailable=false must not apply.
        do {
            let modelD = StubHostModel()
            var contextD: TrainerGameContext<SupportedSaveTargetModule>? = TrainerGameContext(model: modelD, session: session)
            let initBefore = dispatchedApplyStaged
            modelD.backendAvailable = true
            if !waitUntil(2.0, { dispatchedApplyStaged == initBefore + 1 && !contextD!.saveManager.busy }) {
                fail("contextD initial backend availability apply did not settle")
            }
            let targetProcess = Process()
            targetProcess.executableURL = URL(fileURLWithPath: args[4])
            targetProcess.standardInput = FileHandle.nullDevice
            targetProcess.standardOutput = FileHandle.nullDevice
            targetProcess.standardError = FileHandle.nullDevice
            try targetProcess.run()
            defer {
                if targetProcess.isRunning {
                    targetProcess.terminate()
                    targetProcess.waitUntilExit()
                }
            }
            let beforeStart = dispatchedApplyStaged
            if !waitUntil(1.0, { contextD!.targetMonitor.refresh(); return contextD!.targetMonitor.isRunning }) {
                fail("contextD did not observe launched target")
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.15))
            if dispatchedApplyStaged != beforeStart {
                fail("targetChanged dispatched staged restore apply while target became running")
            }
            targetProcess.terminate()
            targetProcess.waitUntilExit()
            contextD = nil
        }

        do {
            let targetProcess = Process()
            targetProcess.executableURL = URL(fileURLWithPath: args[4])
            targetProcess.standardInput = FileHandle.nullDevice
            targetProcess.standardOutput = FileHandle.nullDevice
            targetProcess.standardError = FileHandle.nullDevice
            try targetProcess.run()
            defer {
                if targetProcess.isRunning {
                    targetProcess.terminate()
                    targetProcess.waitUntilExit()
                }
            }
            let modelE = StubHostModel()
            var contextE: TrainerGameContext<UnsupportedSaveTargetModule>? = TrainerGameContext(model: modelE, session: session)
            if !waitUntil(1.0, { contextE!.targetMonitor.refresh(); return contextE!.targetMonitor.isRunning }) {
                fail("contextE did not observe launched target")
            }
            modelE.backendAvailable = true
            RunLoop.current.run(until: Date().addingTimeInterval(0.20))
            let beforeExitE = dispatchedApplyStaged
            targetProcess.terminate()
            targetProcess.waitUntilExit()
            contextE!.targetMonitor.refresh()
            RunLoop.current.run(until: Date().addingTimeInterval(0.20))
            if dispatchedApplyStaged != beforeExitE {
                fail("targetChanged dispatched staged restore apply when supportsSaveManagement is false")
            }
            contextE = nil
        }

        do {
            let targetProcess = Process()
            targetProcess.executableURL = URL(fileURLWithPath: args[4])
            targetProcess.standardInput = FileHandle.nullDevice
            targetProcess.standardOutput = FileHandle.nullDevice
            targetProcess.standardError = FileHandle.nullDevice
            try targetProcess.run()
            defer {
                if targetProcess.isRunning {
                    targetProcess.terminate()
                    targetProcess.waitUntilExit()
                }
            }
            let modelF = StubHostModel()
            var contextF: TrainerGameContext<SupportedSaveTargetModule>? = TrainerGameContext(model: modelF, session: session)
            if !waitUntil(1.0, { contextF!.targetMonitor.refresh(); return contextF!.targetMonitor.isRunning }) {
                fail("contextF did not observe launched target")
            }
            let beforeExitF = dispatchedApplyStaged
            targetProcess.terminate()
            targetProcess.waitUntilExit()
            contextF!.targetMonitor.refresh()
            RunLoop.current.run(until: Date().addingTimeInterval(0.20))
            if dispatchedApplyStaged != beforeExitF {
                fail("targetChanged dispatched staged restore apply while backendAvailable is false")
            }
            contextF = nil
        }

        model.backup()
        model.refresh()
        if !model.busy { fail("concurrent Save requests did not start before restart") }
        session.restart()
        if model.busy { fail("restarting the backend left cancelled Save requests busy") }
        if model.error != "host.save.error.incomplete" { fail("restart did not surface request failure") }
        if !waitUntil(3.0, { session.currentStatus.notice == "host.backend.notice.restarted" && session.isRunning }) {
            fail("backend did not recover after restart")
        }
        model.refresh()
        if !waitUntil(2.0, { !model.busy }) { fail("Save requests did not recover after restart") }
        model.backup()
        if !model.busy { fail("backup did not start before stop") }
        session.stop()
        _ = waitUntil(1.0) { !session.isStarted }
        if model.busy { fail("stopping the backend left Save busy") }
        if model.error != "host.save.error.incomplete" { fail("stopped request did not surface failure") }
        print("core_save_manager_lifecycle_u01_ok")
    }
}
'''

path_harness = r'''
import Darwin
import Foundation

func fail(_ message: String) -> Never {
    fputs(message, stderr)
    fputc(10, stderr)
    exit(1)
}

func expect(_ accepted: Bool, _ message: String) {
    if !accepted { fail(message) }
}

@main
struct Runner {
    static func main() throws {
        let args = CommandLine.arguments
        if args.count != 3 { fail("expected fixture root + outside directory") }
        let root = URL(fileURLWithPath: args[1], isDirectory: true)
        let outside = URL(fileURLWithPath: args[2], isDirectory: true)
        let manager = FileManager.default
        let insideDirectory = root.appendingPathComponent("inside", isDirectory: true)
        let insideFile = insideDirectory.appendingPathComponent("save.dat")
        try manager.createDirectory(at: insideDirectory, withIntermediateDirectories: true)
        try Data("fixture".utf8).write(to: insideFile)
        let escapedDirectory = root.appendingPathComponent("escape", isDirectory: true)
        try manager.createDirectory(at: outside.appendingPathComponent("secret"), withIntermediateDirectories: true)
        try manager.createSymbolicLink(at: escapedDirectory, withDestinationURL: outside)
        let similarRoot = root.deletingLastPathComponent().appendingPathComponent("trainer-data-extra")
        try manager.createDirectory(at: similarRoot, withIntermediateDirectories: true)
        let specialFile = insideDirectory.appendingPathComponent("save #1.dat")
        try Data("fixture".utf8).write(to: specialFile)

        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideDirectory.path, under: root)?.path == insideDirectory.path,
            "root-contained local directory should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideFile.path, under: root)?.path == insideFile.path,
            "root-contained local file should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: specialFile.path, under: root)?.path == specialFile.path,
            "scheme-less paths containing spaces and # should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: insideDirectory.absoluteString, under: root) != nil,
            "local file URL should be accepted"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: outside.path, under: root) == nil,
            "absolute path outside trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: similarRoot.path, under: root) == nil,
            "sibling with matching root prefix must not pass containment"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: root.appendingPathComponent("../outside").path, under: root) == nil,
            "lexical traversal outside trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: escapedDirectory.appendingPathComponent("secret").path, under: root) == nil,
            "symlink escape from trainer data root must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "https://example.invalid/save", under: root) == nil,
            "non-file URL scheme must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "file://remote.invalid/" + insideFile.path, under: root) == nil,
            "remote file URL must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "relative/save", under: root) == nil,
            "relative paths must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: root.appendingPathComponent("missing").path, under: root) == nil,
            "nonexistent paths must be rejected"
        )
        expect(
            TrainerSavePathValidator.validatedDirectoryURL(for: insideFile.path, under: root) == nil,
            "regular file must not pass directory-only reveal validation"
        )
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: "FILE://" + insideDirectory.path, under: root) != nil,
            "uppercase FILE scheme should be accepted"
        )
        let fifoURL = insideDirectory.appendingPathComponent("pipe")
        expect(mkfifo(fifoURL.path, 0o600) == 0, "fixture could not create FIFO")
        expect(
            TrainerSavePathValidator.validatedLocalURL(for: fifoURL.path, under: root) == nil,
            "non-regular FIFO must be rejected"
        )
        print("core_save_manager_path_validation_u02_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-save-manager-behavior-") as td:
    base = Path(td)
    worker_path = base / "worker.py"
    main_path = base / "lifecycle.swift"
    binary = base / "lifecycle"
    target_source = base / "target.c"
    target_binary = base / "FixtureTarget" / "mgt_save_tgt"
    target_binary.parent.mkdir(parents=True)
    target_source.write_text("#include <unistd.h>\nint main(void) { for (int i = 0; i < 30; ++i) sleep(1); return 0; }\n", encoding="utf-8")
    subprocess.run([CLANG, str(target_source), "-o", str(target_binary)], check=True)
    target_suffix = f"{base.resolve().name}/FixtureTarget/mgt_save_tgt"
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(lifecycle_harness), encoding="utf-8")
    home = base / "effective-home"
    recovery = home / "Library/Application Support/MacGamingTrainer/test/transactions/.rollback-fixture"
    recovery.mkdir(parents=True)
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    compile_swift_test(harness_sources=[main_path], output=binary, swiftc=SWIFTC, cwd=ROOT)
    proc = launch_fixture(
        [str(binary), PYTHON, str(worker_path), str(recovery), str(target_binary), target_suffix],
        cwd=ROOT, env=environment, text=True, capture_output=True, journey='native.core_save_manager_lifecycle_u01_u02.1', budgets=JOURNEY_BUDGETS
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())

with tempfile.TemporaryDirectory(prefix="mgt-save-path-validation-") as td:
    base = Path(td)
    root = base / "trainer-data"
    outside = base / "outside"
    root.mkdir()
    outside.mkdir()
    main_path = base / "path_validation.swift"
    binary = base / "path_validation"
    main_path.write_text(textwrap.dedent(path_harness), encoding="utf-8")
    compile_swift_test(harness_sources=[main_path], output=binary, swiftc=SWIFTC, cwd=ROOT)
    proc = launch_fixture(
        [str(binary), str(root), str(outside)],
        cwd=ROOT, text=True, capture_output=True, journey='native.core_save_manager_lifecycle_u01_u02.2', budgets=JOURNEY_BUDGETS
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
