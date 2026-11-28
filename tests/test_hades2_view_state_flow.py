MGT_PLATFORM = "macos"

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
from fixture_budgets.hades2_flow import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test

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
                    row['activeLease']={'room':params['room'],'leaseToken':'lease-'+row['doorToken']}
                    if 'reward' in params:row['activeLease']['reward']=params['reward']
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
    if command=='core.save.apply_staged':result={'operation':{'applied':False}}
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
            let sliderModel = makeFixtureModel(Hades2GameModule.self, session: sliderSession,
                logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("slider.log")),
                backendScriptURL: worker) {
                Hades2TrainerModel(services: $0, runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("slider-game-log"),
                    shortcutDefaults: InMemoryDefaults())
            }

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
            let name = localization.string("hades2.gameSpeed.a11y")
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
            let model = makeFixtureModel(Hades2GameModule.self, session: session,
                logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("disclosure.log")),
                backendScriptURL: worker) {
                Hades2TrainerModel(services: $0, runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("disclosure-game-log"),
                    shortcutDefaults: InMemoryDefaults())
            }

            let deadline = Date().addingTimeInterval(4)
            while (!model.backendAvailable || model.busy) && Date() < deadline { pump(0.02) }
            guard model.backendAvailable && !model.busy else { fail("disclosure backend startup") }
            let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
            localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
                resolver: Hades2GameModule.presentationText)
            func label(_ key: String, _ language: TrainerPresentationLanguage) -> String {
                localization.string(key, language: language)
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
            log: { _ in }
        )

        let model = makeFixtureModel(Hades2GameModule.self, session: session,
            logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("model.log"))) {
            Hades2TrainerModel(services: $0, shortcutDefaults: InMemoryDefaults())
        }
        // InMemoryDefaults (tests/fixtures/swift) keeps this harness off the
        // real preferences directory; a real suite there cannot be cleaned up
        // afterwards.
        let localizationDefaults = InMemoryDefaults()
        let localization = TrainerLocalizationStore(defaults: localizationDefaults)
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
            resolver: Hades2GameModule.presentationText)
        if args.count == 4 && args[3] == "search" {
            struct Hades2SearchFixture: View {
                @ObservedObject var model: Hades2TrainerModel
                var body: some View {
                    if let catalog = Hades2GameModule.workbenchSearch(model: model) {
                        TrainerHostWorkbenchSearch(catalog: catalog)
                    }
                }
            }
            exerciseWorkbenchSearch(Hades2SearchFixture(model: model), localization: localization,
                placeholder: { localization.string("hades2.workbench.search") },
                emptyLabel: { localization.string("hades2.workbench.searchEmpty") },
                query: { model.workbenchSearch }, matches: { query in
                    Hades2WorkbenchCatalog.matches(query) { key in
                        TrainerPresentationLanguage.allCases.map {
                            localization.string(key, language: $0)
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
        model.disconnectFromHost()
        if model.editGeneration == editGeneration {
            fail("disconnect barrier did not invalidate editor drafts")
        }
        pump(0.20)

        session.stop()
        pump(0.20)
        let managementLocalization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        let managementSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        let menuContext = TrainerGameContext<Hades2GameModule>(
            session: managementSession,
            backendScriptURL: worker,
            logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("management.log")),
            targetMonitor: TrainerTargetProcessMonitor(snapshot: { .init(isRunning: false, launchGeneration: 0) }),
            localization: managementLocalization
        ) {
            Hades2TrainerModel(services: $0, shortcutDefaults: InMemoryDefaults())
        }
        let managementModel = menuContext.model

        managementWait(host, "management backend startup") {
            managementModel.backendAvailable && !managementModel.busy && !menuContext.saveManager.busy
        }
        managementModel.listProfiles()
        managementWait(host, "management inventory") { !managementModel.busy && managementModel.profiles.count == 1 }
        managementLocalization.language = .en
        var profilesPresented = true
        func text(_ key: String) -> String { managementLocalization.string(key) }
        exerciseProfileManager(
            Hades2ProfileManagerView(model: managementModel,
                isPresented: Binding(get: { profilesPresented }, set: { profilesPresented = $0 })),
            labels: .init(title: text("hades2.manage.profiles"), explanation: "",
                name: text("hades2.profile.namePlaceholder"), picker: "", save: text("hades2.profile.saveCurrent"),
                load: text("hades2.profile.load"), empty: text("hades2.profile.empty")),
            localization: managementLocalization, inventory: { managementModel.profiles.map(\.name) },
            busy: { managementModel.busy }, dismissed: { !profilesPresented },
            commands: { commands(at: commandLog) }, afterLoad: { view in
                managementWait(view, "shortcut compatibility warning") {
                    managementModel.profileShortcutWarning.map { managementHasText(managementLocalization.string($0), in: view) } == true
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
            localization: managementLocalization, refreshTitle: text("hades2.diagnostics.rerun"),
            exportTitle: text("hades2.diagnostics.export"), checkName: "Fixture runtime",
            nonpassingStatus: "host.diagnostics.failed", busy: { managementModel.busy },
            count: { managementModel.diagnostics.count }, dismissed: { !diagnosticsPresented },
            commands: { commands(at: commandLog) }, setMode: setDiagnosticsMode)
        exerciseDiagnosticStatuses(localization: managementLocalization)
        exerciseManagementRouting(localization: managementLocalization)
        let menuCatalog = menuContext.resolvedManagementCatalog(localization: managementLocalization)!
        managementCheck(menuCatalog.additionalMaintenance.map(\.id) == ["prepareSigning", "restoreSigning"]
                        && menuCatalog.saveEditor != nil && menuCatalog.saveManagement != nil,
                        "Hades II Host-resolved menu omitted Save actions or image maintenance commands")
        managementCheck(menuContext.managementGroups(localization: managementLocalization).flatMap(\.actions).map(\.id)
                        == menuCatalog.groups.flatMap(\.actions).map(\.id),
                        "Hades II App menu actions diverged from resolved Management page groups")
        menuCatalog.profiles?.perform()
        managementWait(host, "profile menu routed to Hades II") {
            !managementModel.busy && managementModel.profilesPresented
                && commands(at: commandLog).last?["command"] as? String == "list_profiles"
        }
        managementModel.profilesPresented = false
        menuCatalog.diagnostics?.perform()
        managementWait(host, "diagnostics menu routed to Hades II") {
            !managementModel.busy && managementModel.diagnosticsPresented
                && commands(at: commandLog).last?["command"] as? String == "diagnostics"
        }
        managementModel.diagnosticsPresented = false
        let layoutCatalog: () -> TrainerManagementCatalog = {
            menuContext.resolvedManagementCatalog(localization: managementLocalization)!
        }
        exerciseManagementLayout(content: {
            Hades2ManagementUtilities()
                .environment(\.trainerManagementGroups, layoutCatalog().groups)
        }, catalog: layoutCatalog, localization: managementLocalization)
        exerciseManagementPageDismissal(Hades2TrainerView(model: managementModel), localization: managementLocalization,
            show: { managementModel.diagnosticsPresented = true }, dismissed: { !managementModel.diagnosticsPresented })
        exerciseModuleShortcutSheet(Hades2TrainerView(model: managementModel), localization: managementLocalization,
            show: { managementModel.shortcutSettingsPresented = true }, isPresented: { managementModel.shortcutSettingsPresented },
            chord: { managementModel.shortcutText(.invincibility) }, commands: { commands(at: commandLog) })
        managementModel.connected = false; managementModel.pid = nil
        managementCheck(menuCatalog.disableAll?.isEnabled == true && menuCatalog.additionalMaintenance.allSatisfy(\.isEnabled)
                        && menuCatalog.saveManagement?.isEnabled == true,
                        "detached Hades II command eligibility changed")
        managementModel.pid = 99
        managementCheck(menuCatalog.additionalMaintenance.allSatisfy { !$0.isEnabled },
                        "image-maintenance commands ignored a running target")
        managementModel.pid = nil; managementModel.exiting = true
        let afterExit = commands(at: commandLog).count
        menuCatalog.profiles?.perform(); menuCatalog.diagnostics?.perform(); menuCatalog.shortcuts?.perform()
        menuCatalog.additionalMaintenance.forEach { $0.perform() }
        pump(0.10)
        managementCheck(commands(at: commandLog).count == afterExit
                        && menuCatalog.disableAll?.isEnabled == false
                        && !managementModel.profilesPresented && !managementModel.diagnosticsPresented
                        && !managementModel.shortcutSettingsPresented
                        && menuCatalog.saveManagement?.isEnabled == false,
                        "captured Hades II commands crossed shutdown")
        managementCheck(menuCatalog.log?.isEnabled == true && menuCatalog.logHistory?.isEnabled == true,
                        "shutdown removed diagnostic log access")
        managementSession.stop()
        pump(0.20)
        print("hades2_view_state_flow_ok")
    }
}
'''

WORLD_EXIT_JOURNEY = r'''
@MainActor
private final class NestedMenuProbe {
    var tracking: NSMenu?
    var handled = false
}

/// Open the real nested Target menu by pointer, hand its live NSMenu to
/// `body`, then dismiss it. `body` reads structure and may pick a submenu item.
@MainActor
private func withOpenNestedMenu(_ control: NativeAccessibilityControl, in window: NSWindow,
                                _ body: @escaping (NSMenu) -> Void) {
    activateNativePickerWindow(window)
    let probe = NestedMenuProbe()
    let began = NotificationCenter.default.addObserver(forName: NSMenu.didBeginTrackingNotification,
        object: nil, queue: .main) { notification in
        MainActor.assumeIsolated {
            if probe.tracking == nil { probe.tracking = notification.object as? NSMenu }
        }
    }
    let ended = NotificationCenter.default.addObserver(forName: NSMenu.didEndTrackingNotification,
        object: nil, queue: .main) { notification in
        MainActor.assumeIsolated {
            if notification.object as? NSMenu === probe.tracking { probe.tracking = nil }
        }
    }
    let timer = Timer(timeInterval: 0.02, repeats: true) { timer in
        MainActor.assumeIsolated {
            guard !probe.handled, let menu = probe.tracking else { return }
            probe.handled = true
            body(menu)
            menu.cancelTracking()
            timer.invalidate()
        }
    }
    RunLoop.main.add(timer, forMode: .common)
    RunLoop.main.add(timer, forMode: .eventTracking)
    defer {
        timer.invalidate()
        NotificationCenter.default.removeObserver(began)
        NotificationCenter.default.removeObserver(ended)
    }
    let point = window.convertPoint(fromScreen: NSPoint(x: control.frame.midX, y: control.frame.midY))
    for kind in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
        let event = NSEvent.mouseEvent(with: kind, location: point, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: kind == .leftMouseDown ? 1 : 0)!
        NSApp.postEvent(event, atStart: false)
    }
    nativePickerWait("nested Target menu opened, inspected and dismissed") {
        probe.handled && probe.tracking == nil
    }
    nativePickerPump()
}

private func visibleItems(_ menu: NSMenu) -> [NSMenuItem] {
    menu.update()
    return menu.items.filter { !$0.isHidden && !$0.isSeparatorItem }
}

private func isHeader(_ item: NSMenuItem) -> Bool {
    if #available(macOS 14.0, *) { return item.isSectionHeader }
    return false
}

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
    // #832 catalog shape: rewards plus room types; the game's rules warn and
    // only what cannot be built is disabled.
    let baselineExits: [[String: Any]] = [
        [
            "doorToken": "exit:1",
            "objectId": 101,
            "ordinal": 1,
            "roomName": "F_Combat01",
            "roomKind": "combat",
            "reward": "RoomMoneyDrop",
            "rewardWarning": "room_no_reward",
            "targets": [
                ["kind": "reward", "id": "MaxHealthDrop"],
                ["kind": "roomCategory", "id": "combat", "acceptsReward": true, "warning": "door_forced_destination"],
                ["kind": "roomCategory", "id": "shop"],
            ],
        ],
        [
            "doorToken": "exit:2",
            "objectId": 102,
            "ordinal": 2,
            "roomName": "F_Story01",
            "roomKind": "story",
            "reward": "Story",
            "targets": [
                ["kind": "reward", "id": "WeaponUpgrade"],
                ["kind": "reward", "id": "ZeusUpgrade", "warning": "god_limit"],
                ["kind": "reward", "id": "MaxManaDrop", "enabled": false, "reason": "reward_eligibility_probe_error"],
                ["kind": "roomCategory", "id": "combat", "acceptsReward": true],
                ["kind": "roomCategory", "id": "miniboss", "acceptsReward": true, "warning": "native_ineligible"],
                ["kind": "roomCategory", "id": "P_MiniBoss01", "acceptsReward": true, "warning": "biome_depth_too_low"],
                ["kind": "roomCategory", "id": "story"],
                ["kind": "roomCategory", "id": "shop", "warning": "max_creations_this_run"],
            ],
        ],
    ]
    try writeWorldState(exits: baselineExits, worldActionsEnabled: true)

    let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
        executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
    let model = makeFixtureModel(Hades2GameModule.self, session: session,
        logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("world_exit.log")),
        backendScriptURL: worker) {
        Hades2TrainerModel(services: $0, runLogDirectoryURL: worker.deletingLastPathComponent().appendingPathComponent("world_exit-game-log"),
            shortcutDefaults: InMemoryDefaults())
    }

    nativePickerWait("world_exit backend startup") {
        model.backendAvailable && !model.busy && model.canSelectWorldExit
            && model.selectedWorldExitToken == "exit:1"
            && model.selectedWorldExitTarget == "combat>MaxHealthDrop"
    }

    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    localization.language = .en
    localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix,
        resolver: Hades2GameModule.presentationText)
    func string(_ key: String) -> String { localization.string(key) }
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

    func control(_ roles: [String], _ id: String) -> NativeAccessibilityControl? {
        host.layoutSubtreeIfNeeded()
        return nativeAccessibilityControls(host).first {
            roles.contains($0.role ?? "") && $0.identifier == id
        }
    }
    func findScrollView(in view: NSView) -> NSScrollView? {
        if let scroll = view as? NSScrollView { return scroll }
        for sub in view.subviews {
            if let found = findScrollView(in: sub) { return found }
        }
        return nil
    }
    func exitPicker() -> NativeAccessibilityControl? { control(["AXPopUpButton"], "hades2.worldActions.currentExit") }
    func targetMenu() -> NativeAccessibilityControl? {
        control(["AXPopUpButton"], "hades2.worldActions.target")
    }
    func applyButton() -> NativeAccessibilityControl? { control(["AXButton"], "hades2.worldActions.apply") }
    func revealWorldExitPanel() {
        nativePickerWait("worldExitPanel scrolled into visible viewport") {
            host.layoutSubtreeIfNeeded()
            guard let scroll = findScrollView(in: host),
                  let document = scroll.documentView,
                  let picker = exitPicker(), let target = targetMenu(),
                  !picker.frame.isEmpty, !target.frame.isEmpty else { return false }
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

    let applyTitle = string("hades2.worldActions.apply")
    let cancelTitle = string("hades2.worldActions.cancel")
    let warn = " · ⚠︎ "

    nativePickerWait("real Hades2TrainerView worldExitPanel AX controls mount") {
        exitPicker()?.enabled == true && targetMenu()?.enabled == true && applyButton()?.enabled == true
    }
    revealWorldExitPanel()
    guard applyButton()?.label == applyTitle else {
        fail("worldExitPanel initial button label expected \(applyTitle), got \(applyButton()?.label ?? "nil")")
    }

    func checkMutedWarningStyling(_ attributed: NSAttributedString?, primaryPrefix: String, warningText: String, context: String) {
        guard let attributed else { fail("\(context): missing attributedTitle") }
        let full = attributed.string as NSString
        let primaryRange = full.range(of: primaryPrefix)
        let warningRange = full.range(of: warningText)
        guard primaryRange.location != NSNotFound, warningRange.location != NSNotFound else {
            fail("\(context): missing primary '\(primaryPrefix)' or warning '\(warningText)' in '\(attributed.string)'")
        }
        let primaryColor = attributed.attribute(.foregroundColor, at: primaryRange.location, effectiveRange: nil) as? NSColor
        let warningColor = attributed.attribute(.foregroundColor, at: warningRange.location, effectiveRange: nil) as? NSColor
        guard primaryColor != NSColor.secondaryLabelColor, warningColor == NSColor.secondaryLabelColor else {
            fail("\(context): expected muted gray warning vs primary text (primary=\(String(describing: primaryColor)), warning=\(String(describing: warningColor)))")
        }
    }
    func findPopupButton(in view: NSView, identifier: String) -> NSPopUpButton? {
        if let popup = view as? NSPopUpButton, popup.accessibilityIdentifier() == identifier { return popup }
        return view.subviews.lazy.compactMap { findPopupButton(in: $0, identifier: identifier) }.first
    }
    func allTextFields(in view: NSView) -> [NSTextField] {
        (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(allTextFields)
    }

    let combat = string("hades2.worldActions.route.combat")
    let health = string("hades2.reward.MaxHealthDrop")
    let inPlaceWarn = warn + string("hades2.worldActions.unavailable.room_no_reward")
    let inPlaceTitle = combat + " · " + health + inPlaceWarn
    guard targetMenu()?.valueText == inPlaceTitle else {
        fail("in-place selected summary lost its room reward warning: \(targetMenu()?.valueText ?? "nil")")
    }
    let popupButton = findPopupButton(in: host, identifier: "hades2.worldActions.target")
    checkMutedWarningStyling((popupButton?.cell as? NSPopUpButtonCell)?.menuItem?.attributedTitle,
        primaryPrefix: combat + " · " + health, warningText: inPlaceWarn, context: "closed target summary")
    let anyReward = string("hades2.worldActions.anyReward")
    let routedAny = anyReward + warn + string("hades2.worldActions.unavailable.door_forced_destination")
    withOpenNestedMenu(targetMenu()!, in: window) { menu in
        guard let submenu = visibleItems(menu).first(where: { $0.title == combat })?.submenu,
              let anyIndex = submenu.items.firstIndex(where: { $0.title == routedAny }),
              let healthItem = submenu.items.first(where: {
                  $0.title == health + warn + string("hades2.worldActions.unavailable.room_no_reward")
              }) else {
            fail("own-type choices did not distinguish routing from in-place reward warnings")
        }
        checkMutedWarningStyling(healthItem.attributedTitle, primaryPrefix: health, warningText: inPlaceWarn,
            context: "nested reward menu item")
        submenu.performActionForItem(at: anyIndex)
    }
    nativePickerWait("own-type Any Reward summary keeps routing warning") {
        model.selectedWorldExitTarget == "combat"
            && targetMenu()?.valueText == combat + " · " + routedAny
    }
    withOpenNestedMenu(targetMenu()!, in: window) { menu in
        guard let submenu = visibleItems(menu).first(where: { $0.title == combat })?.submenu,
              let healthIndex = submenu.items.firstIndex(where: { $0.title.hasPrefix(health) }) else {
            fail("own-type reward choice disappeared")
        }
        submenu.performActionForItem(at: healthIndex)
    }
    nativePickerWait("in-place choice restores reward warning") { targetMenu()?.valueText == inPlaceTitle }

    // 1. The Exit picker names each door's current room type and reward.
    let exitMenu = selectNativePicker(exitPicker()!, in: window, moving: 1, opening: .pointer)
    let firstExit = localization.string("hades2.worldActions.exitNumber", arguments: ["1"])
        + " · " + string("hades2.worldActions.route.combat") + " · " + string("hades2.reward.RoomMoneyDrop")
    let secondExit = localization.string("hades2.worldActions.exitNumber", arguments: ["2"])
        + " · " + string("hades2.worldActions.route.story")
    guard exitMenu == [firstExit, secondExit] else {
        fail("Exit picker must show room type and reward: \(exitMenu), expected \([firstExit, secondExit])")
    }
    nativePickerWait("currentExit popup selection repairs the Target choice for exit:2") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "combat>WeaponUpgrade"
            && targetMenu()?.enabled == true
    }

    // 2. Target is a nested menu by room type. Warned items stay enabled;
    // only the refused reward is disabled. Pick Miniboss > Zeus.
    var structure: [String] = []
    withOpenNestedMenu(targetMenu()!, in: window) { menu in
        for item in visibleItems(menu) {
            structure.append((item.hasSubmenu ? "> " : "") + item.title + (item.isEnabled ? "" : " [off]"))
            guard let submenu = item.submenu else { continue }
            for child in visibleItems(submenu) {
                structure.append("  " + (isHeader(child) ? "# " : "") + child.title + (child.isEnabled ? "" : " [off]"))
            }
            if item.title == string("hades2.worldActions.route.miniboss"),
               let zeus = submenu.items.firstIndex(where: { $0.title.hasPrefix(string("hades2.worldActions.god.ZeusUpgrade")) }) {
                submenu.performActionForItem(at: zeus)
            }
        }
    }
    let miniboss = string("hades2.worldActions.route.miniboss")
    let zeus = string("hades2.worldActions.god.ZeusUpgrade")
    let mana = string("hades2.reward.MaxManaDrop") + " · " + string("hades2.worldActions.unavailable.reward_eligibility_probe_error") + " [off]"
    func expectedRewards(_ routeWarning: String? = nil) -> [String] {
        let suffix = routeWarning.map { warn + string("hades2.worldActions.unavailable.\($0)") } ?? ""
        return [
            "  " + anyReward + suffix,
            "  # " + string("hades2.worldActions.gods"),
            "  " + zeus + suffix + warn + string("hades2.worldActions.unavailable.god_limit"),
            "  # " + string("hades2.worldActions.rewards"),
            "  " + string("hades2.reward.WeaponUpgrade") + suffix,
            "  " + mana,
        ]
    }
    let expected = ["> " + combat] + expectedRewards()
        + ["> " + miniboss] + expectedRewards("native_ineligible")
        + ["> " + string("hades2.worldActions.room.P_MiniBoss01")]
        + expectedRewards("biome_depth_too_low")
        + [string("hades2.worldActions.route.story"),
           string("hades2.worldActions.route.shop") + warn + string("hades2.worldActions.unavailable.max_creations_this_run")]
    guard structure == expected else {
        fail("nested Target menu structure:\n\(structure.joined(separator: "\n"))\nexpected:\n\(expected.joined(separator: "\n"))")
    }
    nativePickerWait("submenu pick Miniboss > Zeus selects room type and reward together") {
        model.selectedWorldExitTarget == "miniboss>ZeusUpgrade" && applyButton()?.enabled == true
    }
    let warnedChoice = miniboss + " · " + zeus
        + warn + string("hades2.worldActions.unavailable.native_ineligible")
        + warn + string("hades2.worldActions.unavailable.god_limit")
    guard targetMenu()?.valueText == warnedChoice else {
        fail("selected route summary lost routing/reward warnings: \(targetMenu()?.valueText ?? "nil")")
    }

    // 3. Apply through the real AXButton: while the blocking request is in
    // flight, Target stays enabled and Apply is gated; on completion, the
    // game's lease locks Target and the button switches to Cancel.
    try? FileManager.default.removeItem(at: commandLog)
    try "0.35".write(to: worldActionsDelayURL, atomically: true, encoding: .utf8)
    guard applyButton()!.press() else { fail("worldExitPanel Apply button refused AXPress") }
    nativePickerWait("in-flight blocking apply keeps Target enabled while gating Apply") {
        model.busy
            && !model.canAcceptRuntimeAction
            && exitPicker()?.enabled == true
            && targetMenu()?.enabled == true
            && applyButton()?.enabled == false
    }
    nativePickerWait("apply_world_exit locks Target and switches action to Cancel") {
        let applied = commands(at: commandLog).filter { ($0["command"] as? String) == "apply_world_exit" }
        return applied.count == 1
            && !model.busy
            && model.selectedWorldExitLease?.leaseToken == "lease-exit:2"
            && targetMenu()?.enabled == false
            && applyButton()?.enabled == true
            && applyButton()?.label == cancelTitle
    }
    let applyParams = commands(at: commandLog).last?["params"] as? [String: Any]
    guard applyParams?["doorToken"] as? String == "exit:2"
            && applyParams?["room"] as? String == "miniboss"
            && applyParams?["reward"] as? String == "ZeusUpgrade" else {
        fail("apply_world_exit must carry room type and reward: \(String(describing: applyParams))")
    }
    guard targetMenu()?.valueText == warnedChoice else {
        fail("leased route summary lost routing/reward warnings: \(targetMenu()?.valueText ?? "nil")")
    }

    // 4. Switching exits updates per-exit lock and repairs the choice without
    // leaking a stale cross-door target.
    _ = selectNativePicker(exitPicker()!, in: window, moving: -1, opening: .pointer)
    nativePickerWait("switching to unleased exit:1 unlocks Target and repairs its choice") {
        model.selectedWorldExitToken == "exit:1"
            && model.selectedWorldExitTarget == "combat>MaxHealthDrop"
            && targetMenu()?.enabled == true
            && applyButton()?.enabled == true
            && applyButton()?.label == applyTitle
    }
    _ = selectNativePicker(exitPicker()!, in: window, moving: 1, opening: .pointer)
    nativePickerWait("switching back to leased exit:2 restores the game's leased choice") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "miniboss>ZeusUpgrade"
            && targetMenu()?.enabled == false
            && applyButton()?.enabled == true
            && applyButton()?.label == cancelTitle
    }

    // 5. Cancel through the real AXButton -> unlocks Target and restores Apply.
    guard applyButton()!.press() else { fail("worldExitPanel Cancel button refused AXPress") }
    nativePickerWait("cancel_world_exit unlocks Target and restores Apply") {
        let cancels = commands(at: commandLog).filter { ($0["command"] as? String) == "cancel_world_exit" }
        return cancels.count == 1
            && !model.busy
            && model.selectedWorldExitLease == nil
            && model.selectedWorldExitTarget == "miniboss>ZeusUpgrade"
            && targetMenu()?.enabled == true
            && applyButton()?.enabled == true
            && applyButton()?.label == applyTitle
    }

    // 6. An exit with no buildable target disables Target and Apply while
    // keeping the Exit picker interactive; a disappearing exit repairs.
    let emptyTargetExits = baselineExits + [[
        "doorToken": "exit:3",
        "objectId": 103,
        "ordinal": 3,
        "roomName": "F_MiniBoss01",
        "roomKind": "miniboss",
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
    nativePickerWait("empty-target exit:3 disables Target and Apply") {
        model.selectedWorldExitToken == "exit:3"
            && model.selectedWorldExitTarget.isEmpty
            && exitPicker()?.enabled == true
            && targetMenu()?.enabled == false
            && applyButton()?.enabled == false
    }

    try writeWorldState(exits: [baselineExits[1]], worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("disappeared exit:3 repairs to exit:2 and re-enables Target") {
        model.selectedWorldExitToken == "exit:2"
            && model.selectedWorldExitTarget == "combat>WeaponUpgrade"
            && !model.busy
            && exitPicker()?.enabled == true
            && targetMenu()?.enabled == true
            && applyButton()?.enabled == true
    }

    // 7. Empty exits list with worldActions enabled disables all three controls.
    try writeWorldState(exits: [], worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("empty exits disables all three real worldExitPanel controls") {
        !model.busy && model.worldActionExits.isEmpty
            && exitPicker()?.enabled == false
            && targetMenu()?.enabled == false
            && applyButton()?.enabled == false
    }

    // 8. Revoking worldActions capability disables all three native controls.
    try writeWorldState(exits: baselineExits, worldActionsEnabled: false)
    model.refreshFromHost()
    nativePickerWait("revoked worldActions disables real worldExitPanel controls") {
        !model.busy && !model.canSelectWorldExit
            && exitPicker()?.enabled == false
            && targetMenu()?.enabled == false
            && applyButton()?.enabled == false
    }

    // The Fields bridge may report Story or Shop without changing room family.
    // Keep that observed distinction in both languages instead of hiding it.
    let bridgeExits: [[String: Any]] = ["Story", "Shop"].enumerated().map { index, reward in
        ["doorToken": "bridge:\(index)", "objectId": 200 + index, "ordinal": index + 1,
         "roomName": "H_Bridge01", "roomKind": "", "reward": reward,
         "targets": baselineExits[0]["targets"]!]
    }
    try writeWorldState(exits: bridgeExits, worldActionsEnabled: true)
    model.refreshFromHost()
    nativePickerWait("bridge variants mount") {
        !model.busy && model.worldActionExits.count == 2
            && model.selectedWorldExitToken == "bridge:0" && exitPicker()?.enabled == true
    }
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        nativePickerPump()
        revealWorldExitPanel()
        let labels = selectNativePicker(exitPicker()!, in: window,
            moving: language == .en ? 1 : -1, opening: .pointer)
        let expected = ["story", "shop"].enumerated().map { index, reward in
            localization.string("hades2.worldActions.exitNumber", arguments: [String(index + 1)])
                + " · " + string("hades2.worldActions.room.H_Bridge01")
                + " · " + string("hades2.worldActions.route.\(reward)")
        }
        guard labels == expected else {
            fail("bridge exits lost their reported Story/Shop distinction: \(labels), expected \(expected)")
        }
    }

    model.activateAcquisition(.exact)
    nativePickerWait("Chaos encounters available before selecting Chaos") {
        host.layoutSubtreeIfNeeded()
        return model.acquisitionTarget == .exact && allTextFields(in: host).contains {
            $0.accessibilityIdentifier() == "hades2.spawn.chaosEncounters"
        }
    }

    // 9. Verify Boon Rarity Control single-row layout (widths 760/900/1050 EN/ZH),
    // Exact Boons Row 1 alignment right next to search box, and unclipped Default placeholders.
    for width in [CGFloat(760), CGFloat(900), CGFloat(1050)] {
        for language in [TrainerPresentationLanguage.en, .zhCN] {
            localization.language = language
            host.frame = NSRect(x: 0, y: 0, width: width, height: viewportHeight)
            window.setContentSize(NSSize(width: width, height: viewportHeight))
            host.layoutSubtreeIfNeeded()
            nativePickerPump()
            guard let legendary = control(["AXCheckBox"], "hades2.feature.forceLegendary"),
                  let duo = control(["AXCheckBox"], "hades2.feature.forceDuo") else {
                fail("Force Legendary / Force Duo checkboxes missing (lang=\(language), width=\(width))")
            }
            guard abs(legendary.frame.midY - duo.frame.midY) < 2,
                  duo.frame.minX >= legendary.frame.maxX - 1,
                  legendary.frame.height < 28, duo.frame.height < 28 else {
                fail("Force checkboxes wrapped or stacked at width=\(width) lang=\(language): leg=\(legendary.frame) duo=\(duo.frame)")
            }
            let exactTitle = string("hades2.spawn.exactBoons")
            let exactSearchPlaceholder = string("hades2.spawn.search")
            if let levelField = allTextFields(in: host).first(where: { $0.accessibilityIdentifier() == "hades2.acquisition.level" }),
               let exactSearch = allTextFields(in: host).first(where: { $0.placeholderString == exactSearchPlaceholder }) {
                let levelScreen = window.convertToScreen(levelField.convert(levelField.bounds, to: nil))
                let searchScreen = window.convertToScreen(exactSearch.convert(exactSearch.bounds, to: nil))
                let rarityLabel = string("hades2.traits.targetRarity")
                if let rarityPicker = nativeAccessibilityControls(host).first(where: {
                    $0.role == "AXPopUpButton" && ($0.label == rarityLabel || $0.identifier == "hades2.traits.targetRarity")
                        && abs($0.frame.midY - levelScreen.midY) < 20
                }) {
                    guard searchScreen.minX - rarityPicker.frame.maxX <= 68 else {
                        fail("Exact Boons Row 1 controls not right-aligned next to search (search=\(searchScreen), rarity=\(rarityPicker.frame))")
                    }
                }
                if width >= 1000,
                   let titleNode = nativeAccessibilityControls(host).first(where: {
                       $0.role == "AXStaticText" && $0.text == exactTitle && abs($0.frame.midY - levelScreen.midY) < 20
                   }) {
                    guard levelScreen.minX - titleNode.frame.maxX >= 40 else {
                        fail("Exact Boons Row 1 controls stayed left-aligned next to title (title=\(titleNode.frame), level=\(levelScreen))")
                    }
                }
                guard abs(levelScreen.midY - searchScreen.midY) < 20, levelScreen.maxX < searchScreen.minX else {
                    fail("Exact Boons Row 1 level field misaligned with search: level=\(levelScreen) search=\(searchScreen)")
                }
            }
            let defaultPlaceholder = string("hades2.gathering.native")
            guard defaultPlaceholder == (language == .en ? "Default" : "默认") else {
                fail("Expected gathering placeholder 'Default'/'默认', got '\(defaultPlaceholder)'")
            }
            let nativeProbFields = allTextFields(in: host).filter { $0.placeholderString == defaultPlaceholder }
            guard !nativeProbFields.isEmpty else {
                fail("Missing probability fields with placeholder '\(defaultPlaceholder)'")
            }
            for field in nativeProbFields {
                let neededWidth = field.placeholderAttributedString?.size().width
                    ?? ((field.placeholderString ?? "") as NSString).size(
                        withAttributes: [.font: field.font ?? NSFont.systemFont(ofSize: NSFont.systemFontSize)]
                    ).width
                guard neededWidth <= field.bounds.width else {
                    fail("Probability placeholder '\(defaultPlaceholder)' (\(neededWidth)pt) clipped inside \(field.bounds.width)pt field")
                }
            }
        }
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

    compile_swift_test(
        games=("hades2",),
        harness_sources=[
            ROOT / "tests/fixtures/swift/TrainerBackendFixture.swift",
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
            main_path,
        ],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CFFIXED_USER_HOME"] = str(home)
    hierarchy = launch_fixture([str(binary), PYTHON, str(worker_path), "hierarchy"],
                               journey="hades2.hierarchy", budgets=JOURNEY_BUDGETS,
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
        [str(binary), PYTHON, str(slider_worker), "slider"], journey="hades2.slider", budgets=JOURNEY_BUDGETS,
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
        [str(binary), PYTHON, str(disclosure_worker), "disclosure"], journey="hades2.disclosure", budgets=JOURNEY_BUDGETS,
        cwd=ROOT, env=env, text=True, capture_output=True,
    )
    if disclosure_proc.returncode != 0:
        print(disclosure_proc.stdout)
        print(disclosure_proc.stderr)
        raise SystemExit(disclosure_proc.returncode)
    assert "hades2_disclosure_module_journey_ok" in disclosure_proc.stdout, disclosure_proc.stdout
    print(disclosure_proc.stdout.strip())
    search_proc = launch_fixture([str(binary), PYTHON, str(worker_path), "search"],
                                 journey="hades2.search", budgets=JOURNEY_BUDGETS,
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
        journey="hades2.world_exit", budgets=JOURNEY_BUDGETS,
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
        journey="hades2.state_flow", budgets=JOURNEY_BUDGETS,
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
