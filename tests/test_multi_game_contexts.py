"""Two live backend workers keep their identity, requests and tools across selection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from real_module_navigation_harness import run_real_module_navigation

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ContractFixtures/reference_module"
HARNESS = r'''
import AppKit
import SwiftUI

struct NavigationFixtureSidebar: View {
    @Environment(\.trainerNavigateToSection) private var navigate
    @Environment(\.trainerSelectedSection) private var selection
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let gameID: String
    let name: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button(name + " sections") {}.accessibilityIdentifier("test.sections." + gameID)
            ForEach(0..<3) { index in
                TrainerSectionButton(
                    title: localization.language == .en ? "A longer section name \(index)" : "较长的章节导航名称 \(index)",
                    systemImage: "list.bullet", selected: selection == gameID + ".\(index)"
                ) { navigate(gameID + ".\(index)") }
                .accessibilityIdentifier("test.navigate.\(gameID).\(index)")
                .keyboardShortcut(KeyEquivalent(Character(String(index))), modifiers: [.command, .option])
            }
        }
    }
}

struct NavigationFixtureSections: View {
    let gameID: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(0..<3) { index in
                Text("Destination \(gameID).\(index)")
                    .frame(maxWidth: .infinity, minHeight: 420, alignment: .topLeading)
                    .accessibilityIdentifier("test.destination.\(gameID).\(index)")
                    .trainerSectionTarget(gameID + ".\(index)")
            }
            Color.clear.frame(height: 900)
        }
    }
}

@MainActor final class NavigationGeometryState: ObservableObject {
    @Published var prefixHeight: CGFloat = 800
    @Published var tailHeight: CGFloat = 900
    @Published var showTarget = false
}

struct NavigationGeometryFixture: View {
    @ObservedObject var state: NavigationGeometryState
    let navigation: TrainerSectionNavigation
    var body: some View {
        TrainerWorkbenchViewport(navigation: navigation) {
            VStack(spacing: 0) {
                Color.clear.frame(height: state.prefixHeight)
                if state.showTarget {
                    Text("Late destination").frame(maxWidth: .infinity, minHeight: 40, alignment: .topLeading)
                        .trainerSectionTarget("late")
                }
                Color.clear.frame(height: state.tailHeight)
            }
        } feedback: { EmptyView() }
    }
}

final class NavigationPolicyDocument: NSView {
    override var isFlipped: Bool { true }
}

struct NavigationToolField: NSViewRepresentable {
    let field: NSTextField
    func makeNSView(context: Context) -> NSTextField { field }
    func updateNSView(_ view: NSTextField, context: Context) {}
}

func navigationPump(_ seconds: TimeInterval) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)), inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

func navigationClick(in scroll: NSScrollView) {
    let window = scroll.window!
    precondition(scroll.bounds.width > 0 && scroll.bounds.height > 0
                 && scroll.contentView.bounds.width > 0 && scroll.contentView.bounds.height > 0,
                 "native click fixture has an empty viewport: scroll=\(scroll.bounds) clip=\(scroll.contentView.bounds)")
    let localPoint = NSPoint(x: scroll.bounds.midX, y: scroll.bounds.midY)
    precondition(scroll.bounds.contains(localPoint), "fixture click lies outside its native viewport")
    let point = scroll.convert(localPoint, to: nil)
    navigationTrace("fixture-click window=\(window.windowNumber) key=\(window.isKeyWindow) bounds=\(scroll.bounds) point=\(point) pending-scope=\(ObjectIdentifier(scroll))")
    for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
        let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: type == .leftMouseDown ? 1 : 0)!
        NSApp.sendEvent(event)
    }
}

func navigationTrace(_ message: String) {
    FileHandle.standardError.write(Data(("navigation_trace \(ProcessInfo.processInfo.systemUptime) \(message)\n").utf8))
}

@main struct Test {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()
        enableNativeAccessibility()
        let navigation = TrainerSectionNavigation()
        navigation.navigate(to: "first")
        let superseded = navigation.request!
        navigation.navigate(to: "second")
        precondition(!navigation.consume(superseded), "obsolete navigation was applied")
        precondition(navigation.consume(navigation.request!) && navigation.selection == "second")
        navigation.navigate(to: "second")
        precondition(navigation.request != nil, "repeated section selection cannot return to its destination")
        navigation.setVisible(false)
        navigation.navigate(to: "hidden")
        precondition(navigation.request == nil && navigation.selection == "second")
        navigation.setVisible(true)
        precondition(navigation.request == nil, "returning page replayed an old navigation request")
        navigation.navigate(to: "cancelled-wait")
        let cancelledWait = navigation.request!
        navigation.navigate(to: "current-wait")
        let currentWait = navigation.request!
        navigation.cancelRequest(cancelledWait)
        precondition(navigation.request == currentWait, "obsolete cancellation retired a newer navigation")
        navigation.cancelRequest(currentWait)
        precondition(navigation.request == nil && navigation.selection == "second")
        var finishedScrolls: [String] = []
        navigation.navigate(to: "third")
        let third = navigation.request!
        precondition(navigation.consume(third, finishScroll: { finishedScrolls.append("third") }))
        navigation.navigate(to: "fourth")
        let fourth = navigation.request!
        precondition(navigation.consume(fourth, finishScroll: { finishedScrolls.append("fourth") }))
        navigation.didFinishScroll(third)
        navigation.setVisible(false)
        navigation.setVisible(false)
        precondition(finishedScrolls == ["fourth"], "hiding a page finished an obsolete jump or finished twice")
        navigation.setVisible(true)
        navigation.navigate(to: "fifth")
        let fifth = navigation.request!
        precondition(navigation.consume(fifth, finishScroll: { finishedScrolls.append("fifth") }))
        navigation.didFinishScroll(fifth)
        navigation.setVisible(false)
        precondition(finishedScrolls == ["fourth"], "a completed jump replaced a later manual scroll position")
        print("navigation_system_reduce_motion=\(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion)")
        // Two games use the identical Core reply lifetime contract. Out-of-
        // order fixture replies must not adopt retired source/target baselines,
        // replace focused drafts, or replay an old Apply into a new window.
        func verifySaveEditorReplies(_ game: String) {
            let owner = TrainerSaveEditorReplyCoordinator()
            let inventory = owner.capture(.inventory, bindsDocument: false)
            let firstRead = owner.beginNewDocumentRead()
            let secondRead = owner.beginNewDocumentRead()
            precondition(!owner.accepts(inventory) && !owner.accepts(firstRead) && owner.accepts(secondRead),
                         "\(game): rapid source reads accepted an obsolete result")

            owner.bind(workspaceID: "workspace:A", baselineGeneration: "baseline:1")
            precondition(owner.owns(workspaceID: "workspace:A", baselineGeneration: "baseline:1"))
            let oldQuery = owner.capture(.query)
            let oldDetail = owner.capture(.detail)
            let oldReview = owner.capture(.review)
            let advancedDetail = owner.capture(.advancedDetail)
            let recentQuery = owner.capture(.query)
            var visible = "authoritative"
            var focusedDraft = "unfinished typed correction"
            func receive(_ ticket: TrainerSaveEditorReplyCoordinator.Ticket, _ value: String) {
                if owner.accepts(ticket) { visible = value }
            }
            receive(oldQuery, "stale search")
            receive(recentQuery, "latest search")
            precondition(visible == "latest search" && focusedDraft == "unfinished typed correction",
                         "\(game): overlapping search overwrote latest result or focused draft")
            owner.invalidate(.detail)
            precondition(!owner.accepts(oldDetail) && owner.accepts(advancedDetail) && owner.accepts(oldReview),
                         "\(game): detail cancellation invalidated an unrelated request")
            owner.invalidate(.advancedDetail)
            precondition(!owner.accepts(advancedDetail), "\(game): stale Advanced editor detail was accepted")

            // Target selection retains the same backend workspace/generation,
            // but still invalidates old query/review tokens.
            owner.bind(workspaceID: "workspace:A", baselineGeneration: "baseline:1")
            precondition(!owner.accepts(recentQuery) && !owner.accepts(oldReview),
                         "\(game): target switch adopted an old response")
            let capturedRow = ("workspace:A", "baseline:1")
            let pendingApply = owner.capture()
            let pendingQuery = owner.capture(.query)
            owner.bind(workspaceID: "workspace:A", baselineGeneration: "baseline:2")
            precondition(!owner.accepts(pendingApply) && !owner.accepts(pendingQuery)
                         && !owner.owns(workspaceID: capturedRow.0, baselineGeneration: capturedRow.1),
                         "\(game): stale row/Apply crossed an installed document baseline")
            let committedQuery = owner.capture(.query)
            owner.invalidate(.query)
            receive(committedQuery, "cancelled query")
            precondition(visible == "latest search", "\(game): cancelled search repainted the editor")

            // Closing a window during a read also rejects a late success after
            // the next window binds identical backend identity strings.
            let readBeforeClose = owner.beginNewDocumentRead()
            owner.retire()
            precondition(!owner.accepts(readBeforeClose) && !owner.owns(
                workspaceID: "workspace:A", baselineGeneration: "baseline:2"),
                         "\(game): closing retained pending read authority")
            owner.bind(workspaceID: "workspace:A", baselineGeneration: "baseline:2")
            receive(pendingApply, "replayed Apply")
            precondition(visible == "latest search" && focusedDraft == "unfinished typed correction",
                         "\(game): close/reopen accepted a reply from the retired tool window")
            focusedDraft = "new document draft"
            precondition(owner.accepts(owner.capture(.query)) && focusedDraft == "new document draft",
                         "\(game): new document cannot issue a fresh request")
        }
        verifySaveEditorReplies("Hades I")
        verifySaveEditorReplies("Hades II")
        let server = URL(fileURLWithPath: CommandLine.arguments[1])
        let python = URL(fileURLWithPath: CommandLine.arguments[2])
        let firstSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python)))
        let secondSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python)))
        func log(_ game: String, _ message: String) {
            FileHandle.standardError.write(Data(("\(game): \(ProcessInfo.processInfo.systemUptime) \(message)\n").utf8))
        }
        let first = FirstFixtureModel(session: firstSession, backendScriptURL: server,
                                      log: { log("first", $0) })
        let second = SecondFixtureModel(session: secondSession, backendScriptURL: server,
                                       log: { log("second", $0) })
        let firstContext = TrainerGameContext<FirstFixtureGameModule>(model: first, session: firstSession)
        let secondContext = TrainerGameContext<SecondFixtureGameModule>(model: second, session: secondSession)
        let application = TrainerApplicationCoordinator(contexts: [
            AnyTrainerGameContext(firstContext), AnyTrainerGameContext(secondContext)
        ])
        func wait(line: UInt = #line, _ condition: () -> Bool) {
            let limit = Date(timeIntervalSinceNow: 30)
            while !condition() && Date() < limit { navigationPump(0.01) }
            precondition(condition(), "Live context did not reach expected state at \(line); first=\(first.backendStatus), second=\(second.backendStatus)")
        }
        wait { first.backendAvailable && second.backendAvailable && !first.busy && !second.busy }
        firstContext.toggleConnection()
        secondContext.toggleConnection()
        wait { first.connected && second.connected && !first.busy && !second.busy }
        first.setEnabled(true)
        wait { first.enabled && !first.busy }
        var pids: [String: Int] = [:]
        func recordPID(_ session: TrainerBackendSession, _ key: String) {
            session.send("status", operation: "test", reply: { reply in pids[key] = reply.result?["pid"] as? Int })
        }
        recordPID(firstSession, "first")
        recordPID(secondSession, "second")
        wait { pids.count == 2 }
        precondition(pids["first"] != pids["second"])
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        var mayClose = false
        var closes = 0
        let toolDraft = NSTextField(string: "retained tool draft")
        let window = firstContext.toolWindows.open(id: "document", title: "First draft", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { mayClose }, onClose: { closes += 1 }) {
                NavigationToolField(field: toolDraft).frame(width: 240, height: 24)
            }
        }
        let document = window.contentView
        let pageWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 1000),
                                  styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        pageWindow.isReleasedWhenClosed = false
        pageWindow.contentViewController = NSHostingController(rootView:
            TrainerGamePages(application: application).environmentObject(localization).trainerTheme(.standard))
        pageWindow.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        wait { app.isActive && pageWindow.isKeyWindow }
        navigationPump(0.2)
        func fields(_ view: NSView) -> [NSTextField] {
            (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
        }
        guard let draftField = fields(pageWindow.contentView!).first(where: { $0.stringValue == "First draft" }) else {
            preconditionFailure("First game editor was not mounted")
        }
        func gameButton(_ id: String) -> NativeAccessibilityControl {
            guard let button = nativeAccessibilityControls(pageWindow).first(where: {
                $0.identifier == "host.game.\(id)"
            }) else { preconditionFailure("Game is missing from the sidebar: \(id)") }
            return button
        }
        func visibleSections() -> [String] {
            nativeAccessibilityControls(pageWindow).compactMap(\.identifier).filter { $0.hasPrefix("test.sections.") }
        }
        precondition(visibleSections() == ["test.sections.first_fixture"], "Inactive game sections were expanded")
        precondition(!nativeAccessibilityControls(pageWindow).contains {
            $0.role == "AXStaticText" && $0.text == localization.localized("host.gameLibrary") &&
                $0.frame.maxX < draftField.accessibilityFrame().minX
        }, "Game cards must not introduce a library heading")
        let firstGameFrame = gameButton("first_fixture").frame
        let secondGameFrame = gameButton("second_fixture").frame
        precondition(firstGameFrame.maxX < draftField.accessibilityFrame().minX &&
                     abs(firstGameFrame.minX - secondGameFrame.minX) < 1 &&
                     firstGameFrame.minY > secondGameFrame.minY,
                     "Game choices must form a vertical list in the left sidebar")
        precondition(pageWindow.makeFirstResponder(draftField))
        let editor = draftField.currentEditor() as! NSTextView
        editor.selectAll(nil)
        editor.insertText("unfinished draft", replacementRange: editor.selectedRange())
        navigationPump(0.05)
        precondition(gameButton("second_fixture").press())
        wait { application.selectedGameID == "second_fixture" }
        wait { visibleSections() == ["test.sections.second_fixture"] }
        precondition(first.connected && second.connected && first.enabled)
        NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: app)
        precondition(first.activations > 0 && second.activations > 0, "Hidden game lost lifecycle subscription")
        first.setEnabled(false)
        second.setEnabled(true)
        wait { !first.enabled && second.enabled && !first.busy && !second.busy }
        recordPID(firstSession, "firstAfter")
        recordPID(secondSession, "secondAfter")
        wait { pids.count == 4 }
        precondition(pids["first"] == pids["firstAfter"] && pids["second"] == pids["secondAfter"])
        precondition(gameButton("first_fixture").press())
        wait { application.selectedGameID == "first_fixture" }
        wait { visibleSections() == ["test.sections.first_fixture"] }
        precondition(application.context(id: "first_fixture")?.typed(as: FirstFixtureGameModule.self) === firstContext)
        navigationPump(0.1)
        precondition(fields(pageWindow.contentView!).contains { $0 === draftField && $0.stringValue == "unfinished draft" },
                     "Page selection discarded a view-local input draft")
        precondition(window.contentView === document && window.isVisible)

        func sectionButton(_ game: String, _ index: Int) -> NativeAccessibilityControl {
            nativeAccessibilityControls(pageWindow).first {
                $0.identifier == "test.navigate.\(game).\(index)"
            }!
        }
        func requestCount() -> Int {
            let games = server.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("games")
            return ["first_fixture", "second_fixture"].reduce(0) { total, game in
                let url = games.appendingPathComponent(game).appendingPathComponent("navigation_requests.jsonl")
                return total + ((try? String(contentsOf: url, encoding: .utf8)) ?? "").split(separator: "\n").count
            }
        }
        let beforeNavigation = requestCount()
        let firstScroll = draftField.enclosingScrollView!
        for index in [2, 0, 1] { precondition(sectionButton("first_fixture", index).press()) }
        wait { firstContext.navigation.selection == "first_fixture.1" && firstContext.navigation.request == nil }
        navigationPump(0.3)
        let firstDestination = firstScroll.contentView.bounds.origin
        precondition(firstDestination.y > 400, "section navigation did not move the real viewport")
        let firstAnchor = nativeAccessibilityControls(pageWindow).first {
            $0.identifier == "test.destination.first_fixture.1"
        }!
        let firstViewport = pageWindow.convertToScreen(firstScroll.convert(firstScroll.bounds, to: nil))
        precondition(abs(firstAnchor.frame.maxY - firstViewport.maxY) < 4,
                     "section navigation did not align its real destination to the viewport")
        firstScroll.contentView.scroll(to: NSPoint(x: 0, y: firstDestination.y + 160))
        firstScroll.reflectScrolledClipView(firstScroll.contentView)
        precondition(sectionButton("first_fixture", 1).press())
        wait { abs(firstScroll.contentView.bounds.origin.y - firstDestination.y) < 2 }

        // Observe a real jump after motion starts, then switch away while it
        // is in flight. Settling the latest destination must happen before the
        // page is hidden; later frames cannot keep moving that hidden page.
        navigationPump(0.3)
        let switchToSecond = gameButton("second_fixture")
        let switchToFirst = gameButton("first_fixture")
        let movingAnchor = nativeAccessibilityControls(pageWindow).first {
            $0.identifier == "test.destination.first_fixture.2"
        }!
        let movingDestination = firstDestination.y + firstViewport.maxY - movingAnchor.frame.maxY
        precondition(movingDestination > firstDestination.y + 300)
        precondition(sectionButton("first_fixture", 2).press())
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            let deadline = Date(timeIntervalSinceNow: 2)
            var observedMotion = false
            while Date() < deadline {
                navigationPump(0.002)
                let offset = firstScroll.contentView.bounds.origin.y
                if offset > firstDestination.y + 2 && offset < movingDestination - 2 {
                    observedMotion = true
                    navigationTrace("in-flight origin=\(firstDestination.y) observed=\(offset) destination=\(movingDestination)")
                    break
                }
                if offset >= movingDestination - 2 { break }
            }
            precondition(observedMotion, "native fixture did not observe the jump while it was moving")
        } else {
            wait { abs(firstScroll.contentView.bounds.origin.y - movingDestination) < 2 }
        }
        navigationTrace("before switch offset=\(firstScroll.contentView.bounds.origin.y) destination=\(movingDestination)")
        precondition(switchToSecond.press())
        precondition(application.selectedGameID == "second_fixture")
        let retiredPosition = firstScroll.contentView.bounds.origin.y
        navigationTrace("after switch offset=\(retiredPosition) destination=\(movingDestination) visible=\(firstContext.navigation.isVisible)")
        precondition(abs(retiredPosition - movingDestination) < 2,
                     "switching games left an active jump between its origin and selected destination: actual=\(retiredPosition) expected=\(movingDestination)")
        for _ in 0..<15 {
            navigationPump(0.02)
            precondition(abs(firstScroll.contentView.bounds.origin.y - retiredPosition) < 2,
                         "an already-started navigation kept moving a hidden page")
        }
        precondition(switchToFirst.press())
        wait { visibleSections() == ["test.sections.first_fixture"] }
        precondition(abs(firstScroll.contentView.bounds.origin.y - retiredPosition) < 2,
                     "returning to a page replayed a retired jump")
        // A completed jump must release its finish callback: subsequent manual
        // scrolling belongs to the user and is retained through selection.
        firstScroll.contentView.scroll(to: NSPoint(x: 0, y: retiredPosition + 70))
        firstScroll.reflectScrolledClipView(firstScroll.contentView)
        let manualPosition = firstScroll.contentView.bounds.origin.y
        precondition(switchToSecond.press())
        navigationPump(0.05)
        precondition(abs(firstScroll.contentView.bounds.origin.y - manualPosition) < 2,
                     "a completed jump overrode a manual scroll on page selection")
        precondition(switchToFirst.press())
        wait { visibleSections() == ["test.sections.first_fixture"] }
        precondition(sectionButton("first_fixture", 1).press())
        wait { abs(firstScroll.contentView.bounds.origin.y - firstDestination.y) < 2 }
        navigationPump(0.3)

        // A selection on the same event turn retires the old page's pending
        // layout request. Neither a delayed callback nor returning may replay it.
        precondition(sectionButton("first_fixture", 2).press())
        precondition(gameButton("second_fixture").press())
        wait { application.selectedGameID == "second_fixture" && visibleSections() == ["test.sections.second_fixture"] }
        firstContext.navigation.navigate(to: "first_fixture.2")
        navigationPump(0.3)
        precondition(firstContext.navigation.request == nil && firstContext.navigation.selection == "first_fixture.1")
        precondition(abs(firstScroll.contentView.bounds.origin.y - firstDestination.y) < 2,
                     "a hidden page moved after navigation was cancelled")
        let secondField = fields(pageWindow.contentView!).first { $0.stringValue == "Second draft" }!
        let secondScroll = secondField.enclosingScrollView!
        precondition(firstScroll !== secondScroll && secondScroll.contentView.bounds.origin.y < 2,
                     "game selection replaced or shared a retained viewport")
        second.setEnabled(false)
        precondition(second.busy)
        precondition(sectionButton("second_fixture", 2).press())
        wait { secondContext.navigation.selection == "second_fixture.2" && !second.busy }
        navigationPump(0.3)
        let secondDestination = secondScroll.contentView.bounds.origin
        precondition(secondDestination.y > firstDestination.y + 300)
        precondition(requestCount() == beforeNavigation + 1, "navigation dispatched or replayed a backend command")

        for language in [TrainerPresentationLanguage.en, .zhCN] {
            localization.language = language
            precondition(localization.localized("host.refreshStatus") != "host.refreshStatus",
                         "navigation fixture did not load shipped Host translations")
            for width: CGFloat in [1077, 1400] {
                pageWindow.setContentSize(NSSize(width: width, height: 1000))
                for game in ["first_fixture", "second_fixture", "first_fixture"] {
                    precondition(gameButton(game).press())
                    wait { application.selectedGameID == game && visibleSections() == ["test.sections." + game] }
                    let controls = nativeAccessibilityControls(pageWindow)
                    for id in ["first_fixture", "second_fixture"] {
                        precondition(controls.filter { $0.identifier == "host.game." + id }.count == 1,
                                     "selection mounted duplicate game cards")
                    }
                    precondition(abs(firstScroll.contentView.bounds.origin.y - firstDestination.y) < 2)
                    precondition(abs(secondScroll.contentView.bounds.origin.y - secondDestination.y) < 2)
                }
            }
        }
        let keyboard = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [.command, .option],
            timestamp: 0, windowNumber: pageWindow.windowNumber, context: nil, characters: "0",
            charactersIgnoringModifiers: "0", isARepeat: false, keyCode: 29)!
        _ = pageWindow.performKeyEquivalent(with: keyboard)
        wait { firstContext.navigation.selection == "first_fixture.0" }
        precondition(secondContext.navigation.selection == "second_fixture.2", "hidden sidebar kept its keyboard action")

        window.makeKeyAndOrderFront(nil)
        precondition(window.makeFirstResponder(toolDraft))
        let toolEditor = window.firstResponder
        application.selectedGameID = "second_fixture"
        navigationPump(0.2)
        precondition(window.firstResponder === toolEditor && toolDraft.stringValue == "retained tool draft",
                     "game selection resigned an independent tool-window draft")
        application.selectedGameID = "first_fixture"
        pageWindow.makeKeyAndOrderFront(nil)
        precondition(requestCount() == beforeNavigation + 1)
        second.toggleConnectionFromHost()
        wait { !second.connected && !second.busy }
        precondition(gameButton("second_fixture").press())
        wait { application.selectedGameID == "second_fixture" }
        precondition(sectionButton("second_fixture", 0).press())
        wait { secondContext.navigation.selection == "second_fixture.0" }
        precondition(first.connected && !second.connected && firstSession.isStarted && secondSession.isStarted,
                     "disconnected navigation changed another game's connection")
        precondition(requestCount() == beforeNavigation + 2)
        first.postponeTermination = true
        var terminated: Bool?
        application.prepareForTermination { terminated = true }
        navigationPump(0.05)
        precondition(terminated == nil && firstSession.isStarted && secondSession.isStarted,
                     "Quit bypassed a tool-window write barrier")
        precondition(application.terminationRequested && !firstContext.toolWindows.interactionEnabled)
        mayClose = true
        first.refreshFromHost()
        wait { first.pendingTermination != nil && !second.busy }
        second.setEnabled(false)
        precondition(second.busy)
        first.finishPostponedTermination()
        precondition(terminated == nil && secondSession.isStarted,
                     "Later context's newly busy operation was interrupted")
        wait { terminated == true && !firstSession.isStarted && !secondSession.isStarted }
        precondition(closes == 1)
        pageWindow.close()

        // The native owner waits for a newly mounted destination and resolves
        // its current geometry, including a shorter document's legal end.
        let geometryState = NavigationGeometryState()
        let geometryNavigation = TrainerSectionNavigation()
        geometryNavigation.navigate(to: "late")
        let geometryWindow = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 340, height: 240),
                                      styleMask: [.titled], backing: .buffered, defer: false)
        geometryWindow.isReleasedWhenClosed = false
        geometryWindow.contentViewController = NSHostingController(rootView:
            NavigationGeometryFixture(state: geometryState, navigation: geometryNavigation)
                .frame(width: 340, height: 240).trainerTheme(.standard))
        geometryWindow.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        wait { NSApp.isActive && geometryWindow.isKeyWindow }
        navigationPump(0.04)
        precondition(geometryNavigation.request != nil && geometryNavigation.selection == nil,
                     "navigation dropped a target before its first native layout")
        func scrollViews(_ view: NSView) -> [NSScrollView] {
            (view as? NSScrollView).map { [$0] } ?? view.subviews.flatMap(scrollViews)
        }
        let geometryScroll = scrollViews(geometryWindow.contentView!).first!
        wait { geometryScroll.bounds.width > 0 && geometryScroll.bounds.height > 0
            && geometryScroll.contentView.bounds.width > 0 && geometryScroll.contentView.bounds.height > 0 }
        let cancelledWaitingPosition = geometryScroll.contentView.bounds.origin
        navigationClick(in: geometryScroll)
        precondition(geometryNavigation.request == nil && geometryNavigation.selection == nil,
                     "native input did not retire a navigation still waiting for layout")
        geometryState.showTarget = true
        navigationPump(0.05)
        precondition(geometryNavigation.request == nil && geometryNavigation.selection == nil
                     && geometryScroll.contentView.bounds.origin == cancelledWaitingPosition,
                     "a later target layout replayed the navigation cancelled by native input")
        geometryNavigation.navigate(to: "late")
        wait { geometryNavigation.request == nil && geometryNavigation.selection == "late" }
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            wait { geometryScroll.contentView.bounds.origin.y > 2 }
        }
        geometryState.prefixHeight = 1_100
        geometryState.tailHeight = 30
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { geometryNavigation.navigate(to: "late") }
        navigationPump(0.3)
        let clip = geometryScroll.contentView
        let clampedEnd = clip.constrainBoundsRect(NSRect(x: 0, y: 100_000,
                                                         width: clip.bounds.width, height: clip.bounds.height)).origin.y
        precondition(abs(clip.bounds.origin.y - clampedEnd) < 2,
                     "a changing document left navigation beyond its current clamped destination")

        // A real pointer click takes ownership from an active jump. Its old
        // animation may neither continue afterwards nor finish on page hide.
        geometryState.prefixHeight = 1_800
        geometryState.tailHeight = 900
        navigationPump(0.04)
        let pointerOrigin = clip.bounds.origin.y
        geometryNavigation.navigate(to: "late")
        wait { geometryNavigation.request == nil }
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            wait { clip.bounds.origin.y > pointerOrigin + 2 }
        }
        navigationClick(in: geometryScroll)
        let pointerPosition = clip.bounds.origin.y
        navigationPump(0.3)
        precondition(abs(clip.bounds.origin.y - pointerPosition) < 2,
                     "a cancelled navigation continued after native pointer input")
        geometryNavigation.setVisible(false)
        precondition(abs(clip.bounds.origin.y - pointerPosition) < 2,
                     "hiding a page completed a jump already cancelled by its user")
        geometryWindow.close()

        // Exercise the production policy-update entry point on an actual
        // AppKit viewport without changing the user's accessibility setting.
        let policyOwner = TrainerSectionScroll()
        let policyNavigation = TrainerSectionNavigation()
        let policyScroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 340, height: 240))
        let policyDocument = NavigationPolicyDocument(frame: NSRect(x: 0, y: 0, width: 320, height: 1_800))
        let policyTarget = NSView(frame: NSRect(x: 0, y: 900, width: 320, height: 40))
        policyDocument.addSubview(policyTarget)
        policyScroll.documentView = policyDocument
        let policyWindow = NSWindow(contentRect: policyScroll.frame, styleMask: [.titled], backing: .buffered, defer: false)
        policyWindow.isReleasedWhenClosed = false
        policyWindow.contentView = policyScroll
        policyWindow.makeKeyAndOrderFront(nil)
        navigationPump(0.03)
        policyScroll.contentView.scroll(to: .zero)
        policyNavigation.navigate(to: "policy")
        policyOwner.scroll(policyNavigation.request!, navigation: policyNavigation)
        precondition(policyNavigation.request != nil, "an unregistered policy target was consumed")
        policyOwner.setReduceMotion(true)
        policyOwner.register(policyTarget, id: "policy")
        wait { policyNavigation.request == nil }
        precondition(abs(policyScroll.contentView.bounds.origin.y - 900) < 2,
                     "late target used the Reduce Motion policy captured by its old request")

        policyTarget.setFrameOrigin(NSPoint(x: 0, y: 1_200))
        policyOwner.setReduceMotion(false)
        policyNavigation.navigate(to: "policy")
        policyOwner.scroll(policyNavigation.request!, navigation: policyNavigation)
        let policyDeadline = Date().addingTimeInterval(2)
        var policyMotionObserved = false
        while Date() < policyDeadline {
            navigationPump(0.002)
            let offset = policyScroll.contentView.bounds.origin.y
            if offset > 902 && offset < 1_198 { policyMotionObserved = true; break }
            if offset >= 1_198 { break }
        }
        precondition(policyMotionObserved, "policy fixture did not observe actual in-flight native movement")
        policyOwner.setReduceMotion(true)
        precondition(abs(policyScroll.contentView.bounds.origin.y - 1_200) < 2,
                     "enabling Reduce Motion did not immediately finish the active native jump")
        navigationPump(0.3)
        precondition(abs(policyScroll.contentView.bounds.origin.y - 1_200) < 2,
                     "a retired animation moved the viewport after Reduce Motion changed")
        policyOwner.cancel()
        policyWindow.close()
        print("multi_game_contexts_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-multi-context-") as directory:
    project = Path(directory)
    shutil.copytree(ROOT / "Backend/core", project / "Backend/core")
    shutil.copytree(ROOT / "Sources/Core", project / "Sources/Core")
    shutil.copytree(ROOT / "Tools", project / "Tools")
    shutil.copy2(ROOT / "Info.plist", project / "Info.plist")
    for language in ("en", "zh-CN"):
        localized = project / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(ROOT / "Resources/Localization" / f"{language}.lproj/Host.strings",
                     localized / "Host.strings")
    modules = []
    frontends = []
    for word, name in (("First", "first_fixture"), ("Second", "second_fixture")):
        destination = project / "Backend/games" / name
        shutil.copytree(FIXTURE / "backend", destination)
        adapter = destination / "adapter.py"
        adapter.write_text("import os, time, json\nfrom pathlib import Path\n" + adapter.read_text().replace(
            "    def dispatch(self, command, params, request_id):",
            "    def dispatch(self, command, params, request_id):\n"
            "        with Path(__file__).with_name('navigation_requests.jsonl').open('a') as log:\n"
            "            log.write(json.dumps({'command': command, 'params': params}) + '\\n')").replace(
            "'enabled': self.enabled}", "'enabled': self.enabled, 'pid': os.getpid()}").replace(
            "if command == 'set_enabled':", "if command == 'set_enabled':\n            time.sleep(0.3)"))
        manifest = json.loads((destination / "module.json").read_text())
        manifest["id"] = name
        manifest["displayName"] = word + " Fixture"
        manifest["backend"]["adapter"] = f"games.{name}.adapter:ReferenceFixtureAdapter"
        manifest["frontend"]["sourceDirectory"] = f"Sources/{word}Fixture"
        manifest["frontend"]["moduleType"] = word + "FixtureGameModule"
        manifest["targetApplication"]["processName"] = word + "InertTarget"
        manifest["targetApplication"]["bundleIdentifier"] = "test." + name
        manifest.pop("app", None)
        (destination / "module.json").write_text(json.dumps(manifest))
        source = project / manifest["frontend"]["sourceDirectory"] / (word + "Module.swift")
        source.parent.mkdir(parents=True)
        source.write_text((FIXTURE / "frontend/ReferenceFixtureModule.swift").read_text().replace(
            "ReferenceFixture", word + "Fixture").replace(
            f"static func makeSidebarActions(model: {word}FixtureModel) -> some View {{\n        EmptyView()",
            f'static func makeSidebarActions(model: {word}FixtureModel) -> some View {{\n'
            f'        NavigationFixtureSidebar(gameID: "{name}", name: "{word}")').replace(
            "    func prepareForTermination(completion: @escaping () -> Void) {",
            "    @Published var postponeTermination = false\n    var pendingTermination: (() -> Void)?\n"
            "    func finishPostponedTermination() {\n        backendSession.stop()\n        let done = pendingTermination\n"
            "        pendingTermination = nil\n        done?()\n    }\n"
            "    func prepareForTermination(completion: @escaping () -> Void) {\n"
            "        if postponeTermination { pendingTermination = completion; return }").replace(
            "    func setEnabled(_ value: Bool)",
            "    @Published var activations = 0\n    func hostDidBecomeActive() { activations += 1 }\n    func setEnabled(_ value: Bool)").replace(
            "    @ObservedObject var model:",
            '    @State private var draft = "' + word + ' draft"\n    @ObservedObject var model:').replace(
            "        VStack(alignment: .leading, spacing: 12) {",
            '        VStack(alignment: .leading, spacing: 12) {\n            TextField("Draft", text: $draft)\n'
            f'            NavigationFixtureSections(gameID: "{name}")'))
        frontends.append(source)
        modules.append(name)
    generated = project / "Generated.swift"
    subprocess.run([sys.executable, str(project / "Tools/generate_game_binding.py"),
                    ",".join(modules), str(generated)], check=True, cwd=project)
    main = project / "Harness.swift"
    main.write_text(HARNESS)
    binary = project / "test"
    subprocess.run(["swiftc", "-parse-as-library", *map(str, sorted((project / "Sources/Core").rglob("*.swift"))),
                    *map(str, frontends), str(ROOT / "tests/fixtures/swift/NativeAccessibility.swift"),
                    str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
                    str(generated), str(main), "-o", str(binary)], check=True)
    env = {**os.environ, "HOME": str(project / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
    Path(env["HOME"]).mkdir()
    subprocess.run([str(binary), str(project / "Backend/core/server.py"), sys.executable],
                   cwd=project, env=env, check=True, timeout=90)

# Keep the reference-module isolation gate above, then exercise the shipped
# Hades/Hades II adapters together in a separate bounded native process.
run_real_module_navigation(ROOT)
