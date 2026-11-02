"""Native workbench search journeys used by both actual module header adapters."""

SEARCH_JOURNEY = r'''
private struct SearchPageFixture<Content: View>: View {
    let content: Content
    let visibility: TrainerGamePageVisibility
    var body: some View {
        VStack(spacing: 16) {
            content
            Text("Search workbench anchor").frame(maxWidth: .infinity, minHeight: 120)
                .accessibilityIdentifier("fixture.search.workbench")
        }
        .padding(12)
        .environment(\.trainerGamePageVisibility, visibility)
    }
}

func searchJourneyCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("workbench search journey: " + message) }
}

@MainActor
func searchJourneyPump(_ duration: TimeInterval = 0.05) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
func searchJourneyWait(_ expectation: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(3)
    repeat {
        if condition() { return }
        searchJourneyPump(0.02)
    } while Date() < deadline
    fatalError("workbench search timed out: " + expectation)
}

func searchJourneyFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(searchJourneyFields)
}

func searchJourneyScrollView(_ view: NSView) -> NSScrollView? {
    if let scroll = view as? NSScrollView { return scroll }
    for child in view.subviews {
        if let scroll = searchJourneyScrollView(child) { return scroll }
    }
    return nil
}

/// Public AX actions can submit without any NSEvent. Resolve the exposed
/// SwiftUI text node rather than its ignored AppKit backing NSTextField.
@MainActor
private func searchJourneyQueryConfirmation(
    _ host: NSView, window: NSWindow, field: NSTextField, placeholder: String, query: String
) -> (route: String, perform: () -> Void) {
    func value(_ object: NSObject, _ name: String) -> Any? {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector) else { return nil }
        return object.perform(selector)?.takeUnretainedValue()
    }
    func boolean(_ object: NSObject, _ name: String) -> Bool? {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector) else { return nil }
        typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
        return unsafeBitCast(object.method(for: selector), to: Getter.self)(object, selector)
    }
    func allows(_ object: NSObject, _ action: Selector) -> Bool? {
        let selector = NSSelectorFromString("isAccessibilitySelectorAllowed:")
        guard object.responds(to: selector) else { return nil }
        typealias Getter = @convention(c) (AnyObject, Selector, Selector) -> Bool
        return unsafeBitCast(object.method(for: selector), to: Getter.self)(object, selector, action)
    }
    let frame = window.convertToScreen(field.convert(field.bounds, to: nil))
    let center = NSPoint(x: frame.midX, y: frame.midY)
    let candidates = nativeAccessibilityControls(host).filter { node in
        let named = node.label == placeholder
            || value(node.object, "accessibilityPlaceholderValue") as? String == placeholder
        return node.role == "AXTextField" && named && node.valueText == query && node.frame.contains(center)
    }
    searchJourneyCheck(field.window === window && candidates.count == 1,
                       "public AX query node did not uniquely match its owner, name, value and frame")
    let object = candidates[0].object
    searchJourneyCheck(boolean(object, "isAccessibilityElement") == true,
                       "query confirmation addressed an ignored backing field")
    let rawActions = value(object, "accessibilityActionNames") as? [Any] ?? []
    let actions = rawActions.compactMap { item -> String? in
        (item as? String) ?? (item as? NSAccessibility.Action)?.rawValue
    }
    searchJourneyCheck(actions.contains("AXConfirm"),
                       "exposed query does not advertise AXConfirm; composition continuation is unverified")
    let legacy = NSSelectorFromString("accessibilityPerformAction:")
    if object.responds(to: legacy), allows(object, legacy) != false {
        return ("AXConfirm", {
            typealias Action = @convention(c) (AnyObject, Selector, NSString) -> Void
            unsafeBitCast(object.method(for: legacy), to: Action.self)(object, legacy, "AXConfirm" as NSString)
        })
    }
    let modern = NSSelectorFromString("accessibilityPerformConfirm")
    searchJourneyCheck(object.responds(to: modern) && allows(object, modern) == true,
                       "advertised AXConfirm has no allowed public action route")
    return ("accessibilityPerformConfirm", { _ = boolean(object, "accessibilityPerformConfirm") })
}

@MainActor
private final class SearchJourneyInputAudit {
    var expectedEvent: NSEvent?
    private var expectedCount = 0
    private var otherCount = 0
    private var monitor: Any?

    init() {
        monitor = NSEvent.addLocalMonitorForEvents(
            matching: [.keyDown, .leftMouseDown, .rightMouseDown, .otherMouseDown]
        ) { [weak self] event in
            MainActor.assumeIsolated {
                if let self {
                    if event === self.expectedEvent { self.expectedCount += 1 }
                    else { self.otherCount += 1 }
                }
                return event
            }
        }
    }

    func check(_ phase: String) {
        searchJourneyCheck(expectedCount == (expectedEvent == nil ? 0 : 1) && otherCount == 0,
                           "unexpected native input during \(phase): expected=\(expectedCount), other=\(otherCount)")
    }

    func stop() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
    }
}

/// Header content, catalog resolution and query ownership come from the real
/// game module; only the backend worker is synthetic. Every event uses AppKit.
@MainActor
func exerciseWorkbenchSearch<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore,
    placeholder: () -> String, emptyLabel: () -> String, query: () -> String,
    matches: (String) -> [(id: String, destination: String)], commands: () -> [[String: Any]]
) {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    NSApp.activate(ignoringOtherApps: true)
    let oldLanguage = localization.language
    defer { localization.language = oldLanguage }
    let before = commands().count
    let cases: [(CGFloat, TrainerPresentationLanguage)] = [(300, .en), (540, .zhCN)]
    var clearLabels: [String] = []
    for (width, language) in cases {
        localization.language = language
        let clearLabel = localization.localized("host.search.clear")
        searchJourneyCheck(clearLabel != "host.search.clear", "search fixture did not load the shipped Host translations")
        clearLabels.append(clearLabel)
        let visibility = TrainerGamePageVisibility()
        var destinations: [String] = []
        let host = NSHostingView(rootView: SearchPageFixture(content: content, visibility: visibility)
            .environmentObject(localization)
            .environment(\.trainerNavigateToSection, { destinations.append($0) }))
        let window = NSWindow(contentRect: NSRect(x: 200, y: 500, width: width, height: 220),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        searchJourneyPump(0.2)
        func field() -> NSTextField {
            host.layoutSubtreeIfNeeded()
            guard let field = searchJourneyFields(host).first(where: { $0.placeholderString == placeholder() }) else {
                fatalError("workbench search journey: actual module search field is missing")
            }
            return field
        }
        func resultControls(_ window: NSWindow) -> [NativeAccessibilityControl] {
            guard let root = window.contentView else { return [] }
            return nativeAccessibilityControls(root).filter {
                $0.role == "AXButton" && $0.identifier?.hasPrefix("trainer.workbench.result.") == true
            }
        }
        func popover() -> NSWindow? {
            NSApp.windows.first { candidate in
                guard candidate !== window, candidate.isVisible, let root = candidate.contentView else { return false }
                return !resultControls(candidate).isEmpty
                    || nativeAccessibilityControls(root).contains { $0.text == emptyLabel() }
            }
        }
        func enter(_ value: String) {
            window.makeKeyAndOrderFront(nil)
            searchJourneyCheck(window.makeFirstResponder(field()), "native search field refused focus")
            guard let editor = field().currentEditor() as? NSTextView else {
                fatalError("workbench search journey: native search editor is missing")
            }
            editor.selectAll(nil)
            editor.insertText(value, replacementRange: editor.selectedRange())
            searchJourneyPump()
            searchJourneyCheck(query() == value, "native typing did not update the module query immediately")
        }
        func key(_ code: UInt16, _ characters: String) {
            let target = NSApp.keyWindow ?? window
            let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: target.windowNumber,
                context: nil, characters: characters, charactersIgnoringModifiers: characters,
                isARepeat: false, keyCode: code)!
            NSApp.sendEvent(event)
            searchJourneyPump()
        }
        func anchor() -> NSRect {
            nativeAccessibilityControls(host).first { $0.identifier == "fixture.search.workbench" }!.frame
        }
        let originalAnchor = anchor()
        // Both games present the official English term as Life.
        // Use that visible label, not an internal health field name.
        let keyboardQuery = "life"
        let expected = matches(keyboardQuery)
        searchJourneyCheck(expected.count >= 2 && expected[0].destination != expected[1].destination,
                           "native keyboard fixture needs distinct ordered destinations")
        enter(keyboardQuery)
        searchJourneyWait("ordered module results") { popover().map { resultControls($0).count == expected.count } == true }
        let panel = popover()!
        let originalFrame = panel.frame
        searchJourneyCheck(resultControls(panel).map(\.identifier) == expected.map { "trainer.workbench.result." + $0.id },
                           "native discovery changed the module's result order")
        searchJourneyCheck(anchor() == originalAnchor, "opening search displaced the workbench")
        let inputFrame = window.convertToScreen(field().convert(field().bounds, to: nil))
        searchJourneyCheck(!panel.frame.intersects(inputFrame), "results cover the typed query")
        guard let scroll = searchJourneyScrollView(panel.contentView!) else {
            fatalError("workbench search journey: native results viewport is missing")
        }
        let viewport = panel.convertToScreen(scroll.contentView.convert(scroll.contentView.bounds, to: nil))
        let hostFrame = window.convertToScreen(host.convert(host.bounds, to: nil))
        // AppKit's outer popover frame includes its arrow and decoration. The
        // authored viewport, actual rows and visible labels must fit, without
        // guessing system chrome insets or accepting clipped native controls.
        searchJourneyCheck(viewport.width > 0 && viewport.minX >= hostFrame.minX - 1
                           && viewport.maxX <= hostFrame.maxX + 1,
                           "results content overflows the narrow host: \(viewport) in \(hostFrame)")
        let resultContent = nativeAccessibilityControls(panel.contentView!).filter {
            ($0.role == "AXButton" || $0.role == "AXStaticText") && $0.frame.width > 0
        }
        searchJourneyCheck(!resultContent.isEmpty && resultContent.allSatisfy {
            viewport.insetBy(dx: -1, dy: -1).contains($0.frame)
        }, "a native search row or label is clipped by the results viewport")
        // Continue typing through the actual key window after opening. A
        // popover that steals the field editor cannot pass by setting a binding.
        key(49, " ")
        searchJourneyCheck(query() == keyboardQuery + " " && destinations.isEmpty, "opening results stole native typing focus")
        key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!))
        key(36, "\r")
        searchJourneyWait("Return navigates the arrow-selected result") { destinations == [expected[1].destination] && popover() == nil }

        // A retained Hades I query reopens by Arrow; Hades II's adapter clears
        // its query after navigation and accepts the same query again.
        if query().isEmpty { enter(keyboardQuery) }
        else {
            window.makeKeyAndOrderFront(nil)
            searchJourneyCheck(window.makeFirstResponder(field()), "retained query refused focus")
            key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!))
        }
        searchJourneyWait("repeated query reopens") { popover() != nil }
        key(53, "\u{1b}")
        searchJourneyWait("Escape closes and returns editing focus") {
            popover() == nil && field().currentEditor() != nil && NSApp.keyWindow === window
        }
        searchJourneyCheck(!query().isEmpty && destinations.count == 1, "Escape cleared the query or navigated")
        enter(keyboardQuery)
        // If this is the identical retained input, Arrow explicitly reopens.
        if popover() == nil { key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!)) }
        searchJourneyWait("result before empty update") { popover() != nil }
        let staleRow = resultControls(popover()!).first!
        let samePanel = popover()!
        enter("no-fixture-result-628")
        searchJourneyWait("empty discovery state") {
            popover() === samePanel && resultControls(samePanel).isEmpty
        }
        searchJourneyCheck(samePanel.frame.size == originalFrame.size && anchor() == originalAnchor,
                           "query updates resized the results viewport or moved the workbench")
        _ = staleRow.press()
        searchJourneyPump()
        searchJourneyCheck(destinations.count == 1 && popover() === samePanel,
                           "a stale row navigated or dismissed the current query")
        let clear = nativeAccessibilityControls(host).first { $0.identifier == "trainer.search.clear" }!
        searchJourneyCheck(clear.label == clearLabel, "native search clear action did not resolve the current language")
        searchJourneyCheck(clear.press(), "native clear action refused Press")
        searchJourneyWait("clear keeps editing focus and dismisses") {
            query().isEmpty && popover() == nil && field().currentEditor() != nil
        }

        // Exercise the real text-input client's composition state without
        // changing the user's system input method or simulating candidate UI.
        enter(keyboardQuery)
        searchJourneyWait("results before native marked input") { popover() != nil }
        guard let compositionEditor = field().currentEditor() as? NSTextView else {
            fatalError("workbench search journey: marked input lost its native editor")
        }
        let beforeComposition = destinations
        func markQuery(in editor: NSTextView) {
            editor.selectAll(nil)
            editor.setMarkedText(keyboardQuery,
                selectedRange: NSRange(location: keyboardQuery.utf16.count, length: 0),
                replacementRange: editor.selectedRange())
            searchJourneyPump()
            searchJourneyCheck(editor.hasMarkedText() && field().currentEditor() === editor,
                               "native marked input was ended or moved to the results")
        }
        markQuery(in: compositionEditor)
        key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!))
        searchJourneyCheck(destinations == beforeComposition && field().currentEditor() === compositionEditor,
                           "composition Arrow navigated or resigned the native query editor")
        compositionEditor.unmarkText()
        searchJourneyPump()
        searchJourneyCheck(!compositionEditor.hasMarkedText(), "native composition did not finish")
        // Return without another Arrow proves the marked Arrow did not even
        // change selection; clamping a two-result list cannot hide that defect.
        key(36, "\r")
        searchJourneyWait("composition Arrow retained the first result") {
            destinations == beforeComposition + [expected[0].destination] && popover() == nil
        }
        enter("")
        enter(keyboardQuery)
        searchJourneyWait("fresh results before composition Return") { popover() != nil }
        guard let returnEditor = field().currentEditor() as? NSTextView else {
            fatalError("workbench search journey: composition Return lost its native editor")
        }
        let beforeReturn = destinations
        markQuery(in: returnEditor)
        key(36, "\r")
        searchJourneyCheck(destinations == beforeReturn && field().currentEditor() === returnEditor,
                           "composition Return navigated or resigned the native query editor")
        returnEditor.unmarkText()
        searchJourneyPump()
        searchJourneyCheck(!returnEditor.hasMarkedText(), "native Return composition did not finish")
        key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!))
        key(36, "\r")
        searchJourneyWait("keyboard selection resumes after native composition") {
            destinations == beforeReturn + [expected[1].destination] && popover() == nil
        }

        enter("生命")
        let bilingual = matches("生命")
        searchJourneyCheck(!bilingual.isEmpty, "actual module lacks the bilingual health alias")
        searchJourneyWait("Chinese aliases in either presentation language") {
            popover().map { resultControls($0).map(\.identifier) == bilingual.map { "trainer.workbench.result." + $0.id } } == true
        }
        let oldPageRow = resultControls(popover()!).first!
        visibility.setVisible(false)
        searchJourneyWait("page switch dismisses results") { popover() == nil }
        _ = oldPageRow.press()
        searchJourneyPump()
        searchJourneyCheck(destinations.count == 3 && query() == "生命", "hidden page routed a stale result or erased its query")
        visibility.setVisible(true)
        searchJourneyPump()
        searchJourneyCheck(popover() == nil, "returning to a page reopened stale results")
        window.makeKeyAndOrderFront(nil)
        searchJourneyCheck(window.makeFirstResponder(field()), "returning page refused search focus")
        key(125, String(UnicodeScalar(NSDownArrowFunctionKey)!))
        searchJourneyWait("explicit keyboard reopen after page switch") { popover() != nil }
        searchJourneyCheck(resultControls(popover()!).first!.press(), "native result click refused Press")
        searchJourneyWait("mouse selection navigates current module") {
            destinations == [expected[1].destination, expected[0].destination, expected[1].destination,
                             bilingual[0].destination] && popover() == nil
        }
        searchJourneyCheck(commands().count == before, "search, keyboard or click dispatched a trainer command")
        if language == .zhCN {
            // Keep the original two-language keyboard/AX journey above intact.
            // This pair proves Confirm works ordinarily, then remains a new
            // action after composing input without another key or mouse event.
            NSApp.activate(ignoringOtherApps: true)
            window.makeKeyAndOrderFront(nil)
            searchJourneyWait("active key query owner before AX composition continuation") {
                NSApp.isActive && window.isKeyWindow
            }
            enter("")
            enter(keyboardQuery)
            searchJourneyWait("ordinary results before AX Confirm") { popover() != nil }
            let queryField = field()
            let ordinaryBefore = destinations
            let confirmationRoute: String
            do {
                let audit = SearchJourneyInputAudit()
                defer { audit.stop() }
                let confirmation = searchJourneyQueryConfirmation(host, window: window, field: queryField,
                    placeholder: placeholder(), query: query())
                confirmationRoute = confirmation.route
                confirmation.perform()
                searchJourneyPump()
                audit.check("ordinary AX Confirm")
            }
            searchJourneyCheck(destinations == ordinaryBefore + [expected[0].destination],
                               "ordinary public AX Confirm did not navigate exactly once")

            let composingInputs: [(String, UInt16, String)] = [
                ("Return", 36, "\r"),
                ("selection Arrow", 125, String(UnicodeScalar(NSDownArrowFunctionKey)!)),
                ("caret Arrow", 123, String(UnicodeScalar(NSLeftArrowFunctionKey)!)),
            ]
            for (kind, code, characters) in composingInputs {
                enter("")
                enter(keyboardQuery)
                searchJourneyWait("results before composing \(kind) and AX Confirm") { popover() != nil }
                searchJourneyCheck(NSApp.isActive && window.isKeyWindow && field() === queryField,
                                   "AX continuation lost its active original query owner")
                guard let editor = queryField.currentEditor() as? NSTextView else {
                    fatalError("workbench search journey: AX continuation lost its native editor")
                }
                let prior = destinations
                do {
                    let audit = SearchJourneyInputAudit()
                    defer { audit.stop() }
                    markQuery(in: editor)
                    let target = NSApp.keyWindow ?? window
                    let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [],
                        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: target.windowNumber,
                        context: nil, characters: characters, charactersIgnoringModifiers: characters,
                        isARepeat: false, keyCode: code)!
                    audit.expectedEvent = event
                    NSApp.sendEvent(event)
                    searchJourneyPump()
                    searchJourneyCheck(destinations == prior && queryField.currentEditor() === editor,
                                       "composing \(kind) navigated or resigned the native query editor")
                    editor.unmarkText()
                    searchJourneyPump()
                    searchJourneyCheck(!editor.hasMarkedText() && queryField.currentEditor() === editor
                                       && query() == keyboardQuery && NSApp.isActive && window.isKeyWindow,
                                       "composing \(kind) did not leave the same active, completed query")
                    let confirmation = searchJourneyQueryConfirmation(host, window: window, field: queryField,
                        placeholder: placeholder(), query: query())
                    searchJourneyCheck(confirmation.route == confirmationRoute, "query changed its public AX Confirm route")
                    confirmation.perform()
                    searchJourneyPump()
                    audit.check("composing \(kind) followed by AX Confirm")
                }
                searchJourneyCheck(destinations == prior + [expected[0].destination],
                                   "AX Confirm after composing \(kind) did not navigate exactly once to the first result")
            }
            searchJourneyCheck(commands().count == before, "AX composition continuation dispatched a trainer command")
            print("workbench_search_ax_confirm_composition_ok")
        }
        window.contentView = nil
        window.close()
        searchJourneyPump()
    }
    searchJourneyCheck(Set(clearLabels).count == 2, "search languages did not resolve to distinct clear labels")
    print("workbench_search_native_focus_navigation_ok")
}
'''
