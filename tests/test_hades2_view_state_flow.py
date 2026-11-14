import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from management_ui_harness import PROFILE_JOURNEY, DIAGNOSTICS_JOURNEY, MANAGEMENT_JOURNEY
from slider_ui_harness import SLIDER_JOURNEY
from visual_hierarchy_harness import VISUAL_HIERARCHY_JOURNEY
from room_picker_alignment_harness import ROOM_PICKER_ALIGNMENT_JOURNEY
from disclosure_ui_harness import DISCLOSURE_JOURNEY
from native_picker_harness import NATIVE_PICKER
from search_ui_harness import SEARCH_JOURNEY
from macos_fixture_policy import launch_fixture

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 SwiftUI state-flow test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
log_path=pathlib.Path(__file__).with_suffix('.commands.jsonl')
profiles=[{'name':'Fixture','updatedAt':'Today'}]
for raw in sys.stdin:
    req=json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({**req, 'fixtureGame': args.game}, sort_keys=True) + '\n')
    command=req['command'];params=req.get('params',{})
    if command=='save_profile' and params.get('name')=='Closing while saving':time.sleep(.2)
    result={'connected':True}
    speed_path=log_path.with_suffix('.speed')
    if speed_path.exists():
        speed=float(speed_path.read_text())
        if command=='set_desired' and params.get('feature')=='gameSpeed':
            speed=params['value'];speed_path.write_text(str(speed))
        result.update(gameSpeed=speed, featureSupport={'gameSpeed':True})
        observation_mode_path=log_path.with_suffix('.speed_observation')
        observation_mode=observation_mode_path.read_text() if observation_mode_path.exists() else 'valid'
        if observation_mode=='empty':
            result['runtimeDiagnostics']={}
        elif observation_mode=='invalid':
            result['runtimeDiagnostics']={'gameSpeedAppliedValue': 'unknown'}
        elif observation_mode=='null':
            result['runtimeDiagnostics']={'gameSpeedAppliedValue': None}
        elif observation_mode!='omitted':
            result['runtimeDiagnostics']={'gameSpeedAppliedValue': speed}
    disclosure_path=log_path.with_suffix('.disclosure')
    if disclosure_path.exists():
        result.update(gameSpeed=1.0,featureSupport={'gameSpeed':int(disclosure_path.read_text())>0})
    world_actions_path=log_path.with_suffix('.world_actions')
    if world_actions_path.exists():
        world_delay_path=log_path.with_suffix('.world_actions_delay')
        if command=='apply_world_exit' and world_delay_path.exists():
            delay=float(world_delay_path.read_text(encoding='utf-8'))
            world_delay_path.unlink()
            time.sleep(delay)
        world_state=json.loads(world_actions_path.read_text(encoding='utf-8'))
        exits=world_state['exits']
        if command=='apply_world_exit':
            for row in exits:
                if row['doorToken']==params['doorToken']:
                    row['activeLease']={'kind':params['kind'],'target':params['target'],'leaseToken':'lease-'+row['doorToken']}
            world_actions_path.write_text(json.dumps(world_state),encoding='utf-8')
        elif command=='cancel_world_exit':
            for row in exits:
                if row['doorToken']==params['doorToken'] and (row.get('activeLease') or {}).get('leaseToken')==params.get('leaseToken'):
                    row.pop('activeLease',None)
            world_actions_path.write_text(json.dumps(world_state),encoding='utf-8')
        result.update(status='ready',scene='run',capabilities=world_state['capabilities'],worldActions={'exits':exits})
    if command in ('list_profiles','save_profile','delete_profile'):
        if command=='save_profile' and params['name']!='__error__':
            profiles=[row for row in profiles if row['name']!=params['name']]+[{'name':params['name'],'updatedAt':'Today'}]
        if command=='delete_profile':profiles=[row for row in profiles if row['name']!=params['name']]
        result={'profiles':profiles}
    if command=='load_profile':result={'shortcuts':{'_layoutVersion':999}}
    mode_path=log_path.with_suffix('.mode')
    mode=mode_path.read_text() if mode_path.exists() else 'viewer'
    if command=='diagnostics':
        checks=[{'name':'Fixture connection','ok':True,'detail':'42'},
                {'name':'Fixture runtime','detail':'Fixture caution'}]
        if mode=='empty':checks=[]
        result={'checks':checks,'passed':100,'total':100}

    reply={'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':__MGT_MODULE_PROTOCOL__,'gameID':args.game,'ok':True,'result':result}
    if command=='diagnostics' and mode=='error':
        reply.update(ok=False,error={'code':'fixture_diagnostics','presentation':'Diagnostic fixture rejected.'})
        reply.pop('result')
    if command=='save_profile' and params.get('name')=='__error__':
        reply.update(ok=False,error={'code':'fixture_profile','presentation':'Profile fixture rejected.'})
        reply.pop('result')
    print(json.dumps(reply), flush=True)
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
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()
        // Native menu, responder and field-editor work runs inside AppKit's
        // application loop. A Timer also leaves nested native pumps free to
        // receive the original model/backend callbacks on the main queue.
        Timer.scheduledTimer(withTimeInterval: 0.01, repeats: false) { _ in
            MainActor.assumeIsolated {
                do { try exerciseJourney() }
                catch { fail("Hades II native fixture: " + String(describing: error)) }
                app.stop(nil)
                let wake = NSEvent.otherEvent(with: .applicationDefined, location: .zero, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: 0, context: nil,
                    subtype: 0, data1: 0, data2: 0)!
                app.postEvent(wake, atStart: false)
            }
        }
        app.run()
    }

    @MainActor
    static func exerciseJourney() throws {
        _ = NSApplication.shared
        guard NSApp.isRunning else { fail("Hades II native journey did not enter the AppKit application event loop") }
        enableNativeAccessibility()
        let args = CommandLine.arguments
        guard args.count == 3 || args.count == 4 else { fail("expected python + worker and optional journey") }
        if args.count == 4 && args[3] == "hierarchy" {
            exerciseVisualHierarchy(descriptor: Hades2GameModule.descriptor, presentation: Hades2GameModule.presentation)
            exerciseRoomPickerAlignment()
            print("hades2_visual_hierarchy_ok")
            return
        }
        let python = URL(fileURLWithPath: args[1])
        let worker = URL(fileURLWithPath: args[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")

        if args.count == 4 && args[3] == "slider" {
            let speedURL = commandLog.deletingPathExtension().appendingPathExtension("speed")
            try "1.0".write(to: speedURL, atomically: true, encoding: .utf8)
            let sliderSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
                executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
            let sliderModel = Hades2TrainerModel(session: sliderSession,
                logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("slider.log")),
                backendScriptURL: worker,
                runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("slider-game-log"),
                shortcutDefaults: InMemoryDefaults())
            sliderModel.hostTargetLifetimeChanged(observation: .init(isRunning: false, launchGeneration: 0))
            let deadline = Date().addingTimeInterval(4)
            while (!sliderModel.backendAvailable || sliderModel.busy) && Date() < deadline { pump(0.02) }
            guard sliderModel.backendAvailable && !sliderModel.busy else { fail("slider backend startup") }
            let observedDeadline = Date().addingTimeInterval(4)
            while sliderModel.appliedGameSpeed == nil && Date() < observedDeadline { pump(0.02) }
            guard sliderModel.appliedGameSpeed == 1.0 else {
                fail("Hades II speed caption did not receive the verified helper observation")
            }
            // Exercise the real backend reply projection: an omitted field is
            // sparse; an explicit empty/invalid diagnostic revokes an old value.
            let observationModeURL = commandLog.deletingPathExtension().appendingPathExtension("speed_observation")
            func checkObservedSpeed(_ mode: String, _ expected: Double?) throws {
                try mode.write(to: observationModeURL, atomically: true, encoding: .utf8)
                let oldCount = commands(at: commandLog).count
                sliderModel.refreshFromHost()
                let deadline = Date().addingTimeInterval(4)
                while Date() < deadline {
                    pump(0.02)
                    if commands(at: commandLog).count > oldCount && !sliderModel.busy { break }
                }
                guard commands(at: commandLog).count > oldCount && !sliderModel.busy else {
                    fail("speed observation refresh did not complete: \(mode)")
                }
                guard sliderModel.appliedGameSpeed == expected else {
                    fail("speed observation \(mode): expected \(String(describing: expected)), got \(String(describing: sliderModel.appliedGameSpeed))")
                }
            }
            try checkObservedSpeed("empty", nil)
            try checkObservedSpeed("valid", 1.0)
            try checkObservedSpeed("omitted", 1.0)
            try checkObservedSpeed("invalid", nil)
            try checkObservedSpeed("null", nil)
            try checkObservedSpeed("valid", 1.0)
            let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
            localization.language = .en
            localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
                resolver: Hades2GameModule.presentationText)
            let name = Hades2GameModule.resolveText(key: "hades2.gameSpeed.a11y", localization: localization)
            try exerciseModuleSlider(Hades2TrainerView(model: sliderModel), localization: localization,
                sliderLabel: name, fieldLabel: name, gameID: "hades2", mutation: "set_desired",
                currentValue: { sliderModel.gameSpeed }, busy: { sliderModel.busy },
                commands: { commands(at: commandLog) }, observe: { speed in
                    try String(speed).write(to: speedURL, atomically: true, encoding: .utf8)
                    sliderModel.refreshFromHost()
                })
            sliderSession.stop()
            pump(0.1)
            return
        }

        if args.count == 4 && args[3] == "disclosure" {
            let availability = commandLog.deletingPathExtension().appendingPathExtension("disclosure")
            try "3".write(to: availability, atomically: true, encoding: .utf8)
            let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
                executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
            let model = Hades2TrainerModel(session: session,
                logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("disclosure.log")),
                backendScriptURL: worker,
                runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("disclosure-game-log"),
                shortcutDefaults: InMemoryDefaults())
            model.hostTargetLifetimeChanged(observation: .init(isRunning: false, launchGeneration: 0))
            let deadline = Date().addingTimeInterval(4)
            while (!model.backendAvailable || model.busy) && Date() < deadline { pump(0.02) }
            guard model.backendAvailable && !model.busy else { fail("disclosure backend startup") }
            let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
            localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
                resolver: Hades2GameModule.presentationText)
            func label(_ key: String, _ language: TrainerPresentationLanguage) -> String {
                Hades2GameModule.resolveText(key: key, language: language, localization: localization)
            }
            try exerciseModuleDisclosure(Hades2TrainerView(model: model), localization: localization, gameID: "hades2",
                expanded: Binding(get: { model.numericControlsExpanded }, set: { model.numericControlsExpanded = $0 }),
                primaryLabel: { label("hades2.vital.runGold", $0) },
                expandedLabel: { label("hades2.feature.damageMultiplier", $0) },
                outsideLabel: { label("hades2.gameSpeed.a11y", $0) },
                conditionalRole: "AXSlider", conditionalLabel: { label("hades2.gameSpeed.a11y", $0) },
                busy: { model.busy }, commands: { commands(at: commandLog) }, observeAvailability: { count in
                    try String(count).write(to: availability, atomically: true, encoding: .utf8)
                    model.refreshFromHost()
                })
            session.stop()
            pump(0.1)
            return
        }
        if args.count == 4 && args[3] == "world_exit" {
            try exerciseWorldExitJourney(python: python, worker: worker, commandLog: commandLog)
            return
        }

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

        let model = Hades2TrainerModel(
            session: session,
            logSink: TrainerLogSink(gameID: Hades2GameModule.descriptor.id),
            shortcutDefaults: InMemoryDefaults()
        )
        // InMemoryDefaults (tests/fixtures/swift) keeps this harness off the
        // real preferences directory; a real suite there cannot be cleaned up
        // afterwards.
        let localizationDefaults = InMemoryDefaults()
        let localization = TrainerLocalizationStore(defaults: localizationDefaults)
        if args.count == 4 && args[3] == "search" {
            exerciseWorkbenchSearch(Hades2HeaderActions(model: model), localization: localization,
                placeholder: { Hades2GameModule.resolveText(key: "hades2.workbench.search", localization: localization) },
                emptyLabel: { Hades2GameModule.resolveText(key: "hades2.workbench.searchEmpty", localization: localization) },
                query: { model.workbenchSearch }, matches: { query in
                    Hades2WorkbenchCatalog.matches(query) { key in
                        TrainerPresentationLanguage.allCases.map {
                            Hades2GameModule.resolveText(key: key, language: $0, localization: localization)
                        }
                    }.map { (id: $0.id, destination: $0.section.id) }
                }, commands: { commands(at: commandLog) })
            session.stop()
            pump(0.15)
            print("hades2_workbench_search_native_ok")
            return
        }
        let host = NSHostingView(
            rootView: Hades2TrainerView(model: model)
                .environmentObject(localization)
        )
        host.frame = NSRect(x: 0, y: 0, width: 1200, height: 900)
        host.layoutSubtreeIfNeeded()
        pump(0.10)

        try? FileManager.default.removeItem(at: commandLog)

        // Locating a function preserves the entire workbench and cannot send a
        // runtime mutation. Numeric results also expose the folded controls.
        model.workbenchSearch = "Grasp"
        model.showWorkbenchSection(.values)
        if !model.workbenchSearch.isEmpty || !model.numericControlsExpanded {
            fail("numeric navigation did not reveal the controls and clear the query")
        }
        model.workbenchSearch = "Garden"
        model.showWorkbenchSection(.resources)
        if !model.workbenchSearch.isEmpty || !model.numericControlsExpanded {
            fail("section navigation reset unrelated numeric disclosure state")
        }
        pump(0.10)
        if !commands(at: commandLog).isEmpty { fail("function navigation dispatched a backend action") }

        model.connected = true
        model.capabilities = [
            "setHealth": true,
            "setMana": true,
            "setArmor": true,
            "setRerolls": true,
            "setSpellCharge": true,
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

        // A present health owner must not enable unrelated operation owners.
        model.status = "ready"
        model.scene = "run"
        if model.canMutateTraits || model.canOpenSellTraits
            || model.canOpenSpecialChoice || model.canAcquireChaosPair {
            fail("unrelated owner capabilities leaked from vital state")
        }
        // Resident capabilities are Hades-owned operation owners. Host
        // presentation status/scene must not re-derive that native policy, and
        // one operation owner must not silently authorize another.
        model.capabilities["traitMutation"] = true
        model.status = "waiting"
        model.scene = "crossroads"
        if !model.canMutateTraits {
            fail("trait UI re-derived ownership from presentation state")
        }
        if model.canOpenSellTraits || model.canOpenSpecialChoice || model.canAcquireChaosPair {
            fail("trait owner leaked into unrelated native operations")
        }
        model.capabilities["traitMutation"] = false
        model.status = "ready"
        model.scene = "run"
        model.capabilities["setMana"] = false
        model.capabilities["setRerolls"] = false
        model.capabilities["setSpellCharge"] = false
        if !model.canSetVital("health") || model.canSetVital("mana") ||
           model.canSetRerolls || model.canSetSpellCharge {
            fail("owner-specific editing flags were ignored")
        }
        try? FileManager.default.removeItem(at: commandLog)
        model.setVital("mana", field: "current", text: "55")
        model.lockVital("mana", locked: true)
        model.setRerolls("5")
        model.lockRerolls(true)
        model.setCounter("spellCharge", text: "30")
        pump(0.20)
        if !commands(at: commandLog).isEmpty {
            fail("unavailable owner was allowed to mutate native state")
        }
        model.capabilities["setMana"] = true
        model.capabilities["setRerolls"] = true
        model.capabilities["setSpellCharge"] = true

        // Completed lock edits use the existing request queue. An unlock must
        // remain the final intent, with no delayed relock after it.
        try? FileManager.default.removeItem(at: commandLog)
        model.setStat("dodge", text: "33.3", locked: true)
        model.setStat("dodge", text: "33.3", locked: false)
        pump(0.60)
        let statCommands = commands(at: commandLog).filter { ($0["command"] as? String) == "set_stat" }
        if statCommands.count != 2 { fail("unlock/relock emitted wrong set_stat count: \(statCommands)") }
        let params = statCommands.last?["params"] as? [String: Any]
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
        let managementSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        let managementModel = Hades2TrainerModel(session: managementSession,
            logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("management.log")),
            backendScriptURL: worker,
            shortcutDefaults: InMemoryDefaults())
        managementModel.hostTargetLifetimeChanged(observation: .init(isRunning: false, launchGeneration: 0))
        managementWait(host, "management backend startup") { managementModel.backendAvailable && !managementModel.busy }
        managementModel.listProfiles()
        managementWait(host, "management inventory") { !managementModel.busy && managementModel.profiles.count == 1 }
        localization.language = .en
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
            resolver: Hades2GameModule.presentationText)
        var profilesPresented = true
        func text(_ key: String) -> String { Hades2GameModule.resolveText(key: key, localization: localization) }
        exerciseProfileManager(
            Hades2ProfileManagerView(model: managementModel,
                isPresented: Binding(get: { profilesPresented }, set: { profilesPresented = $0 })),
            labels: .init(title: text("hades2.manage.profiles"), explanation: "",
                name: text("hades2.profile.namePlaceholder"), picker: "", save: text("hades2.profile.saveCurrent"),
                load: text("hades2.profile.load"), empty: text("hades2.profile.empty")),
            localization: localization, inventory: { managementModel.profiles.map(\.name) },
            busy: { managementModel.busy }, dismissed: { !profilesPresented },
            commands: { commands(at: commandLog) }, afterLoad: { view in
                managementWait(view, "shortcut compatibility warning") {
                    managementModel.profileShortcutWarning.map { managementHasText(localization.string($0), in: view) } == true
                }
            }
        )
        managementCheck(managementModel.profileShortcutWarning == nil, "profile dismissal retained its compatibility warning")
        func setDiagnosticsMode(_ mode: String) throws {
            let path = commandLog.deletingPathExtension().appendingPathExtension("mode")
            try mode.write(to: path, atomically: true, encoding: .utf8)
        }
        try setDiagnosticsMode("viewer")
        managementModel.runDiagnostics()
        managementWait(host, "module diagnostic checks") { !managementModel.busy && managementModel.diagnostics.count == 2 }
        var diagnosticsPresented = true
        try exerciseDiagnostics(Hades2DiagnosticsView(model: managementModel,
                isPresented: Binding(get: { diagnosticsPresented }, set: { diagnosticsPresented = $0 })),
            localization: localization, refreshTitle: text("hades2.diagnostics.rerun"),
            exportTitle: text("hades2.diagnostics.export"), checkName: "Fixture runtime",
            nonpassingStatus: "host.diagnostics.failed", busy: { managementModel.busy },
            count: { managementModel.diagnostics.count }, dismissed: { !diagnosticsPresented },
            commands: { commands(at: commandLog) }, setMode: setDiagnosticsMode)
        exerciseDiagnosticStatuses(localization: localization)
        exerciseManagementRouting(localization: localization)
        let menuCatalog = Hades2ManagementCatalog.make(model: managementModel, localization: localization)
        managementCheck(menuCatalog.additionalMaintenance.map(\.id) == ["prepareSigning", "restoreSigning"],
                        "optional image-maintenance commands lost their module owner")
        menuCatalog.profiles.perform()
        managementWait(host, "profile menu routed to Hades II") {
            !managementModel.busy && managementModel.profilesPresented
                && commands(at: commandLog).last?["command"] as? String == "list_profiles"
        }
        managementModel.profilesPresented = false
        menuCatalog.diagnostics.perform()
        managementWait(host, "diagnostics menu routed to Hades II") {
            !managementModel.busy && managementModel.diagnosticsPresented
                && commands(at: commandLog).last?["command"] as? String == "diagnostics"
        }
        managementModel.diagnosticsPresented = false
        exerciseManagementLayout(content: {
            Hades2ManagementUtilities(model: managementModel, openSaveEditor: {})
                .environment(\.trainerManagementActions, TrainerManagementActions(openSaveManagement: {}))
        }, catalog: { Hades2ManagementCatalog.make(model: managementModel, localization: localization,
                openSaveEditor: {}, openSaveManagement: {}) }, localization: localization)
        exerciseManagementPageDismissal(Hades2TrainerView(model: managementModel), localization: localization,
            show: { managementModel.diagnosticsPresented = true }, dismissed: { !managementModel.diagnosticsPresented })
        exerciseModuleShortcutSheet(Hades2TrainerView(model: managementModel), localization: localization,
            show: { managementModel.shortcutSettingsPresented = true }, isPresented: { managementModel.shortcutSettingsPresented },
            chord: { managementModel.shortcutText(.invincibility) }, commands: { commands(at: commandLog) })
        managementModel.connected = false; managementModel.pid = nil
        managementCheck(!menuCatalog.disableAll.isEnabled && menuCatalog.additionalMaintenance.allSatisfy(\.isEnabled),
                        "detached Hades II command eligibility changed")
        managementModel.pid = 99
        managementCheck(menuCatalog.additionalMaintenance.allSatisfy { !$0.isEnabled },
                        "image-maintenance commands ignored a running target")
        managementModel.pid = nil; managementModel.exiting = true
        let afterExit = commands(at: commandLog).count
        menuCatalog.profiles.perform(); menuCatalog.diagnostics.perform(); menuCatalog.shortcuts.perform()
        menuCatalog.additionalMaintenance.forEach { $0.perform() }
        pump(0.10)
        managementCheck(commands(at: commandLog).count == afterExit
                        && !managementModel.profilesPresented && !managementModel.diagnosticsPresented
                        && !managementModel.shortcutSettingsPresented,
                        "captured Hades II commands crossed shutdown")
        managementCheck(menuCatalog.log.isEnabled && menuCatalog.logHistory.isEnabled,
                        "shutdown removed diagnostic log access")
        managementSession.stop()
        pump(0.20)
        print("hades2_view_state_flow_ok")
    }
}
'''

WORLD_EXIT_JOURNEY = r'''
@MainActor
private func exerciseWorldExitJourney(python: URL, worker: URL, commandLog: URL) throws {
    let worldActionsURL = commandLog.deletingPathExtension().appendingPathExtension("world_actions")
    let worldActionsDelayURL = commandLog.deletingPathExtension().appendingPathExtension("world_actions_delay")
    func writeWorldState(exits: [[String: Any]], worldActionsEnabled: Bool) throws {
        let payload: [String: Any] = [
            "capabilities": ["worldActions": worldActionsEnabled],
            "exits": exits,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        try data.write(to: worldActionsURL, options: .atomic)
    }
    let baselineExits: [[String: Any]] = [
        [
            "doorToken": "exit:1",
            "objectId": 101,
            "ordinal": 1,
            "roomName": "F_Combat01",
            "reward": "RoomMoneyDrop",
            "targets": [
                ["kind": "reward", "id": "MaxHealthDrop"],
                ["kind": "roomCategory", "id": "shop"],
            ],
        ],
        [
            "doorToken": "exit:2",
            "objectId": 102,
            "ordinal": 2,
            "roomName": "F_Story01",
            "reward": "MetaCardPointsCommonDrop",
            "targets": [
                ["kind": "reward", "id": "WeaponUpgrade"],
                ["kind": "roomCategory", "id": "story"],
            ],
        ],
    ]
    try writeWorldState(exits: baselineExits, worldActionsEnabled: true)

    let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
        executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
    let model = Hades2TrainerModel(
        session: session,
        logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("world_exit.log")),
        backendScriptURL: worker,
        runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("world_exit-game-log"),
        shortcutDefaults: InMemoryDefaults()
    )
    model.hostTargetLifetimeChanged(observation: .init(isRunning: false, launchGeneration: 0))
    nativePickerWait("world_exit backend startup") {
        model.backendAvailable && !model.busy && model.canSelectWorldExit
            && model.selectedWorldExitToken == "exit:1"
            && model.selectedWorldExitTarget == "reward:MaxHealthDrop"
    }

    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    localization.language = .en
    localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
        resolver: Hades2GameModule.presentationText)
    let visibility = TrainerGamePageVisibility()
    let viewportHeight = min(CGFloat(760), (NSScreen.main?.visibleFrame.height ?? 900) - 80)
    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 1050, height: viewportHeight),
        styleMask: [.titled, .closable, .resizable],
        backing: .buffered,
        defer: false
    )
    window.isReleasedWhenClosed = false
    let host = NSHostingView(
        rootView: ScrollView {
            Hades2TrainerView(model: model).frame(maxWidth: .infinity, alignment: .leading)
        }
        .preferredColorScheme(.dark)
        .trainerTheme(.standard)
        .environment(\.trainerGamePageVisibility, visibility)
        .environmentObject(localization)
    )
    host.frame = NSRect(x: 0, y: 0, width: 1050, height: viewportHeight)
    window.contentView = host
    window.center()
    activateNativePickerWindow(window)
    defer {
        window.contentView = nil
        window.close()
        session.stop()
        pump(0.10)
    }

    func control(_ role: String, _ id: String) -> NativeAccessibilityControl? {
        host.layoutSubtreeIfNeeded()
        return nativeAccessibilityControls(host).first { $0.role == role && $0.identifier == id }
    }
    func findScrollView(in view: NSView) -> NSScrollView? {
        if let scroll = view as? NSScrollView { return scroll }
        for sub in view.subviews {
            if let found = findScrollView(in: sub) { return found }
        }
        return nil
    }
    func revealWorldExitPanel() {
        nativePickerWait("worldExitPanel scrolled into visible viewport") {
            host.layoutSubtreeIfNeeded()
            guard let scroll = findScrollView(in: host),
                  let document = scroll.documentView,
                  let picker = control("AXPopUpButton", "hades2.worldActions.currentExit"),
                  let target = control("AXPopUpButton", "hades2.worldActions.target"),
                  !picker.frame.isEmpty,
                  !target.frame.isEmpty else { return false }
            let combined = picker.frame.union(target.frame)
            let localRect = document.convert(window.convertFromScreen(combined), from: nil)
            _ = document.scrollToVisible(localRect)
            host.layoutSubtreeIfNeeded()
            let viewport = window.convertToScreen(scroll.contentView.convert(scroll.contentView.bounds, to: nil))
            return viewport.contains(picker.frame)
                && viewport.contains(target.frame)
                && window.screen?.visibleFrame.contains(picker.frame) == true
                && window.screen?.visibleFrame.contains(target.frame) == true
        }
    }
    func exitPicker() -> NativeAccessibilityControl? { control("AXPopUpButton", "hades2.worldActions.currentExit") }
    func targetPicker() -> NativeAccessibilityControl? { control("AXPopUpButton", "hades2.worldActions.target") }
    func applyButton() -> NativeAccessibilityControl? { control("AXButton", "hades2.worldActions.apply") }

    let applyTitle = Hades2GameModule.resolveText(key: "hades2.worldActions.apply", localization: localization)
    let cancelTitle = Hades2GameModule.resolveText(key: "hades2.worldActions.cancel", localization: localization)

    nativePickerWait("real Hades2TrainerView worldExitPanel AX controls mount") {
        exitPicker()?.enabled == true && targetPicker()?.enabled == true && applyButton()?.enabled == true
    }
    revealWorldExitPanel()
    guard applyButton()?.label == applyTitle else {
        fail("worldExitPanel initial button label expected \(applyTitle), got \(applyButton()?.label ?? "nil")")
    }

    // Open revealed in-viewport layout-allocated pickers via pointer click so
    // initial menu highlight is present without Space-key menu-item rebuild races.
    // 1. Switch currentExit popup from exit 1 -> exit 2 in real Hades2TrainerView.
    let exitMenu = selectNativePicker(exitPicker()!, in: window, moving: 1, opening: .pointer)
    guard exitMenu.count == 2 else {
        fail("worldExitPanel currentExit menu expected 2 exits, got \(exitMenu)")
    }
    nativePickerWait("currentExit popup selection updates target picker for exit:2") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "reward:WeaponUpgrade"
            && targetPicker()?.enabled == true
    }

    // 2. Select Route Category -> Story in the real target popup menu.
    let targetMenu = selectNativePicker(targetPicker()!, in: window, moving: 1, opening: .pointer)
    let rewardsHeader = "# " + Hades2GameModule.resolveText(key: "hades2.worldActions.rewards", localization: localization)
    let routesHeader = "# " + Hades2GameModule.resolveText(key: "hades2.worldActions.routes", localization: localization)
    guard targetMenu.count >= 4 && targetMenu.contains(rewardsHeader) && targetMenu.contains(routesHeader) else {
        fail("worldExitPanel target menu lost section headers: \(targetMenu)")
    }
    nativePickerWait("target popup selection updates model.selectedWorldExitTarget") {
        model.selectedWorldExitTarget == "roomCategory:story" && applyButton()?.enabled == true
    }

    // 3. Apply through the real AXButton: while the blocking request is in
    // flight, the target picker remains enabled and Apply is safely gated; on
    // completion, the target popup locks and the button switches to Cancel.
    try? FileManager.default.removeItem(at: commandLog)
    try "0.35".write(to: worldActionsDelayURL, atomically: true, encoding: .utf8)
    guard applyButton()!.press() else { fail("worldExitPanel Apply button refused AXPress") }
    nativePickerWait("in-flight blocking apply keeps targetPicker enabled while gating applyButton") {
        model.busy
            && !model.canAcceptRuntimeAction
            && exitPicker()?.enabled == true
            && targetPicker()?.enabled == true
            && applyButton()?.enabled == false
    }
    nativePickerWait("apply_world_exit locks target picker and switches action to Cancel") {
        let applied = commands(at: commandLog).filter { ($0["command"] as? String) == "apply_world_exit" }
        return applied.count == 1
            && !model.busy
            && model.selectedWorldExitLease?.leaseToken == "lease-exit:2"
            && targetPicker()?.enabled == false
            && applyButton()?.enabled == true
            && applyButton()?.label == cancelTitle
    }
    let applyParams = commands(at: commandLog).last?["params"] as? [String: Any]
    guard applyParams?["doorToken"] as? String == "exit:2"
            && applyParams?["kind"] as? String == "roomCategory"
            && applyParams?["target"] as? String == "story" else {
        fail("apply_world_exit sent unexpected params: \(String(describing: applyParams))")
    }

    // 4. Switching exits updates per-exit target lock and repairs target
    // selection cleanly without leaking a stale cross-door target.
    _ = selectNativePicker(exitPicker()!, in: window, moving: -1, opening: .pointer)
    nativePickerWait("switching to unleased exit:1 unlocks target picker and repairs target") {
        model.selectedWorldExitToken == "exit:1"
            && model.selectedWorldExitTarget == "reward:MaxHealthDrop"
            && targetPicker()?.enabled == true
            && applyButton()?.enabled == true
            && applyButton()?.label == applyTitle
    }
    _ = selectNativePicker(exitPicker()!, in: window, moving: 1, opening: .pointer)
    nativePickerWait("switching back to leased exit:2 restores locked target picker and leased target") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "roomCategory:story"
            && targetPicker()?.enabled == false
            && applyButton()?.enabled == true
            && applyButton()?.label == cancelTitle
    }

    // 5. Cancel through the real AXButton -> unlocks target popup and restores Apply.
    guard applyButton()!.press() else { fail("worldExitPanel Cancel button refused AXPress") }
    nativePickerWait("cancel_world_exit unlocks target picker and restores Apply") {
        let cancels = commands(at: commandLog).filter { ($0["command"] as? String) == "cancel_world_exit" }
        return cancels.count == 1
            && !model.busy
            && model.selectedWorldExitLease == nil
            && model.selectedWorldExitTarget == "roomCategory:story"
            && targetPicker()?.enabled == true
            && applyButton()?.enabled == true
            && applyButton()?.label == applyTitle
    }

    // 6. Editable exit with empty targets disables target popup & Apply while
    // keeping currentExit interactive; disappearing exit repairs onto exit:2.
    let emptyTargetExits = baselineExits + [[
        "doorToken": "exit:3",
        "objectId": 103,
        "ordinal": 3,
        "roomName": "F_MiniBoss01",
        "reward": "RoomMoneyDrop",
        "targets": [],
    ]]
    try writeWorldState(exits: emptyTargetExits, worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("exit:3 mounts in worldExitPanel") {
        model.worldActionExits.count == 3 && !model.busy
    }
    let threeExitMenu = selectNativePicker(exitPicker()!, in: window, moving: 1, opening: .pointer)
    guard threeExitMenu.count == 3 else {
        fail("worldExitPanel currentExit menu expected 3 exits, got \(threeExitMenu)")
    }
    nativePickerWait("empty-target exit:3 disables targetPicker and applyButton") {
        model.selectedWorldExitToken == "exit:3"
            && model.selectedWorldExitTarget.isEmpty
            && exitPicker()?.enabled == true
            && targetPicker()?.enabled == false
            && applyButton()?.enabled == false
    }

    try writeWorldState(exits: [baselineExits[1]], worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("disappeared exit:3 repairs to exit:2 and re-enables targetPicker") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "reward:WeaponUpgrade"
            && !model.busy
            && exitPicker()?.enabled == true
            && targetPicker()?.enabled == true
            && applyButton()?.enabled == true
    }

    // 7. Empty exits list with worldActions enabled disables all three controls.
    try writeWorldState(exits: [], worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("empty exits disables all three real worldExitPanel controls") {
        !model.busy && model.worldActionExits.isEmpty
            && exitPicker()?.enabled == false
            && targetPicker()?.enabled == false
            && applyButton()?.enabled == false
    }

    // 8. Revoking worldActions capability disables all three native controls.
    try writeWorldState(exits: baselineExits, worldActionsEnabled: false)
    model.refreshFromHost()
    nativePickerWait("revoked worldActions disables real worldExitPanel controls") {
        !model.busy && !model.canSelectWorldExit
            && exitPicker()?.enabled == false
            && targetPicker()?.enabled == false
            && applyButton()?.enabled == false
    }
    print("hades2_world_exit_module_journey_ok")
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-view-state-flow-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "view_state_flow"
    # A bare executable's UserDefaults.standard resolves to a domain named after
    # the process, and CFFIXED_USER_HOME does not redirect it on current macOS.
    # Every store this fixture builds therefore receives InMemoryDefaults(), so
    # the user's preference tree is never touched and repeated or concurrent
    # runs start from the same state without deleting a global domain.
    home = td / "home"
    home.mkdir()
    for language in ("en", "zh-CN"):
        localized = td / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", localized / "Host.strings")
    worker_path.write_text(textwrap.dedent(worker.replace("__MGT_MODULE_PROTOCOL__", str(json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["protocolVersion"]))), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness) + PROFILE_JOURNEY + DIAGNOSTICS_JOURNEY + MANAGEMENT_JOURNEY + SLIDER_JOURNEY + VISUAL_HIERARCHY_JOURNEY + ROOM_PICKER_ALIGNMENT_JOURNEY + DISCLOSURE_JOURNEY + SEARCH_JOURNEY + WORLD_EXIT_JOURNEY + NATIVE_PICKER, encoding="utf-8")

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
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
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
    env["CFFIXED_USER_HOME"] = str(home)
    hierarchy = launch_fixture([str(binary), PYTHON, str(worker_path), "hierarchy"],
                               journey="hades2.hierarchy",
                               cwd=ROOT, env=env, text=True, capture_output=True)
    if hierarchy.returncode != 0:
        print(hierarchy.stdout)
        print(hierarchy.stderr)
        raise SystemExit(hierarchy.returncode)
    if "hades2_visual_hierarchy_ok" not in hierarchy.stdout:
        raise SystemExit("Hades II hierarchy fixture exited without completion")
    print(hierarchy.stdout.strip())
    # Reuse the compiled real module, while keeping pointer/field timing out of
    # the existing state-flow budget and using its own backend process/journal.
    slider_worker = td / "slider_worker.py"
    shutil.copy2(worker_path, slider_worker)
    slider_proc = launch_fixture(
        [str(binary), PYTHON, str(slider_worker), "slider"], journey="hades2.slider",
        cwd=ROOT, env=env, text=True, capture_output=True,
    )
    if slider_proc.returncode != 0:
        print(slider_proc.stdout)
        print(slider_proc.stderr)
        raise SystemExit(slider_proc.returncode)
    assert "hades2_slider_module_journey_ok" in slider_proc.stdout, slider_proc.stdout
    print(slider_proc.stdout.strip())
    disclosure_worker = td / "disclosure_worker.py"
    shutil.copy2(worker_path, disclosure_worker)
    disclosure_proc = launch_fixture(
        [str(binary), PYTHON, str(disclosure_worker), "disclosure"], journey="hades2.disclosure",
        cwd=ROOT, env=env, text=True, capture_output=True,
    )
    if disclosure_proc.returncode != 0:
        print(disclosure_proc.stdout)
        print(disclosure_proc.stderr)
        raise SystemExit(disclosure_proc.returncode)
    assert "hades2_disclosure_module_journey_ok" in disclosure_proc.stdout, disclosure_proc.stdout
    print(disclosure_proc.stdout.strip())
    search_proc = launch_fixture([str(binary), PYTHON, str(worker_path), "search"],
                                 journey="hades2.search",
                                 cwd=ROOT, env=env, text=True, capture_output=True)
    if search_proc.returncode != 0:
        print(search_proc.stdout)
        print(search_proc.stderr)
        raise SystemExit(search_proc.returncode)
    assert "hades2_workbench_search_native_ok" in search_proc.stdout, search_proc.stdout
    print(search_proc.stdout.strip())
    world_exit_worker = td / "world_exit_worker.py"
    shutil.copy2(worker_path, world_exit_worker)
    world_exit_proc = launch_fixture(
        [str(binary), PYTHON, str(world_exit_worker), "world_exit"],
        journey="hades2.world_exit",
        cwd=ROOT, env=env, text=True, capture_output=True,
    )
    if world_exit_proc.returncode != 0:
        print(world_exit_proc.stdout)
        print(world_exit_proc.stderr)
        raise SystemExit(world_exit_proc.returncode)
    assert "hades2_world_exit_module_journey_ok" in world_exit_proc.stdout, world_exit_proc.stdout
    print(world_exit_proc.stdout.strip())
    proc = launch_fixture(
        [str(binary), PYTHON, str(worker_path)],
        journey="hades2.state_flow",
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
