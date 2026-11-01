"""Shared native-control journeys included by both existing macOS frontend tests."""

MANAGEMENT_JOURNEY = r'''
@MainActor
func exerciseManagementRouting(localization: TrainerLocalizationStore) {
    exerciseSharedControlMotion(localization: localization)
    var available = ["first": true, "second": true]
    var events: [String] = []
    @MainActor func catalog(_ owner: String) -> TrainerManagementCatalog {
        @MainActor func common(_ kind: TrainerManagementAction.Common) -> TrainerManagementAction {
            .init(kind, localization: localization, enabled: { available[owner] == true }) {
                events.append(owner + ":" + kind.rawValue)
            }
        }
        func custom(_ id: String) -> TrainerManagementAction {
            .init(id: id, title: id, icon: "gearshape", enabled: { available[owner] == true }) {
                events.append(owner + ":" + id)
            }
        }
        return .init(titles: .init(daily: "Daily", settings: "Settings", maintenance: "Maintenance"),
            refresh: common(.refreshStatus), disableAll: common(.disableAll), profiles: custom("profiles"),
            shortcuts: common(.shortcuts), log: common(.log), diagnostics: custom("diagnostics"),
            logHistory: common(.logHistory), clearLogs: common(.clearLogs),
            additionalMaintenance: owner == "first" ? [custom("optional")] : [])
    }
    let first = catalog("first"), second = catalog("second")
    managementCheck(first.groups.flatMap(\.actions).map(\.id) == [
        "refreshStatus", "disableAll", "profiles", "shortcuts", "log", "diagnostics", "logHistory", "clearLogs", "optional",
    ], "common command order drifted or an absent document action was fabricated")
    managementCheck(!second.groups.flatMap(\.actions).contains { $0.id == "optional" },
                    "optional command leaked into another context")
    first.refresh.perform(); second.diagnostics.perform(); first.additionalMaintenance[0].perform()
    available["first"] = false
    first.refresh.perform(); first.profiles.perform(); first.additionalMaintenance[0].perform()
    second.profiles.perform()
    managementCheck(events == ["first:refreshStatus", "second:diagnostics", "first:optional", "second:profiles"],
                    "captured commands lost their context or ignored live unavailability")
}

@MainActor
func exerciseManagementLayout<Content: View>(
    content: () -> Content, catalog: () -> TrainerManagementCatalog, localization: TrainerLocalizationStore
) {
    let previousLanguage = localization.language
    defer { localization.language = previousLanguage }
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for width: CGFloat in [420, 760] {
            let expected = catalog().groups.flatMap(\.actions)
            let host = NSHostingView(rootView: content().environmentObject(localization).frame(width: width))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 1000),
                                  styleMask: [.titled], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = host
            managementWait(host, "common management actions at width \(width)") {
                let controls = nativeAccessibilityControls(host)
                return expected.allSatisfy { action in
                    controls.filter { $0.role == "AXButton" && $0.identifier == "trainer.management." + action.id }.count == 1
                }
            }
            let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
            for action in expected {
                let control = nativeAccessibilityControls(host).first { $0.identifier == "trainer.management." + action.id }!
                managementCheck(control.label == action.title && control.enabled == action.isEnabled,
                                "management action label or availability drifted: " + action.id)
                managementCheck(control.frame.width > 0 && control.frame.height > 0 && bounds.contains(control.frame),
                                "management action overflowed its narrow native host: " + action.id)
            }
            window.contentView = nil
            window.close()
        }
    }
}

@MainActor private final class ManagementPageVisibility: ObservableObject {
    @Published var visible = true
}

private struct ManagementPageFixture<Content: View>: View {
    let content: Content
    @ObservedObject var visibility: ManagementPageVisibility
    var body: some View { content.environment(\.trainerGamePageVisible, visibility.visible) }
}

@MainActor
func exerciseManagementPageDismissal<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore,
    show: () -> Void, dismissed: () -> Bool
) {
    let visibility = ManagementPageVisibility()
    let host = NSHostingView(rootView: ManagementPageFixture(content: content, visibility: visibility)
        .environmentObject(localization))
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 800),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    host.layoutSubtreeIfNeeded()
    show()
    managementWait(host, "module management sheet presented") { window.attachedSheet != nil }
    visibility.visible = false
    managementWait(host, "hidden module management sheet dismissed") { dismissed() && window.attachedSheet == nil }
    visibility.visible = true
    host.layoutSubtreeIfNeeded()
    managementCheck(dismissed(), "returning to the page reopened a stale management presentation")
    window.contentView = nil
    window.close()
}
'''

PROFILE_JOURNEY = r'''
func managementCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func managementWait(_ view: NSView, _ expectation: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    repeat {
        view.layoutSubtreeIfNeeded()
        if condition() { return }
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))
    } while Date() < deadline
    fatalError("management UI timed out: " + expectation)
}

func managementFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(managementFields)
}

func managementPress(_ name: String, in view: NSView) {
    managementWait(view, "enabled button " + name) {
        namedNativeControl(view, role: "AXButton", name: name)?.enabled == true
    }
    managementCheck(namedNativeControl(view, role: "AXButton", name: name)!.press(),
                    "native button refused Press: " + name)
}

func managementHasText(_ text: String, in view: NSView) -> Bool {
    nativeAccessibilityControls(view).contains { $0.text == text }
}

@MainActor
func exerciseProfileManager<Content: View>(
    _ content: Content, labels: TrainerProfileManagerLabels,
    localization: TrainerLocalizationStore, inventory: () -> [String], busy: () -> Bool,
    dismissed: () -> Bool, commands: () -> [[String: Any]],
    afterLoad: (NSView) -> Void = { _ in }
) {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 600),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    let host = NSHostingView(rootView: content.environmentObject(localization))
    window.contentView = host
    host.frame = NSRect(x: 0, y: 0, width: 620, height: 600)
    func run(_ label: String, command: String, name: String? = nil) {
        let count = commands().count
        managementPress(label, in: host)
        managementWait(host, command + " reply") { !busy() && commands().count > count }
        let request = commands().last!
        managementCheck(request["command"] as? String == command, "wrong management command")
        if let name {
            managementCheck((request["params"] as? [String: Any])?["name"] as? String == name,
                            "selection or name draft routed to a different profile")
        }
    }
    func enter(_ value: String) {
        managementWait(host, "native profile name field") {
            managementFields(host).contains { $0.accessibilityLabel() == labels.name }
        }
        let field = managementFields(host).first { $0.accessibilityLabel() == labels.name }!
        let coordinator = field.delegate as! TrainerTextField.Coordinator
        coordinator.begin()
        field.stringValue = value
        coordinator.controlTextDidChange(Notification(name: NSControl.textDidChangeNotification, object: field))
        coordinator.controlTextDidEndEditing(Notification(name: NSControl.textDidEndEditingNotification, object: field))
    }

    managementWait(host, "initial profile inventory") { inventory() == ["Fixture"] && !busy() }
    run(labels.load, command: "load_profile", name: "Fixture")
    afterLoad(host)
    enter(" Renamed ")
    run(labels.save, command: "save_profile", name: "Renamed")
    managementWait(host, "created profile") { inventory().contains("Renamed") }
    run(labels.load, command: "load_profile", name: "Renamed")
    enter("__error__")
    run(labels.save, command: "save_profile", name: "__error__")
    managementWait(host, "visible failed-save feedback") {
        managementHasText("Profile fixture rejected.", in: host)
    }
    managementCheck(!inventory().contains("__error__"), "failed save fabricated a stored profile")
    run(labels.load, command: "load_profile", name: "Renamed")
    run(localization.localized("host.delete"), command: "delete_profile", name: "Renamed")
    managementWait(host, "deleted selected profile") { inventory() == ["Fixture"] }
    run(labels.load, command: "load_profile", name: "Fixture")
    run(localization.localized("host.delete"), command: "delete_profile", name: "Fixture")
    managementWait(host, "empty inventory feedback") {
        inventory().isEmpty && managementHasText(labels.empty, in: host)
    }
    managementCheck(namedNativeControl(host, role: "AXButton", name: labels.load)?.enabled != true,
                    "empty inventory retained an enabled load action")
    run(localization.localized("host.refresh"), command: "list_profiles")
    managementPress(localization.localized("host.done"), in: host)
    managementCheck(dismissed(), "Done did not dismiss the owning module sheet")
    window.contentView = nil
    window.close()
    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
}
'''

DIAGNOSTICS_JOURNEY = r'''
@MainActor
func exerciseDiagnostics<Content: View>(
    _ content: Content, localization: TrainerLocalizationStore,
    refreshTitle: String, exportTitle: String, checkName: String, nonpassingStatus: String,
    busy: () -> Bool, count: () -> Int, dismissed: () -> Bool,
    commands: () -> [[String: Any]], setMode: (String) throws -> Void
) rethrows {
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 620),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    let host = NSHostingView(rootView: content.environmentObject(localization))
    window.contentView = host
    host.frame = NSRect(x: 0, y: 0, width: 700, height: 620)
    managementWait(host, "diagnostic names, details and truthful summary") {
        managementHasText(checkName, in: host)
            && managementHasText("Fixture caution", in: host)
            && managementHasText(localization.localized("host.diagnostics.summary", arguments: ["1", "2"]), in: host)
            && managementHasText(localization.localized(nonpassingStatus), in: host)
    }
    managementCheck(namedNativeControl(host, role: "AXButton", name: exportTitle)?.enabled == true,
                    "module diagnostic export became inaccessible")
    func refresh() {
        let before = commands().count
        managementPress(refreshTitle, in: host)
        managementWait(host, "diagnostic refresh reply") { !busy() && commands().count > before }
        managementCheck(commands().last?["command"] as? String == "diagnostics",
                        "diagnostic refresh lost its game-owned command")
    }
    try setMode("empty")
    refresh()
    managementWait(host, "diagnostic empty state") {
        count() == 0 && managementHasText(localization.localized("host.diagnostics.empty"), in: host)
    }
    try setMode("error")
    refresh()
    managementWait(host, "diagnostic failure feedback") {
        managementHasText("Diagnostic fixture rejected.", in: host)
    }
    try setMode("viewer")
    refresh()
    managementWait(host, "diagnostic recovery") { count() == 2 && !busy() }
    managementPress(localization.localized("host.done"), in: host)
    managementCheck(dismissed(), "diagnostic Done did not dismiss the owning module sheet")
    window.contentView = nil
    window.close()
}

@MainActor
func exerciseDiagnosticStatuses(localization: TrainerLocalizationStore) {
    var refreshes = 0, exports = 0, dismissed = false
    let labels = TrainerDiagnosticsLabels(title: "Fixture Diagnostics", explanation: "",
        refresh: "Refresh fixture", export: "Export fixture")
    let checks = [TrainerDiagnosticStatus.passed, .warning, .failed, .unknown].map { status in
        TrainerDiagnosticEntry(id: status.rawValue, name: "Fixture " + status.rawValue, detail: "", status: status)
    }
    func content(busy: Bool, refresh: Bool, export: Bool) -> some View {
        TrainerDiagnosticsView(labels: labels, checks: checks, busy: busy, canRefresh: refresh, canExport: export,
            actions: .init(refresh: { refreshes += 1 }, export: { exports += 1 }, dismiss: { dismissed = true }))
            .environmentObject(localization)
    }
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 620),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    let host = NSHostingView(rootView: content(busy: false, refresh: true, export: true))
    window.contentView = host
    host.frame = NSRect(x: 0, y: 0, width: 700, height: 620)
    managementWait(host, "unknown diagnostic remains nonpassing and accessible") {
        managementHasText(localization.localized("host.diagnostics.summary", arguments: ["1", "4"]), in: host)
            && managementHasText(localization.localized("host.diagnostics.unknown"), in: host)
    }
    managementPress(labels.refresh, in: host)
    managementPress(labels.export, in: host)
    managementCheck(refreshes == 1 && exports == 1, "diagnostic action callbacks did not remain independent")
    host.rootView = content(busy: true, refresh: true, export: true)
    managementWait(host, "busy diagnostic controls disabled") {
        namedNativeControl(host, role: "AXButton", name: labels.refresh)?.enabled == false
            && namedNativeControl(host, role: "AXButton", name: labels.export)?.enabled == false
    }
    host.rootView = content(busy: false, refresh: false, export: true)
    managementWait(host, "independent diagnostic action availability") {
        namedNativeControl(host, role: "AXButton", name: labels.refresh)?.enabled == false
            && namedNativeControl(host, role: "AXButton", name: labels.export)?.enabled == true
    }
    managementPress(localization.localized("host.done"), in: host)
    managementCheck(dismissed, "unavailable refresh trapped the diagnostic sheet")
    window.contentView = nil
    window.close()
}
'''

MANAGEMENT_JOURNEY += r'''
@MainActor private final class ControlMotionState: ObservableObject {
    @Published var enabled = true
    @Published var isOn = false
    @Published var locked = false
    @Published var selected = false
    @Published var pending = false
    @Published var phase = "Ready"
    var acceptsToggle = true
    var requests: [String] = []

    func toggle() {
        requests.append("toggle")
        if acceptsToggle { isOn.toggle() }
        else { pending = true; phase = "Pending" }
    }
}

private struct ControlMotionFixture: View {
    @ObservedObject var state: ControlMotionState
    let title: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TrainerFeatureToggleRow(title: title, icon: "bolt", state: .init(
                isOn: state.isOn, isInteractive: state.enabled && !state.pending,
                canEditValue: false, opacity: state.pending ? 0.65 : 1,
                indicatorColor: state.phase == "Ready" ? .purple : .orange,
                helpText: state.phase, isWarning: state.phase != "Ready"
            ), shortcutText: nil, action: state.toggle)
            HStack(spacing: 12) {
                TrainerLockButton(title: title, locked: state.locked, enabled: state.enabled) {
                    state.requests.append("lock"); state.locked.toggle()
                }.accessibilityIdentifier("motion.lock")
                TrainerSelectionControl(selected: state.selected, enabled: state.enabled) {
                    state.requests.append("selection"); state.selected.toggle()
                }.accessibilityIdentifier("motion.selection")
                TrainerResetButton(title: "Reset", enabled: state.enabled) {
                    state.requests.append("reset")
                }.accessibilityIdentifier("motion.reset")
            }
            TrainerPrimaryActionButton(title: title, enabled: state.enabled, width: 180) {
                state.requests.append("primary")
            }
            .accessibilityIdentifier("motion.primary")
            .keyboardShortcut("k", modifiers: [.command, .option])
            TrainerSecondaryActionButton(title: title, enabled: state.enabled, width: 180) {
                state.requests.append("secondary")
            }.accessibilityIdentifier("motion.secondary")
        }.padding(12)
    }
}

private func motionToggleValue(_ control: NativeAccessibilityControl) -> Bool? {
    let selector = NSSelectorFromString("accessibilityValue")
    guard control.object.responds(to: selector) else { return nil }
    let value = control.object.perform(selector)?.takeUnretainedValue()
    if let number = value as? NSNumber { return number.boolValue }
    if let text = value as? String { return text == "1" || text == "true" }
    return nil
}

@MainActor
func exerciseSharedControlMotion(localization: TrainerLocalizationStore) {
    let roles: [TrainerMotion.Role] = [.directManipulation, .selection, .disclosure, .transientFeedback]
    for role in roles {
        let reduced = TrainerMotion.transaction(role, reduceMotion: true)
        managementCheck(reduced.animation == nil && reduced.disablesAnimations,
                        "Reduce Motion allowed a custom or descendant animation")
    }
    let direct = TrainerMotion.transaction(.directManipulation, reduceMotion: false)
    managementCheck(direct.animation == nil && direct.disablesAnimations,
                    "direct manipulation inherited lagging animation")
    let selection = TrainerMotion.transaction(.selection, reduceMotion: false)
    managementCheck(selection.animation != nil && !selection.disablesAnimations,
                    "normal selection lost its interruptible motion")
    var native = Transaction(animation: .linear(duration: 9))
    let inherited = native.animation
    TrainerMotion.nativeControlTransaction(&native, reduceMotion: false)
    managementCheck(native.animation == inherited && !native.disablesAnimations,
                    "native controls replaced normal system transaction behavior")
    TrainerMotion.nativeControlTransaction(&native, reduceMotion: true)
    managementCheck(native.animation == nil && native.disablesAnimations,
                    "native controls inherited a moving reduced-motion transaction")

    let previousLanguage = localization.language
    defer { localization.language = previousLanguage }
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for (reduced, width) in [(false, CGFloat(420)), (true, CGFloat(340))] {
            let state = ControlMotionState()
            let title = language == .en ? "Fixture control" : "测试功能"
            let host = NSHostingView(rootView: ControlMotionFixture(state: state, title: title)
                .environmentObject(localization).environment(\.accessibilityReduceMotion, reduced))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 260),
                styleMask: [.titled, .closable], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            func button(_ id: String) -> NativeAccessibilityControl? {
                nativeAccessibilityControls(host).first { $0.identifier == "motion." + id && $0.role == "AXButton" }
            }
            func toggle() -> NativeAccessibilityControl? {
                nativeAccessibilityControls(host).first {
                    $0.label == title && ($0.role == "AXCheckBox" || $0.role == "AXSwitch")
                }
            }
            let ids = ["lock", "selection", "reset", "primary", "secondary"]
            managementWait(host, "shared native controls") {
                ids.allSatisfy { button($0)?.enabled == true } && toggle()?.enabled == true
            }
            let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
            for id in ids {
                let frame = button(id)!.frame
                managementCheck(frame.width > 0 && frame.height > 0 && bounds.contains(frame),
                                "shared native control clipped at width \(width): " + id)
                if ["lock", "selection", "reset"].contains(id) {
                    managementCheck(frame.width <= 27 && frame.height <= 25,
                                    "native compact control changed the metric-card footprint: " + id)
                }
            }
            for expected in [true, false, true, false] {
                let before = state.requests.count
                managementCheck(toggle()!.press(), "native feature toggle refused AX press")
                managementWait(host, "rapid toggle reversal") {
                    state.isOn == expected && toggle().flatMap(motionToggleValue) == expected
                }
                managementCheck(state.requests.count == before + 1, "toggle double-fired or waited for motion")
            }
            state.acceptsToggle = false
            managementCheck(toggle()!.press(), "pending feature toggle refused AX press")
            managementWait(host, "pending feature state") { toggle()?.enabled == false }
            managementCheck(!state.isOn && toggle().flatMap(motionToggleValue) == false,
                            "pending animation fabricated an acknowledged on state")
            state.pending = false; state.phase = "Failed"
            managementWait(host, "failed feature recovery") { toggle()?.enabled == true && toggle()?.help == "Failed" }
            managementCheck(toggle().flatMap(motionToggleValue) == false, "failed action left false success state")
            state.acceptsToggle = true; state.phase = "Ready"

            for _ in 0..<2 {
                for id in ids {
                    let before = state.requests.count
                    managementCheck(button(id)!.press(), "native shared button refused AX press: " + id)
                    managementWait(host, "immediate button action") { state.requests.count == before + 1 }
                }
            }
            managementCheck(!state.locked && !state.selected, "repeated state controls did not reverse")
            let key = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [.command, .option],
                timestamp: 0, windowNumber: window.windowNumber, context: nil, characters: "k",
                charactersIgnoringModifiers: "k", isARepeat: false, keyCode: 40)!
            let beforeKey = state.requests.count
            _ = window.performKeyEquivalent(key)
            managementWait(host, "native button keyboard equivalent") { state.requests.count == beforeKey + 1 }
            managementCheck(state.requests.last == "primary", "keyboard action targeted the wrong control")

            state.enabled = false
            managementWait(host, "disabled shared controls") {
                ids.allSatisfy { button($0)?.enabled == false } && toggle()?.enabled == false
            }
            let beforeDisabled = state.requests.count
            for id in ids { _ = button(id)!.press() }
            _ = toggle()!.press()
            _ = window.performKeyEquivalent(key)
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            managementCheck(state.requests.count == beforeDisabled, "disabled control dispatched an action")

            state.isOn = true; state.locked = true; state.selected = true
            managementWait(host, "external observed state") {
                toggle().flatMap(motionToggleValue) == true
                    && button("selection")?.valueText == localization.localized("host.selection.selected")
                    && button("lock")?.label == localization.localized("host.unlockValue", arguments: [title])
            }
            managementCheck(state.requests.count == beforeDisabled, "observation animation dispatched an action")
            window.contentView = nil
            window.close()
        }
    }
}
'''
