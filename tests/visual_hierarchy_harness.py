"""Shared native visual hierarchy journey, using each real module's presentation."""

VISUAL_HIERARCHY_JOURNEY = r'''
@MainActor private final class VisualHierarchyState: ObservableObject {
    @Published var current = "125"
    @Published var maximum = "150"
    @Published var amount = "12345"
    @Published var stat = "20"
    @Published var counter = "3"
    @Published var focus: String?
    @Published var selected = true
}

private struct VisualHierarchyFixture: View {
    @ObservedObject var state: VisualHierarchyState
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let descriptor: GameModuleDescriptor
    let presentation: TrainerGamePresentation

    private func title(_ english: String, _ chinese: String) -> String {
        localization.language == .en ? english : chinese
    }

    var body: some View {
        TrainerShell {
            TrainerSidebar {
                TrainerSidebarCard(descriptor: descriptor, presentation: presentation,
                    connected: true, busy: false, targetRunning: true,
                    operationToken: .init(key: "host.refreshStatus"),
                    statusToken: .init(key: "host.connected"),
                    detailToken: .init(key: "host.refreshStatusHelp"),
                    selected: state.selected, onSelect: { state.selected = true }) {
                    TrainerPrimaryActionButton(title: localization.localized("host.refreshStatus"),
                        enabled: true, width: 160) {}
                    TrainerSectionButton(title: title("Common functions", "常用功能"),
                        systemImage: "switch.2") {}
                }
            }
        } content: {
            VStack(alignment: .leading, spacing: TrainerTheme.standard.pageSpacing) {
                TrainerPageHeader(title: presentation.headerTitle) { EmptyView() }
                TrainerSection(title: title("Run values", "当前数值"), icon: "chart.bar") {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                        TrainerVitalMetricCard(title: title("Health", "生命值"), icon: "heart", tint: .red,
                            current: $state.current, maximum: $state.maximum, focus: $state.focus,
                            currentField: "current", maximumField: "maximum",
                            locked: false, editable: true, onLock: {})
                        TrainerAmountMetricCard(title: title("Resources", "资源数量"), icon: "circle", tint: .orange,
                            text: $state.amount, focus: $state.focus, focusValue: "amount",
                            locked: false, editable: true, onLock: {})
                        TrainerStatMetricCard(title: title("Movement speed", "移动速度"), icon: "figure.walk",
                            text: $state.stat, focus: $state.focus, focusValue: "stat", suffix: "%",
                            locked: true, supported: true, available: true, editable: false, onLock: {})
                        TrainerCounterMetricCard(title: title("Remaining uses", "剩余次数"), icon: "arrow.clockwise",
                            tint: .blue, text: $state.counter, focus: $state.focus,
                            focusValue: "counter", detail: nil, editable: true)
                    }
                }
                TrainerSection(title: title("Common functions", "常用功能"), icon: "switch.2") {
                    VStack(spacing: 1) {
                        TrainerFeatureToggleRow(title: title("A longer localized feature name", "较长的双语功能名称"),
                            icon: "shield", state: .init(isOn: false, isInteractive: false,
                                canEditValue: false, opacity: 1, indicatorColor: .secondary,
                                helpText: title("Currently unavailable", "当前不可用"), isWarning: false),
                            shortcutText: nil, action: {})
                        TrainerLabeledControlRow(title: title("Selected option", "指定选项"), icon: "list.bullet",
                            tint: TrainerTheme.standard.accent, emphasized: false) {
                            Picker(title("Selected option", "指定选项"), selection: .constant("first")) {
                                Text(title("A long localized option", "较长的本地化选项")).tag("first")
                            }
                            .labelsHidden()
                            .trainerPickerWidth(.standard)
                            .background(HierarchyPickerLayoutProbe().allowsHitTesting(false).accessibilityHidden(true))
                            .accessibilityIdentifier("hierarchy.picker")
                        }
                    }.trainerGroupedRows()
                }
            }
            .frame(minWidth: TrainerTheme.standard.contentMinWidth,
                   maxWidth: TrainerTheme.standard.pageMaxWidth, alignment: .topLeading)
        }
        .preferredColorScheme(.dark)
        .trainerTheme(.standard)
    }
}

// The width role owns the SwiftUI allocation. AppKit owns the native bezel's
// interior/insets, so its AX frame need not equal that allocation's width.
private struct HierarchyPickerLayoutProbe: NSViewRepresentable {
    final class Frame: NSView {}
    func makeNSView(context: Context) -> Frame { Frame() }
    func updateNSView(_ view: Frame, context: Context) {}
}

private func hierarchyPickerFrame(_ view: NSView) -> NSView? {
    if view is HierarchyPickerLayoutProbe.Frame { return view }
    return view.subviews.lazy.compactMap(hierarchyPickerFrame).first
}

private func hierarchyCheck(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

private func hierarchyFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(hierarchyFields)
}

@MainActor
private func hierarchyPump(_ duration: TimeInterval) {
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
private func hierarchyWait(_ host: NSView, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(3)
    repeat {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        hierarchyPump(0.02)
    } while Date() < deadline
    hierarchyCheck(condition(), "visual hierarchy did not mount its native controls")
}

@MainActor
private func hierarchyStableFrames(_ host: NSView, fields: [NSTextField], context: String,
                                   ready: () -> Bool) -> [NSRect] {
    let deadline = Date().addingTimeInterval(3)
    var previous: [NSRect] = []
    var stableSamples = 0
    repeat {
        host.layoutSubtreeIfNeeded()
        let frames = fields.map { $0.convert($0.bounds, to: nil) }
        stableSamples = ready() && frames == previous ? stableSamples + 1 : 0
        previous = frames
        if stableSamples >= 4 { return frames }
        hierarchyPump(0.02)
    } while Date() < deadline
    fatalError("visual hierarchy did not settle: \(context) ready=\(ready()) active=\(NSApp.isActive) key=\(host.window?.isKeyWindow == true) frames=\(previous)")
}

@MainActor
func exerciseVisualHierarchy(descriptor: GameModuleDescriptor, presentation: TrainerGamePresentation) {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    NSApp.activate(ignoringOtherApps: true)
    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    let theme = TrainerTheme.standard
    // System accessibility environment values are read-only. Exercise the
    // actual shared policy for both inputs and render the user's current
    // setting without changing global preferences or inventing an override.
    hierarchyCheck(theme.boundaryColor(for: .standard) == theme.separator
                   && theme.boundaryColor(for: .increased) != theme.separator,
                   "Increase Contrast did not strengthen shared surface boundaries")
    hierarchyCheck(theme.selectionMarkerWidth(for: .increased) > theme.selectionMarkerWidth(for: .standard),
                   "Increase Contrast did not strengthen selected-card emphasis")
    let contrastName = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast ? "increased" : "standard"
    print("visual_hierarchy_system_contrast=" + contrastName)
    func components(_ color: Color) -> NSColor {
        NSColor(color).usingColorSpace(.deviceRGB)!
    }
    func luminance(_ color: Color) -> Double {
        let c = components(color)
        func linear(_ value: CGFloat) -> Double {
            let value = Double(value)
            return value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
        }
        return linear(c.redComponent) * 0.2126 + linear(c.greenComponent) * 0.7152 + linear(c.blueComponent) * 0.0722
    }
    let levels = [theme.background, theme.sidebarBackground, theme.panel, theme.panelRaised]
    hierarchyCheck(levels.allSatisfy { components($0).alphaComponent == 1 },
                   "structural surfaces depend on an uncontrolled window backdrop")
    let luminances = levels.map(luminance)
    hierarchyCheck(zip(luminances, luminances.dropFirst()).allSatisfy(<),
                   "canvas, sidebar, panels and raised content lost their visual order")
    hierarchyCheck((1.0 + 0.05) / (luminance(theme.panelRaised) + 0.05) >= 7,
                   "raised dark surfaces do not retain clear foreground contrast")

    // These are the product's real minimum shell width and a normal desktop
    // width. A 760-point whole window would violate its 760-point content pane.
    let minimumWidth = theme.contentMinWidth + theme.pagePadding * 2 + 260 + 1
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for key in ["host.refreshStatus", "host.connected", "host.refreshStatusHelp",
                    "host.input.currentValue", "host.input.maximumValue", "host.lockValue", "host.unlockValue"] {
            hierarchyCheck(localization.localized(key, arguments: ["Fixture"]) != key,
                           "visual hierarchy is missing its shipped Host localization: " + key)
        }
        hierarchyCheck(localization.localized("host.refreshStatus", language: .en)
                       != localization.localized("host.refreshStatus", language: .zhCN),
                       "visual hierarchy did not load both shipped Host language tables")
        for width in [minimumWidth, CGFloat(1280)] {
            let state = VisualHierarchyState()
            let host = NSHostingView(rootView: VisualHierarchyFixture(state: state,
                descriptor: descriptor, presentation: presentation).environmentObject(localization))
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 740),
                styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.appearance = NSAppearance(named: .darkAqua)
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            hierarchyWait(host) {
                NSApp.isActive && window.isKeyWindow
                    && hierarchyFields(host).filter { ["125", "150", "12345", "20", "3"].contains($0.stringValue) }.count == 5
            }
            let controls = nativeAccessibilityControls(host)
            hierarchyCheck(!controls.contains { control in
                [control.label, control.valueText, control.help].compactMap { $0 }.contains { $0.contains("host.") }
            }, "rendered native hierarchy exposes an unresolved Host presentation key")
            guard let game = controls.first(where: { $0.identifier == "host.game." + descriptor.id }),
                  let picker = controls.first(where: { $0.identifier == "hierarchy.picker" && $0.role == "AXPopUpButton" }) else {
                fatalError("actual sidebar selection or native Picker is missing")
            }
            let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
            hierarchyCheck(game.frame.height >= 30 && bounds.contains(game.frame),
                           "sidebar selection lost its hit target or clipped its label")
            guard let pickerLayout = hierarchyPickerFrame(host) else { fatalError("missing Picker layout probe") }
            let pickerFrame = window.convertToScreen(pickerLayout.convert(pickerLayout.bounds, to: nil))
            print("hierarchy_picker_geometry game=\(descriptor.id) language=\(language.rawValue) window=\(width) allocation=\(pickerFrame) native=\(picker.frame)")
            hierarchyCheck(abs(pickerFrame.width - theme.pickerStandardWidth) <= 1 && bounds.contains(pickerFrame),
                           "Picker width allocation changed at a constrained window width")
            hierarchyCheck(picker.frame.width > 0 && picker.frame.height > 0 && bounds.contains(picker.frame)
                           && pickerFrame.insetBy(dx: -1, dy: -1).contains(picker.frame),
                           "native Picker bezel escaped its allocated control width")
            let fields = hierarchyFields(host).filter { ["125", "150", "12345", "20", "3"].contains($0.stringValue) }
            for field in fields {
                let frame = window.convertToScreen(field.convert(field.bounds, to: nil))
                hierarchyCheck(frame.width > 0 && frame.height > 0 && bounds.contains(frame),
                               "native metric input was clipped or collapsed")
                hierarchyCheck((field.font?.pointSize ?? 0) >= 19, "metric hierarchy shrank the editable value")
            }
            hierarchyCheck(fields.first { $0.stringValue == "20" }?.isEnabled == false,
                           "visual hierarchy changed a disabled control's capability")
            let amount = fields.first { $0.stringValue == "12345" }!
            hierarchyCheck(window.makeFirstResponder(amount), "native metric input could not receive focus")
            guard let editor = amount.currentEditor() as? NSTextView else { fatalError("missing focused metric draft") }
            editor.selectAll(nil); editor.insertText("54321", replacementRange: editor.selectedRange())
            let context = "game=\(descriptor.id) language=\(language.rawValue) width=\(width)"
            func editingReady() -> Bool {
                NSApp.isActive && window.isKeyWindow && amount.currentEditor() === editor
                    && editor.string == "54321" && state.amount == "54321" && state.focus == "amount"
                    && fields.allSatisfy { $0.window === window }
            }
            // Editing updates the binding and native layout asynchronously. A
            // frame captured on insertText's call stack is not the baseline
            // for the later, independent sidebar selection update.
            let previousFrames = hierarchyStableFrames(host, fields: fields,
                context: context + " after native editing", ready: editingReady)
            state.selected = false
            let selectedFrames = hierarchyStableFrames(host, fields: fields,
                context: context + " after sidebar selection") { editingReady() && !state.selected }
            for (index, field) in fields.enumerated() {
                let frame = selectedFrames[index]
                let measurement = "hierarchy_selection_geometry \(context) field=\(field.accessibilityLabel() ?? field.placeholderString ?? "") value=\(field.stringValue) before=\(previousFrames[index]) after=\(frame) active=\(NSApp.isActive) key=\(window.isKeyWindow) focus=\(state.focus ?? "none")"
                FileHandle.standardError.write(Data((measurement + "\n").utf8))
                hierarchyCheck(abs(frame.minX - previousFrames[index].minX) < 1
                               && abs(frame.minY - previousFrames[index].minY) < 1
                               && abs(frame.width - previousFrames[index].width) < 1,
                               "selection changed native control geometry or density: " + measurement)
            }
            hierarchyCheck(editor.string == "54321", "surface update replaced a focused typed draft")
            window.makeFirstResponder(nil)
            state.selected = true
            _ = hierarchyStableFrames(host, fields: fields, context: context + " before snapshot") {
                window.isKeyWindow && state.selected && amount.currentEditor() == nil
                    && fields.allSatisfy { $0.window === window }
            }
            if let directory = ProcessInfo.processInfo.environment["MGT_UI_SNAPSHOT_DIR"], !directory.isEmpty {
                let url = URL(fileURLWithPath: directory, isDirectory: true)
                try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
                host.layoutSubtreeIfNeeded()
                guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
                    fatalError("native hierarchy snapshot allocation failed")
                }
                host.cacheDisplay(in: host.bounds, to: bitmap)
                guard let png = bitmap.representation(using: .png, properties: [:]) else {
                    fatalError("native hierarchy snapshot encoding failed")
                }
                let name = descriptor.id + "-" + language.rawValue + "-" + String(Int(width)) + "-" + contrastName + ".png"
                try! png.write(to: url.appendingPathComponent(name), options: .atomic)
            }
            window.contentView = nil
            window.close()
        }
    }
}
'''
