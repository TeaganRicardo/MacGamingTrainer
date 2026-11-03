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
    @Published var pickerSelection = "first"
    @Published var pickerAvailable = true
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
                        enabled: true, widthRole: .connection) {}
                    TrainerSectionButton(title: title("Common functions", "常用功能"),
                        systemImage: "switch.2") {}
                }
                .background(HierarchyCardHeightProbe().allowsHitTesting(false).accessibilityHidden(true))
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
                            Picker(title("Selected option", "指定选项"), selection: $state.pickerSelection) {
                                Text(title("A long localized option", "较长的本地化选项")).tag("first")
                                Text(title("Second option", "第二个选项")).tag("second")
                            }
                            .labelsHidden()
                            .trainerPicker(.rowValue, state: state.pickerAvailable ? .interactive : .unavailable)
                            .background(HierarchyPickerLayoutProbe().allowsHitTesting(false).accessibilityHidden(true))
                            .accessibilityIdentifier("hierarchy.picker")
                        }
                        TrainerLabeledControlRow(title: title("Unavailable option", "不可用选项"), icon: "list.bullet",
                            tint: .secondary, emphasized: false) {
                            Picker(title("Unavailable option", "不可用选项"), selection: .constant("none")) {
                                Text(title("No available item", "没有可用项目")).tag("none")
                            }
                            .labelsHidden()
                            .trainerPicker(.rowValue, state: .unavailable)
                            .accessibilityIdentifier("hierarchy.picker.unavailable")
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

// Native geometry of the actual sidebar card at each disclosure frame.
private struct HierarchyCardHeightProbe: NSViewRepresentable {
    final class Frame: NSView {}
    func makeNSView(context: Context) -> Frame { Frame() }
    func updateNSView(_ view: Frame, context: Context) {}
}

private func hierarchyCardHeightProbe(_ view: NSView) -> NSView? {
    if view is HierarchyCardHeightProbe.Frame { return view }
    return view.subviews.lazy.compactMap(hierarchyCardHeightProbe).first
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

private func hierarchyFocused(_ target: NativeAccessibilityControl) -> Bool {
    let selector = NSSelectorFromString("isAccessibilityFocused")
    guard target.object.responds(to: selector) else { return false }
    typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
    return unsafeBitCast(target.object.method(for: selector), to: Getter.self)(target.object, selector)
}

private func hierarchySelected(_ target: NativeAccessibilityControl) -> Bool {
    let selector = NSSelectorFromString("isAccessibilitySelected")
    guard target.object.responds(to: selector) else { return false }
    typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
    return unsafeBitCast(target.object.method(for: selector), to: Getter.self)(target.object, selector)
}

@discardableResult
private func hierarchySetFocused(_ target: NativeAccessibilityControl, _ focused: Bool) -> Bool {
    let selector = NSSelectorFromString("setAccessibilityFocused:")
    guard target.object.responds(to: selector) else { return false }
    typealias Setter = @convention(c) (AnyObject, Selector, Bool) -> Void
    unsafeBitCast(target.object.method(for: selector), to: Setter.self)(target.object, selector, focused)
    return true
}

private func hierarchyFields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(hierarchyFields)
}

private func hierarchyBitmap(_ view: NSView, around screenFrame: NSRect) -> Data {
    view.layoutSubtreeIfNeeded()
    guard let window = view.window else { fatalError("native hierarchy window is missing") }
    let windowFrame = window.convertFromScreen(screenFrame)
    let localFrame = view.convert(windowFrame, from: nil)
        .insetBy(dx: -8, dy: -8)
        .intersection(view.bounds)
    guard !localFrame.isEmpty,
          let bitmap = view.bitmapImageRepForCachingDisplay(in: localFrame) else {
        fatalError("native hierarchy bitmap allocation failed")
    }
    view.cacheDisplay(in: localFrame, to: bitmap)
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        fatalError("native hierarchy bitmap encoding failed")
    }
    return png
}

private func hierarchyBitmapExact(_ view: NSView, around screenFrame: NSRect) -> Data {
    view.layoutSubtreeIfNeeded()
    guard let window = view.window else { fatalError("native hierarchy window is missing") }
    let windowFrame = window.convertFromScreen(screenFrame)
    let localFrame = view.convert(windowFrame, from: nil).intersection(view.bounds)
    guard !localFrame.isEmpty,
          let bitmap = view.bitmapImageRepForCachingDisplay(in: localFrame) else {
        fatalError("native Picker chrome bitmap allocation failed")
    }
    view.cacheDisplay(in: localFrame, to: bitmap)
    guard let png = bitmap.representation(using: .png, properties: [:]) else {
        fatalError("native Picker chrome bitmap encoding failed")
    }
    return png
}

private func hierarchyPickerBodySample(_ frame: NSRect) -> NSRect {
    NSRect(
        x: frame.minX + min(7, max(2, frame.width * 0.03)),
        y: frame.midY - 2,
        width: min(6, max(2, frame.width * 0.03)),
        height: 4
    )
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
    if !condition() {
        let fields = hierarchyFields(host)
        let values = fields.map { field in
            "\(field.stringValue){enabled=\(field.isEnabled),frame=\(field.frame)}"
        }
        fatalError("visual hierarchy did not mount its native controls" +
            " active=\(NSApp.isActive) key=\(host.window?.isKeyWindow == true)" +
            " hostBounds=\(host.bounds) windowBounds=\(host.window?.contentView?.bounds.debugDescription ?? "none")" +
            " nativeFields=\(fields.count) values=\(values)")
    }
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
            // The hosted runner's virtual screen can be only 1024pt wide.
            // AppKit otherwise shrinks our 1077pt minimum-width fixture to
            // fit that screen, clipping the final 3pt of a correctly sized
            // control. Keep the product-width window even if partly offscreen;
            // allow its height to clamp to the runner's available space.
            window.minSize = NSSize(width: width, height: 400)
            window.setContentSize(NSSize(width: width, height: 740))
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            hierarchyWait(host) {
                // Hosted macOS may clamp a 740pt requested content height to
                // its actual screen. Wait for mounted native fields in the
                // real window instead of assuming NSWindow preserves 740pt.
                NSApp.isActive && window.isKeyWindow
                    && abs(host.bounds.width - width) < 1
                    && host.bounds.height > 0
                    && abs(host.bounds.width - window.contentView!.bounds.width) < 1
                    && abs(host.bounds.height - window.contentView!.bounds.height) < 1
                    && hierarchyFields(host).filter { ["125", "150", "12345", "20", "3"].contains($0.stringValue) }.count == 5
            }
            let controls = nativeAccessibilityControls(host)
            hierarchyCheck(!controls.contains { control in
                [control.label, control.valueText, control.help].compactMap { $0 }.contains { $0.contains("host.") }
            }, "rendered native hierarchy exposes an unresolved Host presentation key")
            guard let game = controls.first(where: { $0.identifier == "host.game." + descriptor.id }),
                  let picker = controls.first(where: { $0.identifier == "hierarchy.picker" && $0.role == "AXPopUpButton" }),
                  let simultaneouslyUnavailablePicker = controls.first(where: {
                      $0.identifier == "hierarchy.picker.unavailable" && $0.role == "AXPopUpButton"
                  }) else {
                fatalError("actual sidebar selection or native Picker is missing")
            }
            let bounds = window.convertToScreen(host.convert(host.bounds, to: nil)).insetBy(dx: -1, dy: -1)
            hierarchyCheck(game.frame.height >= 30 && bounds.contains(game.frame),
                           "sidebar selection lost its hit target or clipped its label")
            hierarchyCheck(hierarchySelected(game) == state.selected,
                           "module header lost its selected AX state")
            guard let cardProbe = hierarchyCardHeightProbe(host) else {
                fatalError("module-card height probe not mounted")
            }
            hierarchyPump(0.08)
            let expandedCardHeight = cardProbe.bounds.height
            state.selected = false
            var interpolatedCardHeights: [CGFloat] = []
            let collapseDeadline = Date().addingTimeInterval(0.36)
            while Date() < collapseDeadline {
                hierarchyPump(0.016)
                host.layoutSubtreeIfNeeded()
                interpolatedCardHeights.append(cardProbe.bounds.height)
            }
            let collapsedCardHeight = cardProbe.bounds.height
            hierarchyCheck(expandedCardHeight > collapsedCardHeight + 40,
                           "module card did not collapse its real action stack")
            if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
                hierarchyCheck(interpolatedCardHeights.contains {
                    $0 > collapsedCardHeight + 8 && $0 < expandedCardHeight - 8
                }, "module-card disclosure snapped instead of interpolating its geometry")
            }
            // Point inside the collapsed card's left background inset: it is
            // outside the title Button, but must select either game module.
            let cardFrame = cardProbe.convert(cardProbe.bounds, to: nil)
            let cardBackgroundPoint = NSPoint(x: cardFrame.minX + 4, y: cardFrame.midY)
            for eventType in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
                guard let event = NSEvent.mouseEvent(
                    with: eventType,
                    location: cardBackgroundPoint,
                    modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime,
                    windowNumber: window.windowNumber,
                    context: nil,
                    eventNumber: 1,
                    clickCount: 1,
                    pressure: 1
                ) else { fatalError("cannot construct native card pointer event") }
                window.sendEvent(event)
            }
            hierarchyPump(0.10)
            hierarchyCheck(state.selected,
                           "collapsed module-card background rejected pointer selection")
            hierarchyPump(0.40)
            host.layoutSubtreeIfNeeded()
            hierarchyCheck(abs(cardProbe.bounds.height - expandedCardHeight) < 3,
                           "module-card disclosure failed to restore its original height")
            print("sidebar_accordion_native_geometry game=\(descriptor.id) language=\(language.rawValue) width=\(width) expanded=\(expandedCardHeight) collapsed=\(collapsedCardHeight)")
            hierarchyPump(0.08)
            let headerFrame = game.frame
            let unfocusedBitmap = hierarchyBitmap(host, around: headerFrame)
            hierarchyCheck(hierarchySetFocused(game, true), "module header does not accept native AX focus")
            hierarchyPump(0.08)
            guard let focusedGame = nativeAccessibilityControls(host).first(where: {
                $0.identifier == "host.game." + descriptor.id
            }) else { fatalError("focused module header disappeared") }
            hierarchyCheck(hierarchyFocused(focusedGame), "module header did not retain native AX focus")
            hierarchyCheck(abs(focusedGame.frame.minX - headerFrame.minX) < 1
                           && abs(focusedGame.frame.minY - headerFrame.minY) < 1
                           && abs(focusedGame.frame.width - headerFrame.width) < 1
                           && abs(focusedGame.frame.height - headerFrame.height) < 1,
                           "module header focus changed its geometry")
            hierarchyCheck(hierarchyBitmap(host, around: headerFrame) == unfocusedBitmap,
                           "module header focus changed rendered presentation")
            hierarchyCheck(hierarchySetFocused(focusedGame, false), "module header rejected native AX focus removal")
            hierarchyPump(0.08)
            hierarchyCheck(hierarchyBitmap(host, around: headerFrame) == unfocusedBitmap,
                           "module header focus removal changed rendered presentation")
            guard let pickerLayout = hierarchyPickerFrame(host) else { fatalError("missing Picker layout probe") }
            let pickerFrame = window.convertToScreen(pickerLayout.convert(pickerLayout.bounds, to: nil))
            print("hierarchy_picker_geometry game=\(descriptor.id) language=\(language.rawValue) window=\(width) allocation=\(pickerFrame) native=\(picker.frame)")
            hierarchyCheck(abs(pickerFrame.width - theme.pickerStandardWidth) <= 1,
                           "Picker width allocation changed at a constrained window width: language=\(language.rawValue) window=\(width) expected=\(theme.pickerStandardWidth) actual=\(pickerFrame.width) frame=\(pickerFrame)")
            hierarchyCheck(bounds.contains(pickerFrame),
                           "Picker width allocation escaped the content window: language=\(language.rawValue) window=\(width) bounds=\(bounds) frame=\(pickerFrame)")
            hierarchyCheck(picker.frame.width > 0 && picker.frame.height > 0 && bounds.contains(picker.frame)
                           && pickerFrame.insetBy(dx: -1, dy: -1).contains(picker.frame),
                           "native Picker bezel escaped its allocated control width")
            let pickerIndicatorFrame = NSRect(
                x: picker.frame.maxX - min(28, picker.frame.width),
                y: picker.frame.minY,
                width: min(28, picker.frame.width),
                height: picker.frame.height
            )
            let interactivePickerChrome = hierarchyBitmapExact(host, around: pickerIndicatorFrame)
            let interactivePickerBody = hierarchyBitmapExact(host, around: hierarchyPickerBodySample(picker.frame))
            let simultaneousUnavailableChrome = hierarchyBitmapExact(host, around: NSRect(
                x: simultaneouslyUnavailablePicker.frame.maxX - min(28, simultaneouslyUnavailablePicker.frame.width),
                y: simultaneouslyUnavailablePicker.frame.minY,
                width: min(28, simultaneouslyUnavailablePicker.frame.width),
                height: simultaneouslyUnavailablePicker.frame.height
            ))
            let simultaneousUnavailableBody = hierarchyBitmapExact(
                host, around: hierarchyPickerBodySample(simultaneouslyUnavailablePicker.frame)
            )
            hierarchyCheck(simultaneousUnavailableChrome != interactivePickerChrome,
                           "simultaneous interactive/unavailable Pickers shared one chrome presentation")
            hierarchyCheck(simultaneousUnavailableBody != interactivePickerBody,
                           "simultaneous interactive/unavailable Pickers shared one body fill")
            state.pickerSelection = "second"
            hierarchyPump(0.10)
            host.layoutSubtreeIfNeeded()
            guard let selectedPicker = nativeAccessibilityControls(host).first(where: {
                $0.identifier == "hierarchy.picker" && $0.role == "AXPopUpButton"
            }) else { fatalError("Picker disappeared after selection change") }
            hierarchyCheck(
                hierarchyBitmapExact(host, around: NSRect(
                    x: selectedPicker.frame.maxX - min(28, selectedPicker.frame.width),
                    y: selectedPicker.frame.minY,
                    width: min(28, selectedPicker.frame.width),
                    height: selectedPicker.frame.height
                )) == interactivePickerChrome,
                "Picker selection changed the interactive chrome presentation"
            )
            hierarchyCheck(
                hierarchyBitmapExact(host, around: hierarchyPickerBodySample(selectedPicker.frame))
                    == interactivePickerBody,
                "Picker selection changed the interactive body fill"
            )
            state.pickerAvailable = false
            hierarchyPump(0.10)
            host.layoutSubtreeIfNeeded()
            guard let unavailablePicker = nativeAccessibilityControls(host).first(where: {
                $0.identifier == "hierarchy.picker" && $0.role == "AXPopUpButton"
            }) else { fatalError("Picker disappeared in unavailable state") }
            let unavailablePickerChrome = hierarchyBitmapExact(host, around: NSRect(
                x: unavailablePicker.frame.maxX - min(28, unavailablePicker.frame.width),
                y: unavailablePicker.frame.minY,
                width: min(28, unavailablePicker.frame.width),
                height: unavailablePicker.frame.height
            ))
            hierarchyCheck(unavailablePickerChrome != interactivePickerChrome,
                           "interactive and unavailable Picker chrome collapsed into one presentation")
            hierarchyCheck(
                hierarchyBitmapExact(host, around: hierarchyPickerBodySample(unavailablePicker.frame))
                    != interactivePickerBody,
                "interactive and unavailable Picker body fills collapsed into one presentation"
            )
            state.pickerAvailable = true
            hierarchyPump(0.10)
            host.layoutSubtreeIfNeeded()
            guard let restoredPicker = nativeAccessibilityControls(host).first(where: {
                $0.identifier == "hierarchy.picker" && $0.role == "AXPopUpButton"
            }) else { fatalError("Picker disappeared after restoring interaction") }
            hierarchyCheck(
                hierarchyBitmapExact(host, around: NSRect(
                    x: restoredPicker.frame.maxX - min(28, restoredPicker.frame.width),
                    y: restoredPicker.frame.minY,
                    width: min(28, restoredPicker.frame.width),
                    height: restoredPicker.frame.height
                )) == interactivePickerChrome,
                "Picker did not restore the same interactive chrome after unavailable state"
            )
            hierarchyCheck(
                hierarchyBitmapExact(host, around: hierarchyPickerBodySample(restoredPicker.frame))
                    == interactivePickerBody,
                "Picker did not restore the same interactive body fill after unavailable state"
            )
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
