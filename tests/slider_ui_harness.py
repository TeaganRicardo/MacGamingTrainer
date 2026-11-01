"""Actual module-view slider journeys shared by the existing frontend owners."""

SLIDER_JOURNEY = r'''
private struct SliderPageFixture<Content: View>: View {
    let content: Content
    let visibility: TrainerGamePageVisibility
    var body: some View { content.environment(\.trainerGamePageVisibility, visibility) }
}

func sliderJourneyCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("module slider journey: " + message) }
}

@MainActor
func sliderJourneyPump(_ duration: TimeInterval) {
    // A Foundation-only run loop does not dispatch AppKit's activation/window
    // events; native gestures then never start even when hit geometry is valid.
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
func sliderJourneyWait(_ host: NSView, _ expectation: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    repeat {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        sliderJourneyPump(0.02)
    } while Date() < deadline
    fatalError("module slider journey timed out: " + expectation)
}

func sliderJourneyFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(sliderJourneyFields)
}

/// The content is a real game workbench, with its real native number field,
/// model and API. Only the backend process is synthetic and records requests.
@MainActor
func exerciseModuleSlider<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore,
    sliderLabel: String, fieldLabel: String, gameID: String, mutation: String,
    currentValue: () -> Double, busy: () -> Bool, commands: () -> [[String: Any]],
    observe: (Double) throws -> Void
) rethrows {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    NSApp.activate(ignoringOtherApps: true)
    let visibility = TrainerGamePageVisibility()
    let host = NSHostingView(rootView: SliderPageFixture(content: content, visibility: visibility)
        .environmentObject(localization))
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1150, height: 2400),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    sliderJourneyPump(0.3)
    defer { window.contentView = nil; window.close() }
    func slider() -> NativeAccessibilityControl? {
        namedNativeControl(host, role: "AXSlider", name: sliderLabel)
    }
    func field() -> NSTextField? {
        sliderJourneyFields(host).first { $0.accessibilityLabel() == fieldLabel }
    }
    func mutations() -> [[String: Any]] {
        commands().filter {
            ($0["command"] as? String) == mutation
                && (($0["params"] as? [String: Any])?["feature"] as? String) == "gameSpeed"
        }
    }
    func value(_ text: String) -> Bool { field()?.stringValue == text }
    func mouse(_ type: NSEvent.EventType, position: Double) {
        let bounds = window.convertFromScreen(slider()!.frame)
        sliderJourneyCheck(bounds.width > 20 && bounds.height > 0, "missing native slider geometry")
        let point = NSPoint(x: bounds.minX + 10 + (bounds.width - 20) * position, y: bounds.midY)
        let event = NSEvent.mouseEvent(with: type, location: point, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 0, clickCount: 1, pressure: type == .leftMouseUp ? 0 : 1)!
        NSApp.sendEvent(event)
        sliderJourneyPump(0.06)
    }
    sliderJourneyWait(host, "real speed field and enabled slider") {
        slider()?.enabled == true && field()?.isEnabled == true && value("1.0") && !busy()
    }
    // Rendering and backend readiness can precede AppKit's activation event.
    // A first click delivered before that only activates the native window.
    sliderJourneyWait(host, "active native module window") {
        NSApp.isActive && window.isKeyWindow
    }
    let before = mutations().count
    let receivedBefore = commands().count
    mouse(.leftMouseDown, position: 0.75)
    sliderJourneyWait(host, "live numeric preview") { value("2.0") }
    sliderJourneyCheck(commands().count == receivedBefore && mutations().count == before
                       && abs(currentValue() - 1) < 0.000001,
                       "preview mutated the model or dispatched a command")
    mouse(.leftMouseUp, position: 0.75)
    sliderJourneyWait(host, "one acknowledged slider commit") {
        mutations().count == before + 1 && !busy() && abs(currentValue() - 2) < 0.000001 && value("2.0")
    }
    sliderJourneyCheck(commands().count == receivedBefore + 1, "slider sent extra backend traffic")
    let request = mutations().last!
    sliderJourneyCheck(request["fixtureGame"] as? String == gameID
        && ((request["params"] as? [String: Any])?["value"] as? NSNumber)?.doubleValue == 2,
        "slider commit crossed its module or changed its numeric payload")

    // The real module must retain an active preview while observations arrive,
    // then clear it when its page is hidden without releasing a stale command.
    mouse(.leftMouseDown, position: 0.75)
    mouse(.leftMouseDragged, position: 0.25)
    sliderJourneyWait(host, "drag readout") { value("0.5") }
    try observe(3)
    sliderJourneyWait(host, "new model observation under active preview") {
        !busy() && abs(currentValue() - 3) < 0.000001
    }
    sliderJourneyCheck(value("0.5") && mutations().count == before + 1,
                       "observation overwrote the preview or dispatched a mutation")
    visibility.setVisible(false)
    sliderJourneyWait(host, "hidden-page cancellation restores latest observation") {
        slider()?.enabled == false && value("3.0")
    }
    mouse(.leftMouseUp, position: 0.25)
    visibility.setVisible(true)
    sliderJourneyWait(host, "return to retained game page") { slider()?.enabled == true && value("3.0") }
    sliderJourneyCheck(mutations().count == before + 1 && commands().count == receivedBefore + 2,
                       "hidden or returning page committed a cancelled pointer")

    // A no-op edit must release the preview so subsequent observations reach
    // the actual native field. This catches stale preview in each adapter.
    let mapping = TrainerSliderMapping.anchoredLogarithmic(values: [0.1, 0.5, 1, 2, 5], step: 0.1)
    let same = mapping.position(for: currentValue())
    mouse(.leftMouseDown, position: same)
    mouse(.leftMouseUp, position: same)
    try observe(1.4)
    sliderJourneyWait(host, "observation after unchanged click") { !busy() && value("1.4") }
    sliderJourneyCheck(mutations().count == before + 1, "unchanged click emitted a mutation")

    let numberField = field()!
    sliderJourneyCheck(window.makeFirstResponder(numberField), "could not focus real speed field")
    guard let editor = numberField.currentEditor() as? NSTextView else {
        fatalError("module slider journey: missing native field editor")
    }
    editor.selectAll(nil)
    editor.insertText("1.7", replacementRange: editor.selectedRange())
    sliderJourneyCheck(window.makeFirstResponder(nil), "native speed field refused commit")
    sliderJourneyWait(host, "one numeric-field commit through the same adapter") {
        mutations().count == before + 2 && !busy() && value("1.7") && abs(currentValue() - 1.7) < 0.000001
    }
    sliderJourneyCheck(commands().count == receivedBefore + 4,
                       "numeric completion or observation emitted extra backend traffic")
    sliderJourneyCheck(mutations().allSatisfy { $0["fixtureGame"] as? String == gameID },
                       "real module speed requests escaped their original game")
    print(gameID + "_slider_module_journey_ok")
}
'''
