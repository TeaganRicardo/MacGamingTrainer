"""A bounded Host journey through both shipped module adapters and native views."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


WORKER = r'''
import argparse, json, os, pathlib, sys, time
parser = argparse.ArgumentParser()
parser.add_argument('--game', required=True)
game = parser.parse_args().game
folder = pathlib.Path(__file__).parent
config = json.loads((folder / 'fixture.json').read_text())
assert game == config['game']
staged_startup_handled = False
for raw in sys.stdin:
    request = json.loads(raw)
    with (folder / 'commands.jsonl').open('a') as stream:
        stream.write(json.dumps({**request, 'fixtureGame': game, 'workerPID': os.getpid()}) + '\n')
    command = request['command']
    delay = folder / 'delay-next-read'
    if command in ('status', 'scan') and delay.exists():
        delay.unlink()
        time.sleep(0.3)
    result = {'connected': False, 'heroReady': False, 'status': 'disconnected'}
    if command == 'catalog':
        result = {'catalog': [], 'resourceCatalog': [], 'traitNames': {}}
    reply = {'type': 'result', 'id': request['id'], 'gameID': game,
             'protocolVersion': config['hostProtocolVersion'],
             'moduleProtocolVersion': config['moduleProtocolVersion']}
    if command in ('scan', 'status', 'catalog', 'disconnect'):
        reply.update(ok=True, result=result)
    elif command == 'core.save.apply_staged' and not staged_startup_handled:
        # The real Context performs this startup handshake for save-capable
        # descriptors. This worker has no SaveService or filesystem target.
        staged_startup_handled = True
        reply.update(ok=True, result={'operation': {'applied': False}})
    else:
        reply.update(ok=False, error={'code': 'unexpected_navigation_command',
                                    'presentation': 'Navigation dispatched an unexpected command.'})
    print(json.dumps(reply), flush=True)
'''


HARNESS = r'''
import AppKit
import SwiftUI

@MainActor func journeyCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("real module navigation: " + message) }
}

@MainActor func journeyPump(_ duration: TimeInterval = 0.03) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.005)), inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor func journeyWait(_ message: String, onFailure: () -> Void = {}, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    repeat {
        if condition() { return }
        journeyPump(0.01)
    } while Date() < deadline
    onFailure()
    fatalError("real module navigation timed out: " + message)
}

func journeyFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(journeyFields)
}

@MainActor final class RetainedNavigationDraft: ObservableObject {
    @Published var text = "original tool draft"
    let source = UUID()
}

struct RetainedNavigationTool: View {
    @ObservedObject var draft: RetainedNavigationDraft
    var body: some View {
        TextField("Retained tool draft", text: $draft.text).frame(width: 380).padding(20)
    }
}

final class StartupAvailabilityModel: ObservableObject, TrainerHostModel {
    @Published private(set) var backendStatus = TrainerBackendStatus()
    private let session: TrainerBackendSession
    private let script: URL?
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var connected: Bool { false }
    var operation: TrainerTextToken { backendStatus.operation }
    var statusTitle: TrainerTextToken { TrainerTextToken(key: "host.disconnected") }
    var connectionDetailText: TrainerTextToken { statusTitle }
    var hostActionsEnabled: Bool { backendAvailable && !busy }

    init(session: TrainerBackendSession, script: URL? = nil) { self.session = session; self.script = script }
    func start() throws {
        try session.start(descriptor: StartupAvailabilityModule.descriptor, backendScriptURL: script,
            applyPayload: { _ in }, resetGameState: {}, log: { _ in },
            onStatusChange: { [weak self] in self?.backendStatus = $0 })
    }
    func refreshFromHost() { session.send("status", operation: "host.refreshStatus", announceSuccess: false) }
    func toggleConnectionFromHost() { fatalError("startup fixture unexpectedly tried to connect a target") }
    func restartBackendFromHost() { session.restart() }
    func prepareForTermination(completion: @escaping () -> Void) { session.stop(); completion() }
}

struct StartupAvailabilityModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(id: "startup_fixture", displayName: "Startup fixture",
        backendGameID: "startup_fixture", targetProcessName: "InertContextStartupFixture",
        targetBundleIdentifier: "test.inert-context-startup-fixture",
        expectedHostProtocolVersion: HadesGameModule.descriptor.expectedHostProtocolVersion,
        expectedModuleProtocolVersion: HadesGameModule.descriptor.expectedModuleProtocolVersion,
        supportsSaveManagement: true)
    static let presentation = TrainerGamePresentation(headerTitle: "Startup fixture")
    static func makeModel(session: TrainerBackendSession) -> StartupAvailabilityModel { .init(session: session) }
    static func makeContent(model: StartupAvailabilityModel) -> EmptyView { EmptyView() }
    static func makeSidebarActions(model: StartupAvailabilityModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StartupAvailabilityModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StartupAvailabilityModel,
                                      localization: TrainerLocalizationStore) -> TrainerEmptyCommands { .init() }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

@MainActor func exerciseContextStartupAvailability(folder: URL, python: URL) throws {
    for readyBeforeContext in [true, false] {
        let name = readyBeforeContext ? "startup_early" : "startup_late"
        let worker = folder.appendingPathComponent(name)
        func commands() -> [String] {
            let text = (try? String(contentsOf: worker.appendingPathComponent("commands.jsonl"), encoding: .utf8)) ?? ""
            return text.split(separator: "\n").compactMap {
                (try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any])?["command"] as? String
            }
        }
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        defer { session.stop() }
        let model = StartupAvailabilityModel(session: session, script: worker.appendingPathComponent("worker.py"))
        if readyBeforeContext { try model.start() }
        journeyCheck(model.backendAvailable == readyBeforeContext,
                     "startup fixture did not establish its required availability ordering")
        let context = TrainerGameContext<StartupAvailabilityModule>(model: model, session: session)
        journeyCheck(!context.targetMonitor.isRunning, "startup fixture unexpectedly matched a running target")
        if !readyBeforeContext {
            journeyCheck(!session.isStarted && commands().isEmpty,
                         "Context fabricated backend availability before the late module started")
            try model.start()
        }
        let diagnose = {
            let detail = "context_startup_failure \(name) status=\(model.backendStatus) saveBusy=\(context.saveManager.busy) saveError=\(context.saveManager.error) commands=\(commands())\n"
            FileHandle.standardError.write(Data(detail.utf8))
        }
        journeyWait(name + " restores pending saves exactly once", onFailure: diagnose) {
            commands() == ["core.save.apply_staged"] && !model.busy && !context.saveManager.busy
        }
        journeyCheck(context.saveManager.error.isEmpty && model.backendStatus.error.isEmpty,
                     "startup fixture restore handshake failed")
        let lifetime = session.lifecycleID
        let application = TrainerApplicationCoordinator(contexts: [AnyTrainerGameContext(context)])
        for statusCount in 1...2 {
            application.selectedGameID = StartupAvailabilityModule.descriptor.id
            model.objectWillChange.send()
            model.refreshFromHost()
            journeyWait(name + " ordinary reply", onFailure: diagnose) {
                commands().filter { $0 == "status" }.count == statusCount && !model.busy
            }
        }
        journeyPump(0.03)
        journeyCheck(commands() == ["core.save.apply_staged", "status", "status"]
                     && session.lifecycleID == lifetime && context.saveManager.error.isEmpty,
                     "selection or ordinary replies replayed the initial restore handshake")
        session.stop()
        journeyWait(name + " worker stopped") { !session.isStarted }
        print(name + "_availability_ok")
    }
    print("context_startup_availability_ok")
}

@main struct RealModuleNavigation {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()
        // Run the journey from AppKit's event loop, after its launch lifecycle.
        // A main-queue closure would hold that queue while the journey pumps
        // native input and waits for the actual module/backend callbacks.
        Timer.scheduledTimer(withTimeInterval: 0.01, repeats: false) { _ in
            MainActor.assumeIsolated {
                do { try exerciseJourney() }
                catch { fatalError("real module navigation: " + String(describing: error)) }
                app.stop(nil)
                let wake = NSEvent.otherEvent(with: .applicationDefined, location: .zero, modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: 0, context: nil,
                    subtype: 0, data1: 0, data2: 0)!
                app.postEvent(wake, atStart: false)
            }
        }
        app.run()
    }

    @MainActor static func exerciseJourney() throws {
        let started = ProcessInfo.processInfo.systemUptime
        let app = NSApplication.shared
        enableNativeAccessibility()
        let folder = URL(fileURLWithPath: CommandLine.arguments[1])
        let python = URL(fileURLWithPath: CommandLine.arguments[2])
        try exerciseContextStartupAvailability(folder: folder, python: python)
        if CommandLine.arguments.dropFirst(3).first == "startup" { return }
        func commands(_ game: String) -> [[String: Any]] {
            let url = folder.appendingPathComponent(game).appendingPathComponent("commands.jsonl")
            let text = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            return text.split(separator: "\n").compactMap {
                try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
            }
        }
        func session() -> TrainerBackendSession {
            TrainerBackendSession(client: BackendClient(process: BackendProcess(
                executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        }
        let firstSession = session(), secondSession = session()
        defer { firstSession.stop(); secondSession.stop() }
        let firstFolder = folder.appendingPathComponent("hades")
        let secondFolder = folder.appendingPathComponent("hades2")
        let firstLog = TrainerLogSink(url: firstFolder.appendingPathComponent("host.log"))
        let secondLog = TrainerLogSink(url: secondFolder.appendingPathComponent("host.log"))
        let first = HadesTrainerModel(session: firstSession,
            backendScriptURL: firstFolder.appendingPathComponent("worker.py"), defaults: InMemoryDefaults(),
            logSink: firstLog)
        let second = Hades2TrainerModel(session: secondSession,
            logSink: secondLog,
            backendScriptURL: secondFolder.appendingPathComponent("worker.py"),
            runLogDirectoryURL: secondFolder.appendingPathComponent("run-log"))
        let firstContext = TrainerGameContext<HadesGameModule>(model: first, session: firstSession)
        let secondContext = TrainerGameContext<Hades2GameModule>(model: second, session: secondSession)
        journeyCheck(!firstContext.targetMonitor.isRunning && !secondContext.targetMonitor.isRunning,
                     "this synthetic navigation fixture requires both actual games to be closed")
        let application = TrainerApplicationCoordinator(contexts: [
            AnyTrainerGameContext(firstContext), AnyTrainerGameContext(secondContext)])
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.language = .en
        firstContext.registerPresentation(localization)
        secondContext.registerPresentation(localization)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 1077, height: 800),
                              styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentViewController = NSHostingController(rootView:
            TrainerGamePages(application: application).environmentObject(localization).trainerTheme(.standard))
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        func diagnoseStartup() {
            firstSession.flushDiagnostics(); secondSession.flushDiagnostics()
            firstLog.flush(); secondLog.flush()
            func state(_ backend: TrainerBackendStatus, modelError: String,
                       session: TrainerBackendSession, save: TrainerSaveManagerModel, game: String) -> [String: Any] {
                ["backendAvailable": backend.backendAvailable, "busy": backend.busy,
                 "backendError": backend.error, "errorCode": backend.errorCode ?? "",
                 "modelError": modelError, "protocolCompatible": backend.protocolCompatible,
                 "sessionStarted": session.isStarted, "sessionRunning": session.isRunning,
                 "saveBusy": save.busy, "saveError": save.error,
                 "commands": commands(game).compactMap { $0["command"] as? String }]
            }
            let diagnostic: [String: Any] = [
                "active": app.isActive, "key": window.isKeyWindow,
                "visible": window.isVisible, "running": app.isRunning,
                "hades": state(first.backendStatus, modelError: first.localError,
                    session: firstSession, save: firstContext.saveManager, game: "hades"),
                "hades2": state(second.backendStatus, modelError: second.error,
                    session: secondSession, save: secondContext.saveManager, game: "hades2")]
            let data = try! JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys])
            FileHandle.standardError.write(Data("real_module_navigation_startup=".utf8) + data + Data("\n".utf8))
        }
        journeyWait("active native Host and both real module backends", onFailure: diagnoseStartup) {
            app.isActive && window.isKeyWindow && first.backendAvailable && second.backendAvailable
                && !first.busy && !second.busy
                && !firstContext.saveManager.busy && !secondContext.saveManager.busy
                && commands("hades").contains { ($0["command"] as? String) == "core.save.apply_staged" }
                && commands("hades2").contains { ($0["command"] as? String) == "core.save.apply_staged" }
        }
        journeyPump(0.05)
        journeyCheck(firstContext.saveManager.error.isEmpty && secondContext.saveManager.error.isEmpty,
                     "real Context startup save handshake failed")
        let firstLifetime = firstSession.lifecycleID, secondLifetime = secondSession.lifecycleID
        let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        print("real_module_navigation_system_reduce_motion=\(reduced)")
        let settling = TrainerMotion.duration(.selection, reduceMotion: reduced) + 0.08
        let firstBefore = commands("hades").count, secondBefore = commands("hades2").count
        journeyCheck(firstBefore > 0 && secondBefore > 0, "one real adapter never reached its own worker")
        func control(_ id: String) -> NativeAccessibilityControl {
            guard let node = nativeAccessibilityControls(window).first(where: { $0.identifier == id }) else {
                fatalError("real module navigation: missing native control \(id)")
            }
            return node
        }
        func section(_ id: String) -> NativeAccessibilityControl { control("trainer.section." + id) }
        func sectionIDs() -> [String] {
            nativeAccessibilityControls(window).compactMap(\.identifier).filter { $0.hasPrefix("trainer.section.") }
        }
        func expectSections(_ ids: [String]) {
            journeyWait("only the selected module's section index") {
                let actual = sectionIDs()
                return actual.count == ids.count && Set(actual) == Set(ids.map { "trainer.section." + $0 })
            }
        }
        func searchField() -> NSTextField {
            let title = HadesPresentation.text("hades.workbench.search", language: localization.language)
            let fields = journeyFields(window.contentView!).filter { $0.placeholderString == title && $0.isEnabled }
            journeyCheck(fields.count == 1, "Host must expose exactly one enabled module search field")
            return fields[0]
        }
        func scroll() -> NSScrollView {
            guard let result = searchField().enclosingScrollView else {
                fatalError("real module navigation: actual module header has no native viewport")
            }
            return result
        }
        var measuredSwitches: [(game: String, press: Double, settle: Double)] = []
        func selectGame(_ id: String, measure: Bool = false) {
            let began = ProcessInfo.processInfo.systemUptime
            journeyCheck(control("host.game." + id).press(), "game card rejected native AX press")
            let pressed = ProcessInfo.processInfo.systemUptime
            journeyWait("selected game \(id)") { application.selectedGameID == id }
            expectSections(id == "hades" ? HadesWorkbenchSection.visible.map(\.id) : Hades2WorkbenchSection.allCases.map(\.id))
            let settled = ProcessInfo.processInfo.systemUptime
            if measure {
                measuredSwitches.append((id, pressed - began, settled - began))
            }
            journeyPump(0.03)
        }
        func navigate(_ id: String, _ navigation: TrainerSectionNavigation) {
            journeyCheck(section(id).press(), "module section rejected native AX press")
            journeyWait("real module destination \(id)") { navigation.selection == id && navigation.request == nil }
            journeyPump(settling)
        }
        func headingFrame(_ title: String, in scroll: NSScrollView) -> NSRect {
            let viewport = window.convertToScreen(scroll.convert(scroll.bounds, to: nil))
            guard let heading = nativeAccessibilityControls(window).first(where: {
                $0.role == "AXStaticText" && $0.text == title && $0.frame.minX >= viewport.minX
            }) else { fatalError("real module navigation: missing visible section heading \(title)") }
            journeyCheck(heading.frame.minY >= viewport.minY - 2 && heading.frame.maxY <= viewport.maxY + 2,
                         "section target hid its real heading outside the viewport: \(title)")
            return heading.frame
        }
        func checkHeading(_ title: String, in scroll: NSScrollView) {
            let viewport = window.convertToScreen(scroll.convert(scroll.bounds, to: nil))
            journeyCheck(abs(headingFrame(title, in: scroll).maxY - viewport.maxY) < 4,
                         "actual section heading did not align with its native viewport: \(title)")
        }

        expectSections(HadesWorkbenchSection.visible.map(\.id))
        // Warm both retained real module trees before measuring the steady-state
        // interaction the user reported. The settle boundary is the first point
        // where the destination module's native section index is actually exposed.
        for _ in 0..<2 {
            selectGame("hades2")
            selectGame("hades")
        }
        for _ in 0..<6 {
            selectGame("hades2", measure: true)
            selectGame("hades", measure: true)
        }
        let switchPresses = measuredSwitches.map(\.press).sorted()
        let switchSettles = measuredSwitches.map(\.settle).sorted()
        let p95Index = max(0, Int(ceil(Double(switchSettles.count) * 0.95)) - 1)
        print("real_module_switch_timing samples=\(measuredSwitches.count) press_max=\(switchPresses.last ?? 0) settle_p95=\(switchSettles[p95Index]) settle_max=\(switchSettles.last ?? 0)")
        let firstSearch = searchField(), firstScroll = scroll()
        // Every shipped section ID must resolve to its own mounted native
        // target. No test-only target registry or fake module replaces it.
        for target in HadesWorkbenchSection.visible {
            navigate(target.id, firstContext.navigation)
            _ = headingFrame(HadesPresentation.text(target.titleKey, language: .en), in: firstScroll)
        }
        navigate(HadesWorkbenchSection.common.id, firstContext.navigation)
        checkHeading(HadesPresentation.text(HadesWorkbenchSection.common.titleKey, language: .en), in: firstScroll)
        let firstCommon = firstScroll.contentView.bounds.origin.y
        navigate(HadesWorkbenchSection.management.id, firstContext.navigation)
        let firstManagement = firstScroll.contentView.bounds.origin.y
        journeyCheck(firstManagement > firstCommon + 100, "real Hades sections did not move the native viewport")

        // A real pending read remains owned by Hades while its scroll is
        // interrupted by selection of the other real module.
        try "delay".write(to: firstFolder.appendingPathComponent("delay-next-read"), atomically: true, encoding: .utf8)
        first.refreshFromHost()
        journeyCheck(first.busy, "real Hades refresh did not become pending")
        let switchToSecond = control("host.game.hades2")
        journeyCheck(section(HadesWorkbenchSection.common.id).press(), "Hades jump rejected")
        if reduced {
            journeyWait("reduced-motion Hades destination") { abs(firstScroll.contentView.bounds.origin.y - firstCommon) < 2 }
        } else {
            let deadline = Date().addingTimeInterval(2)
            var inFlight = false
            while Date() < deadline {
                journeyPump(0.002)
                let offset = firstScroll.contentView.bounds.origin.y
                if offset > firstCommon + 2 && offset < firstManagement - 2 { inFlight = true; break }
                if offset <= firstCommon + 2 { break }
            }
            journeyCheck(inFlight, "did not observe real Hades viewport movement before switching")
        }
        journeyCheck(switchToSecond.press() && application.selectedGameID == "hades2", "actual Hades II card did not select")
        journeyCheck(abs(firstScroll.contentView.bounds.origin.y - firstCommon) < 2,
                     "actual Hades adapter left its hidden viewport between sections")
        expectSections(Hades2WorkbenchSection.allCases.map(\.id))
        journeyPump(settling)
        journeyCheck(abs(firstScroll.contentView.bounds.origin.y - firstCommon) < 2,
                     "hidden Hades viewport continued moving")
        journeyWait("pending Hades read after game switch") { !first.busy }
        let secondScroll = scroll()
        journeyCheck(secondScroll !== firstScroll, "both actual modules share a native viewport")
        journeyCheck(!second.numericControlsExpanded, "Hades II values unexpectedly started expanded")
        navigate(Hades2WorkbenchSection.values.id, secondContext.navigation)
        journeyCheck(second.numericControlsExpanded, "real Hades II sidebar bypassed its reveal adapter")
        for target in Hades2WorkbenchSection.allCases {
            navigate(target.id, secondContext.navigation)
            _ = headingFrame(Hades2GameModule.resolveText(key: target.titleKey, localization: localization), in: secondScroll)
        }
        navigate(Hades2WorkbenchSection.common.id, secondContext.navigation)
        checkHeading(Hades2GameModule.resolveText(key: Hades2WorkbenchSection.common.titleKey, localization: localization),
                     in: secondScroll)
        let secondCommon = secondScroll.contentView.bounds.origin.y
        for target in [Hades2WorkbenchSection.management, .values, .common, .common] {
            journeyCheck(section(target.id).press(), "rapid actual Hades II navigation rejected")
        }
        journeyWait("last repeated Hades II destination") {
            secondContext.navigation.selection == Hades2WorkbenchSection.common.id && secondContext.navigation.request == nil
        }
        journeyPump(settling)
        journeyCheck(abs(secondScroll.contentView.bounds.origin.y - secondCommon) < 2,
                     "rapid actual Hades II requests left a different destination")

        try "delay".write(to: secondFolder.appendingPathComponent("delay-next-read"), atomically: true, encoding: .utf8)
        second.refreshFromHost()
        journeyCheck(second.busy, "real Hades II refresh did not become pending")
        selectGame("hades")
        journeyWait("pending Hades II read after game switch") { !second.busy }
        journeyCheck(scroll() === firstScroll && abs(firstScroll.contentView.bounds.origin.y - firstCommon) < 2,
                     "returning to actual Hades replaced its viewport or replayed navigation")

        // Native typing belongs to the real Hades header model. Hide/show must
        // retain the query and resign only the hidden page's field editor.
        journeyCheck(window.makeFirstResponder(firstSearch), "real Hades header refused focus")
        let pageEditor = firstSearch.currentEditor() as! NSTextView
        pageEditor.selectAll(nil)
        pageEditor.insertText("retained unmatched query", replacementRange: pageEditor.selectedRange())
        journeyWait("real Hades search draft") { first.workbenchSearch == "retained unmatched query" }
        selectGame("hades2")
        journeyWait("hidden native editor retired") { window.firstResponder !== pageEditor }
        journeyCheck(first.workbenchSearch == "retained unmatched query" && second.workbenchSearch.isEmpty,
                     "game switch transferred or discarded the module-owned draft")
        selectGame("hades")
        journeyCheck(searchField() === firstSearch && firstSearch.stringValue == "retained unmatched query",
                     "returning to Hades reconstructed its native search draft")

        let toolDraft = RetainedNavigationDraft()
        let source = toolDraft.source
        let tool = firstContext.toolWindows.open(id: "retained-native-draft", title: "Retained native draft",
            localization: localization, theme: .standard) {
                TrainerToolWindowContent { RetainedNavigationTool(draft: toolDraft) }
            }
        let document = tool.contentView
        journeyWait("actual context tool window") { tool.isKeyWindow }
        let toolField = journeyFields(tool.contentView!).first { $0.isEditable }!
        journeyCheck(tool.makeFirstResponder(toolField), "retained tool refused native focus")
        let toolEditor = toolField.currentEditor() as! NSTextView
        toolEditor.selectAll(nil)
        toolEditor.insertText("unfinished tool draft", replacementRange: toolEditor.selectedRange())
        journeyWait("retained tool draft") { toolDraft.text == "unfinished tool draft" }
        for language in [TrainerPresentationLanguage.en, .zhCN] {
            localization.language = language
            journeyCheck(localization.localized("host.refreshStatus") != "host.refreshStatus", "missing Host localization")
            window.setContentSize(NSSize(width: language == .en ? 1077 : 1400, height: 800))
            for game in ["hades2", "hades"] { selectGame(game) }
            journeyCheck(tool.contentView === document && tool.firstResponder === toolEditor
                         && toolDraft.text == "unfinished tool draft" && toolDraft.source == source,
                         "actual game selection replaced or resigned an independent tool document")
        }
        journeyCheck(application.context(id: "hades")?.typed(as: HadesGameModule.self) === firstContext
                     && application.context(id: "hades2")?.typed(as: Hades2GameModule.self) === secondContext,
                     "Host replaced one of its actual module contexts")
        journeyCheck(firstContext.model === first && secondContext.model === second
                     && firstContext.session === firstSession && secondContext.session === secondSession
                     && firstSession.lifecycleID == firstLifetime && secondSession.lifecycleID == secondLifetime
                     && firstSession.isStarted && secondSession.isStarted,
                     "game selection restarted or transferred a real model/backend owner")
        journeyCheck(commands("hades").count == firstBefore + 1 && commands("hades2").count == secondBefore + 1,
                     "navigation dispatched or replayed work beyond its two explicit status reads")
        var workerPIDs: [Int] = []
        for game in ["hades", "hades2"] {
            let journal = commands(game)
            journeyCheck(journal.allSatisfy { ($0["fixtureGame"] as? String) == game
                && ["status", "scan", "catalog", "core.save.apply_staged"].contains($0["command"] as? String ?? "") },
                "navigation escaped its worker or dispatched a trainer mutation")
            let baseline = game == "hades" ? firstBefore : secondBefore
            let startup = journal.prefix(baseline).compactMap { $0["command"] as? String }
            let following = journal.dropFirst(baseline).compactMap { $0["command"] as? String }
            journeyCheck(startup.filter { $0 == "core.save.apply_staged" }.count == 1
                         && following == [game == "hades" ? "status" : "scan"],
                         "navigation replayed the startup handshake or dispatched an unrequested operation")
            let pids = Set(journal.compactMap { $0["workerPID"] as? Int })
            journeyCheck(pids.count == 1, "module worker was recreated across selection")
            workerPIDs.append(pids.first!)
        }
        journeyCheck(workerPIDs[0] != workerPIDs[1], "real modules shared a backend process")
        tool.performClose(nil)
        window.close()
        print("real_module_navigation_elapsed=\(ProcessInfo.processInfo.systemUptime - started)")
        print("hades_and_hades2_host_navigation_ok")
    }
}
'''


def _failure_diagnostics(project: Path) -> None:
    """Keep bounded worker evidence before the disposable checkout is removed."""
    for game in ("hades", "hades2", "startup_early", "startup_late"):
        for name in ("commands.jsonl", "host.log"):
            path = project / game / name
            if not path.exists():
                text = "<missing>"
            else:
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 8192))
                    text = "\n".join(stream.read().decode("utf-8", errors="replace").splitlines()[-16:])
            print(f"real_module_navigation_diagnostic {game}/{name}:\n{text}", file=sys.stderr, flush=True)


def run_real_module_navigation(root: Path, *, startup_only: bool = False) -> None:
    """Compile once; the independent native episode has a 30-second budget."""
    with tempfile.TemporaryDirectory(prefix="mgt-real-module-navigation-") as directory:
        project = Path(directory)
        for name in ("Core", "Hades", "Hades2"):
            shutil.copytree(root / "Sources" / name, project / "Sources" / name)
        for language in ("en", "zh-CN"):
            localized = project / f"{language}.lproj"
            localized.mkdir()
            shutil.copy2(root / "Resources/Localization" / f"{language}.lproj/Host.strings", localized / "Host.strings")
        sys.path.insert(0, str(root / "Tools"))
        from module_support import HOST_PROTOCOL_VERSION

        for game in ("hades", "hades2", "startup_early", "startup_late"):
            folder = project / game
            folder.mkdir()
            (folder / "worker.py").write_text(WORKER)
            is_startup_fixture = game.startswith("startup_")
            manifest = json.loads((root / "Backend/games" / ("hades" if is_startup_fixture else game) / "module.json").read_text())
            (folder / "fixture.json").write_text(json.dumps({
                "game": "startup_fixture" if is_startup_fixture else game, "hostProtocolVersion": HOST_PROTOCOL_VERSION,
                "moduleProtocolVersion": manifest["protocolVersion"],
            }))
        generated = project / "ActiveGames.generated.swift"
        subprocess.run([sys.executable, str(root / "Tools/generate_game_binding.py"), "hades,hades2", str(generated)],
                       check=True, cwd=root)
        main = project / "main.swift"
        main.write_text(HARNESS)
        binary = project / "real-navigation"
        sources = sorted((project / "Sources").rglob("*.swift")) + [
            root / "tests/fixtures/swift/NativeAccessibility.swift",
            root / "tests/fixtures/swift/InMemoryDefaults.swift", generated, main,
        ]
        subprocess.run([shutil.which("swiftc"), "-parse-as-library", *map(str, sources), "-o", str(binary)],
                       check=True, cwd=project)
        home = project / "home"
        home.mkdir()
        env = {**os.environ, "HOME": str(home), "CFFIXED_USER_HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
        arguments = [str(binary), str(project), sys.executable] + (["startup"] if startup_only else [])
        completion = "context_startup_availability_ok" if startup_only else "hades_and_hades2_host_navigation_ok"
        try:
            result = subprocess.run(arguments, cwd=project, env=env, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired as error:
            for output in (error.stdout, error.stderr):
                if output:
                    text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
                    print(text[-8192:], file=sys.stderr, flush=True)
            _failure_diagnostics(project)
            raise
        if result.returncode != 0 or completion not in result.stdout:
            _failure_diagnostics(project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert completion in result.stdout
        print(result.stdout.strip())
