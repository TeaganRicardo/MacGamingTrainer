"""Shared native-control journeys included by both existing macOS frontend tests."""

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
