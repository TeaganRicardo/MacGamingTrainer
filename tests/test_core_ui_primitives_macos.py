"""Headless macOS behavior checks for shared Core UI primitives and views."""

MGT_PLATFORM = "macos"
MGT_INPUTS = ("Resources/Localization/",)

import json
from pathlib import Path
import shutil
import sys
import tempfile

from macos_fixture_policy import launch_fixture
from fixture_budgets.core_ui_primitives import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test

if sys.platform != "darwin":
    raise SystemExit("macOS-only Core UI primitives verification")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import AppKit
import SwiftUI

private func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("core UI primitives: " + message) }
}

@MainActor
private func pump(_ duration: TimeInterval = 0.02) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(
            matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default,
            dequeue: true
        ) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
private func waitWindow(_ host: NSView, _ message: String, timeout: TimeInterval = 3.0, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        pump(0.01)
    }
    fatalError("core UI primitives timeout: " + message)
}

@MainActor
private func waitUntil(_ message: String, timeout: TimeInterval = 3.0, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if condition() { return }
        pump(0.01)
    }
    fatalError("core UI primitives timeout: " + message)
}

private struct FrameProbe: NSViewRepresentable {
    final class Marker: NSView {
        let tagID: String
        init(_ tagID: String) { self.tagID = tagID; super.init(frame: .zero) }
        required init?(coder: NSCoder) { nil }
    }
    let tagID: String
    init(_ tagID: String) { self.tagID = tagID }
    func makeNSView(context: Context) -> Marker { Marker(tagID) }
    func updateNSView(_ view: Marker, context: Context) {}
}

private func probeFrame(_ tagID: String, in root: NSView, to space: NSView) -> NSRect? {
    func find(_ v: NSView) -> NSView? {
        if let m = v as? FrameProbe.Marker, m.tagID == tagID { return m }
        for child in v.subviews {
            if let hit = find(child) { return hit }
        }
        return nil
    }
    guard let view = find(root) else { return nil }
    return view.convert(view.bounds, to: space)
}

private func textFields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(textFields)
}

private func focusRingViews(in view: NSView) -> [NSView] {
    let matches = String(describing: type(of: view)).contains("FocusRingView") ? [view] : []
    return matches + view.subviews.flatMap(focusRingViews)
}

private func nativeSwitches(in view: NSView) -> [NSControl] {
    let matches: [NSControl] = (view as? NSControl).flatMap { c in
        String(describing: type(of: c)).contains("Switch") ? [c] : nil
    } ?? []
    return matches + view.subviews.flatMap(nativeSwitches)
}

private func scrollViews(in view: NSView) -> [NSScrollView] {
    (view as? NSScrollView).map { [$0] } ?? view.subviews.flatMap(scrollViews)
}

private func axSubrole(_ control: NativeAccessibilityControl) -> String? {
    let selector = NSSelectorFromString("accessibilitySubrole")
    guard control.object.responds(to: selector) else { return nil }
    return control.object.perform(selector)?.takeUnretainedValue() as? String
}

private func localRect(_ screenRect: NSRect, in host: NSView, window: NSWindow) -> NSRect {
    host.convert(window.convertFromScreen(screenRect), from: nil)
}

private func rasterize(_ host: NSView) -> NSBitmapImageRep {
    host.layoutSubtreeIfNeeded()
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    return bitmap
}

private func rgba(_ bitmap: NSBitmapImageRep, ptX: CGFloat, ptY: CGFloat, host: NSView) -> NSColor {
    let bounds = host.bounds
    let scaleX = CGFloat(bitmap.pixelsWide) / bounds.width
    let scaleY = CGFloat(bitmap.pixelsHigh) / bounds.height
    let px = max(0, min(bitmap.pixelsWide - 1, Int((ptX * scaleX).rounded())))
    let rawY = host.isFlipped ? ptY : (bounds.height - ptY)
    let py = max(0, min(bitmap.pixelsHigh - 1, Int((rawY * scaleY).rounded())))
    return bitmap.colorAt(x: px, y: py)?.usingColorSpace(.deviceRGB) ?? .black
}

private func luminance(_ bitmap: NSBitmapImageRep, ptX: CGFloat, ptY: CGFloat, host: NSView) -> CGFloat {
    let c = rgba(bitmap, ptX: ptX, ptY: ptY, host: host)
    return (c.redComponent + c.greenComponent + c.blueComponent) / 3.0
}

private func hasMatchingPixel(
    _ bitmap: NSBitmapImageRep, in rect: NSRect, host: NSView, step: CGFloat = 1.5,
    matching predicate: (NSColor) -> Bool
) -> Bool {
    var x = rect.minX
    while x <= rect.maxX {
        var y = rect.minY
        while y <= rect.maxY {
            if predicate(rgba(bitmap, ptX: x, ptY: y, host: host)) { return true }
            y += step
        }
        x += step
    }
    return false
}

private func isPurple(_ c: NSColor) -> Bool {
    c.blueComponent > 0.5 && c.blueComponent > c.greenComponent + 0.15 && c.redComponent > 0.25
}

private func isOrange(_ c: NSColor) -> Bool {
    c.redComponent > 0.55 && c.greenComponent > 0.2 && c.redComponent > c.greenComponent + 0.12 && c.redComponent > c.blueComponent + 0.30
}

private func isGreen(_ c: NSColor) -> Bool {
    c.greenComponent > 0.45 && c.greenComponent > c.redComponent + 0.15 && c.greenComponent > c.blueComponent + 0.1
}

private func isCyan(_ c: NSColor) -> Bool {
    c.blueComponent > 0.45 && c.greenComponent > 0.4 && c.blueComponent > c.redComponent + 0.15
}

private func measureCardPaintedBounds(
    bitmap: NSBitmapImageRep, host: NSView, probeX: CGFloat, insideY: CGFloat, canvasLuma: CGFloat
) -> (minY: CGFloat, maxY: CGFloat, height: CGFloat) {
    let threshold = canvasLuma + 0.012
    var minY = insideY
    while minY > 2 && luminance(bitmap, ptX: probeX, ptY: minY - 0.5, host: host) > threshold { minY -= 0.5 }
    var maxY = insideY
    while maxY < host.bounds.height - 2 && luminance(bitmap, ptX: probeX, ptY: maxY + 0.5, host: host) > threshold { maxY += 0.5 }
    return (minY, maxY, maxY - minY)
}

@MainActor
private func clickLocal(_ point: NSPoint, in window: NSWindow, host: NSView) {
    let windowPoint = host.convert(point, to: nil)
    for type in [NSEvent.EventType.leftMouseDown, .leftMouseUp] {
        let event = NSEvent.mouseEvent(
            with: type, location: windowPoint, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: type == .leftMouseUp ? 0 : 1
        )!
        window.sendEvent(event)
    }
}

@MainActor
private func makeWindow(width: CGFloat, height: CGFloat, root: some View, appearance: NSAppearance.Name = .darkAqua) -> (NSWindow, NSHostingView<AnyView>) {
    let window = NSWindow(
        contentRect: NSRect(x: 200, y: 400, width: width, height: height),
        styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false
    )
    window.isReleasedWhenClosed = false
    window.appearance = NSAppearance(named: appearance)
    window.minSize = NSSize(width: width, height: 100)
    window.setContentSize(NSSize(width: width, height: height))
    let host = NSHostingView(rootView: AnyView(root))
    host.frame = NSRect(x: 0, y: 0, width: width, height: height)
    window.contentView = host
    window.orderBack(nil)
    return (window, host)
}

// MARK: - Scenario 1: Toggles & Feature Controls

@MainActor
private func exerciseTogglesAndFeatures(localization: TrainerLocalizationStore) {
    let theme = TrainerTheme.standard
    check(theme.deferred == .orange && theme.warning == .orange,
          "theme.deferred or warning is no longer orange")
    check(theme.rowContentSpacing == 16 && theme.rowIconSize == 40 &&
          theme.compactActionWidth == 88 && theme.compactFieldWidth == 58 &&
          theme.shortcutBadgeMinimumWidth == 52 && theme.pickerActionMaxWidth == 420 &&
          theme.rowHorizontalPadding == 22 && theme.rowMinimumHeight == 64,
          "TrainerTheme.standard layout tokens drifted")

    let detached = TrainerFeaturePresentation(
        enabled: true, supported: true, connected: false,
        active: false, dormant: false, activationPending: false,
        canActivate: true, canEditDesired: true
    )
    let waiting = TrainerFeaturePresentation(
        enabled: true, supported: true, connected: true,
        active: false, dormant: true, activationPending: false,
        canActivate: true, canEditDesired: true
    )
    let mismatch = TrainerFeaturePresentation(
        enabled: true, supported: true, connected: true,
        active: false, dormant: false, activationPending: false,
        canActivate: true, canEditDesired: true
    )
    let active = TrainerFeaturePresentation(
        enabled: true, supported: true, connected: true,
        active: true, dormant: false, activationPending: false,
        canActivate: true, canEditDesired: true
    )
    let pending = TrainerFeaturePresentation(
        enabled: true, supported: true, connected: true,
        active: false, dormant: false, activationPending: true,
        canActivate: true, canEditDesired: true
    )
    let unsupported = TrainerFeaturePresentation(
        enabled: false, supported: false, connected: false,
        active: false, dormant: false, activationPending: false,
        canActivate: false, canEditDesired: false
    )
    check(detached.tint(using: theme) == theme.warning, "detached phase tint must use theme.warning")
    check(waiting.tint(using: theme) == theme.warning && mismatch.tint(using: theme) == theme.warning,
          "waiting/mismatch tint must use theme.warning")
    check(active.tint(using: theme) == theme.accent && pending.tint(using: theme) == theme.accent,
          "active/pending tint must use theme.accent")
    check(unsupported.opacity == theme.disabledOpacity && !unsupported.isInteractive,
          "unsupported feature presentation lost disabledOpacity")
    check(!waiting.helpText(using: localization).isEmpty
          && !detached.helpText(using: localization).isEmpty
          && !mismatch.helpText(using: localization).isEmpty,
          "phase help tokens failed to localize")

    let waitingState = waiting.trainerControlState(using: theme, localization: localization)
    let activeState = active.trainerControlState(using: theme, localization: localization)
    var multText = "2.5"
    let view = VStack(alignment: .leading, spacing: 8) {
        TrainerToggleControl(title: "DefaultSwitch", isOn: true, action: {})
            .frame(maxWidth: .infinity, alignment: .leading)
        TrainerFeatureToggleRow(title: "WaitingToggle", icon: "shield.fill", state: waitingState, shortcutText: "⌃1", action: {})
            .frame(maxWidth: .infinity)
        TrainerFeatureToggleRow(title: "PlainToggle", icon: "heart.fill", state: activeState, shortcutText: nil, action: {})
        TrainerFeatureMultiplierRow(title: "WaitingMult", icon: "bolt.fill", state: waitingState,
                                    text: Binding(get: { multText }, set: { multText = $0 }), shortcutText: "⌃2", action: {})
        TrainerFeatureMultiplierRow(title: "PlainMult", icon: "star.fill", state: activeState,
                                    text: Binding(get: { multText }, set: { multText = $0 }), shortcutText: nil, action: {})
        TrainerCheckboxControl(title: "RefCheckbox", isOn: true) { _ in }
    }
    .padding(12)
    .frame(width: 680)
    .trainerSurface(.canvas)
    .trainerTheme(theme)
    .environmentObject(localization)

    let (win, host) = makeWindow(width: 700, height: 420, root: view)
    func ctrl(_ title: String) -> NativeAccessibilityControl? {
        nativeAccessibilityControls(host).first { $0.label == title && ($0.role == "AXCheckBox" || $0.role == "AXSwitch") }
    }
    let switchTitles = ["DefaultSwitch", "WaitingToggle", "PlainToggle", "WaitingMult", "PlainMult"]
    waitWindow(host, "switches mounted") {
        switchTitles.allSatisfy { ctrl($0) != nil } && ctrl("RefCheckbox") != nil
    }
    let cb = ctrl("RefCheckbox")!
    let cbRect = localRect(cb.frame, in: host, window: win)
    check(axSubrole(cb) != "AXToggle" || cbRect.width < 25, "RefCheckbox unexpectedly became a switch")

    // Each shared switch must have a regular-sized native control.
    let backingSwitches = nativeSwitches(in: host)
    check(backingSwitches.count == switchTitles.count,
          "expected \(switchTitles.count) native Switch NSControls, found \(backingSwitches.count)")
    for sw in backingSwitches {
        check(sw.controlSize == .regular,
              "TrainerToggleControl lost .controlSize(.regular): \(sw.controlSize.rawValue)")
    }

    let bitmap = rasterize(host)
    for title in switchTitles {
        let node = ctrl(title)!
        let r = localRect(node.frame, in: host, window: win)
        check(axSubrole(node) == "AXToggle",
              "\(title) lost switch subrole: subrole=\(String(describing: axSubrole(node))) role=\(String(describing: node.role))")
        check(r.width >= 30 && r.width <= 58 && r.height >= 16 && r.height <= 30,
              "\(title) lost regular switch or .fixedSize() compact dimensions: \(r) cb=\(cbRect)")
    }

    // Verify 40x40 TrainerIconLabel phase tint: orange for waiting vs purple for active.
    func badgeRectForRowTitle(_ text: String) -> NSRect {
        let t = localRect(namedNativeControl(host, role: "AXStaticText", name: text)!.frame, in: host, window: win)
        return NSRect(x: t.minX, y: t.midY - 20, width: 42, height: 40)
    }
    check(hasMatchingPixel(bitmap, in: badgeRectForRowTitle("WaitingToggle"), host: host, step: 0.5, matching: isOrange),
          "TrainerFeatureToggleRow waiting icon badge did not render warning orange tint")
    check(hasMatchingPixel(bitmap, in: badgeRectForRowTitle("PlainToggle"), host: host, step: 0.5, matching: isPurple),
          "TrainerFeatureToggleRow active icon badge did not render accent purple tint")
    check(hasMatchingPixel(bitmap, in: badgeRectForRowTitle("WaitingMult"), host: host, step: 0.5, matching: isOrange),
          "TrainerFeatureMultiplierRow waiting icon badge did not render warning orange tint")
    check(hasMatchingPixel(bitmap, in: badgeRectForRowTitle("PlainMult"), host: host, step: 0.5, matching: isPurple),
          "TrainerFeatureMultiplierRow active icon badge did not render accent purple tint")

    // Verify ShortcutBadgeSlot spacing inside WaitingMult vs PlainMult.
    let sc1 = localRect(nativeAccessibilityControls(host).first { $0.role == "AXStaticText" && $0.text == "⌃1" }!.frame, in: host, window: win)
    let waitToggleRect = localRect(ctrl("WaitingToggle")!.frame, in: host, window: win)
    let plainToggleRect = localRect(ctrl("PlainToggle")!.frame, in: host, window: win)
    let plainLabel = localRect(namedNativeControl(host, role: "AXStaticText", name: "PlainToggle")!.frame, in: host, window: win)
    check(waitToggleRect.minX - sc1.maxX >= 10 && sc1.width > 0, "WaitingToggle lost shortcut badge lane")
    check(plainToggleRect.minX - plainLabel.maxX > 200, "PlainToggle unexpectedly left shortcut gap")

    // Row height >= rowMinimumHeight, multiplier has "×" & numeric field, shortcut slot geometry.
    let multTexts = nativeAccessibilityControls(host).filter { $0.role == "AXStaticText" && $0.text == "×" }
    check(multTexts.count == 2, "multiplier rows lost × unit labels")
    check(textFields(in: host).count == 2, "multiplier rows lost numeric fields")

    win.contentView = nil
    win.close()
    print("scenario1_toggles_features_ok")
}

// MARK: - Scenario 2: TrainerRow, LabeledControlRow & PickerActionLayout

@MainActor
private func exerciseRowAndLayout(localization: TrainerLocalizationStore) {
    let theme = TrainerTheme.standard
    let view = VStack(alignment: .leading, spacing: 12) {
        TrainerRow {
            HStack {
                Text("RowContent").accessibilityIdentifier("row.label")
                Spacer()
                TrainerSecondaryActionButton(title: "Go") {}
                    .accessibilityIdentifier("row.autoAction")
            }
        }
        .background(FrameProbe("row.panel").allowsHitTesting(false).accessibilityHidden(true))

        TrainerLabeledControlRow(title: "NaturalTitle", icon: "flame", tint: theme.accent, emphasized: true) {
            Text("TrailingA").accessibilityIdentifier("natural.a")
            Text("TrailingB").accessibilityIdentifier("natural.b")
        }
        .background(FrameProbe("row.natural").allowsHitTesting(false).accessibilityHidden(true))
    }
    .padding(12)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .trainerSurface(.canvas)
    .trainerTheme(theme)
    .environmentObject(localization)

    let (win, host) = makeWindow(width: 760, height: 240, root: view)
    waitWindow(host, "rows mounted") {
        probeFrame("row.panel", in: host, to: host) != nil
            && nativeAccessibilityControls(host).contains { $0.identifier == "row.autoAction" }
            && nativeAccessibilityControls(host).contains { $0.identifier == "natural.a" }
            && nativeAccessibilityControls(host).contains { $0.identifier == "natural.b" }
    }
    let rowPanel = probeFrame("row.panel", in: host, to: host)!
    check(rowPanel.height >= theme.rowMinimumHeight - 1,
          "TrainerRow shorter than rowMinimumHeight: \(rowPanel.height)")
    let bitmap = rasterize(host)
    let canvasLuma = luminance(bitmap, ptX: 4, ptY: 4, host: host)
    let panelLuma = luminance(bitmap, ptX: rowPanel.minX + 4, ptY: rowPanel.midY, host: host)
    check(panelLuma > canvasLuma + 0.015,
          "TrainerRow lost theme.panel background: canvas=\(canvasLuma) panel=\(panelLuma)")

    let labelRect = localRect(nativeAccessibilityControls(host).first { $0.role == "AXStaticText" && $0.text == "RowContent" }!.frame, in: host, window: win)
    let actionRect = localRect(nativeAccessibilityControls(host).first { $0.identifier == "row.autoAction" }!.frame, in: host, window: win)
    check(abs((labelRect.minX - rowPanel.minX) - theme.rowHorizontalPadding) <= 2,
          "TrainerRow lost leading rowHorizontalPadding: \(labelRect.minX - rowPanel.minX)")
    check(abs((rowPanel.maxX - actionRect.maxX) - theme.rowHorizontalPadding) <= 2,
          "TrainerRow lost trailing rowHorizontalPadding: \(rowPanel.maxX - actionRect.maxX)")
    check(abs(actionRect.width - theme.compactActionWidth) <= 1.5,
          "TrainerRow did not propagate trainerActionWidth: \(actionRect.width)")

    // TrainerLabeledControlRow(.natural) spacing & 40x40 icon badge.
    let naturalPanel = probeFrame("row.natural", in: host, to: host)!
    let naturalTitle = localRect(nativeAccessibilityControls(host).first { $0.role == "AXStaticText" && $0.text == "NaturalTitle" }!.frame, in: host, window: win)
    let trailingA = localRect(nativeAccessibilityControls(host).first { $0.identifier == "natural.a" }!.frame, in: host, window: win)
    let trailingB = localRect(nativeAccessibilityControls(host).first { $0.identifier == "natural.b" }!.frame, in: host, window: win)
    check(naturalTitle.height >= theme.rowIconSize - 1 && naturalTitle.width >= theme.rowIconSize + theme.rowIconSpacing + 20,
          "TrainerIconLabel lost 40x40 icon box: \(naturalTitle)")
    check(abs((naturalTitle.minX - naturalPanel.minX) - theme.rowHorizontalPadding) <= 2,
          "TrainerLabeledControlRow lost leading padding: \(naturalTitle.minX - naturalPanel.minX)")
    check(hasMatchingPixel(bitmap, in: NSRect(x: naturalTitle.minX, y: naturalTitle.minY, width: 40, height: 40), host: host, step: 0.5, matching: isPurple),
          "TrainerIconLabel badge missing accent tint")
    check(trailingA.minX - naturalTitle.maxX >= 8, "TrainerLabeledControlRow lost minimum Spacer(minLength: 8)")
    check(abs((trailingB.minX - trailingA.maxX) - theme.rowContentSpacing) <= 2,
          "TrainerLabeledControlRow lost rowContentSpacing 16: gap=\(trailingB.minX - trailingA.maxX)")

    win.contentView = nil
    win.close()

    // PickerAction row width growth from 760pt to 1050pt (proves .buttonSizing(.flexible) on macOS 26+).
    var pickerWidths: [CGFloat] = []
    for width: CGFloat in [760, 1050] {
        let pickerRow = TrainerLabeledControlRow(title: "Reward", icon: "sparkles", tint: theme.accent,
                                                 emphasized: true, layout: .pickerAction) {
            Picker("Reward", selection: .constant("gold")) {
                Text("Small Gold").tag("gold")
            }
            .labelsHidden()
            .trainerPicker(.rowAction)
            .accessibilityIdentifier("layout.picker")
            TrainerShortcutBadgeSlot(text: "⌃1")
            TrainerSecondaryActionButton(title: "Apply", enabled: true) {}
                .accessibilityIdentifier("layout.apply")
        }
        .frame(width: width)
        .trainerSurface(.canvas)
        .trainerTheme(theme)
        .environmentObject(localization)

        let (pWin, pHost) = makeWindow(width: width, height: 120, root: pickerRow)
        waitWindow(pHost, "pickerAction row at \(width)") {
            nativeAccessibilityControls(pHost).contains { $0.identifier == "layout.picker" && $0.role == "AXPopUpButton" }
                && nativeAccessibilityControls(pHost).contains { $0.identifier == "layout.apply" && $0.role == "AXButton" }
        }
        let picker = localRect(nativeAccessibilityControls(pHost).first { $0.identifier == "layout.picker" }!.frame, in: pHost, window: pWin)
        let apply = localRect(nativeAccessibilityControls(pHost).first { $0.identifier == "layout.apply" }!.frame, in: pHost, window: pWin)
        let gap = apply.minX - picker.maxX
        let minExpectedGap = 16 + theme.shortcutBadgeMinimumWidth + 16
        check(picker.width >= theme.pickerStandardWidth - 2 && picker.width <= theme.pickerActionMaxWidth + 2,
              "rowAction picker escaped [216, 420] at width \(width): \(picker.width)")
        check(gap >= minExpectedGap - 2,
              "rowAction picker overlapped shortcut/action lane at \(width): gap=\(gap) min=\(minExpectedGap)")
        check(abs(apply.width - theme.compactActionWidth) <= 1.5, "rowAction button left 88pt column: \(apply.width)")
        pickerWidths.append(picker.width)
        pWin.contentView = nil
        pWin.close()
    }
    if #available(macOS 26.0, *) {
        check(pickerWidths[1] >= pickerWidths[0] + 24,
              "Picker .rowAction failed to expand flexibly from 760 to 1050: \(pickerWidths)")
    }
    print("scenario2_row_layout_ok")
}

// MARK: - Scenario 3: Metric Cards, Stat Controls, Lock Button

@MainActor
private final class MetricGridFixtureState: ObservableObject {
    @Published var current = "50"
    @Published var maximum = "100"
    @Published var amount = "25"
    @Published var counter = "3"
    @Published var stat = "12"
    @Published var mult = "1.5"
    @Published var focus: String? = nil
    @Published var vitalLocked = false
    var resets = 0
}

private struct MetricGridFixtureView: View {
    @Environment(\.trainerTheme) private var theme
    @ObservedObject var state: MetricGridFixtureState

    var body: some View {
        let grid = TrainerMetricGrid {
            TrainerVitalMetricCard(title: "Vital", icon: "heart.fill", tint: .pink,
                current: $state.current, maximum: $state.maximum, focus: $state.focus,
                currentField: "cur", maximumField: "max",
                locked: state.vitalLocked, editable: true, onLock: { state.vitalLocked.toggle() })
            TrainerAmountMetricCard(title: "Gold", icon: "banknote.fill", tint: .yellow,
                text: $state.amount, focus: $state.focus, focusValue: "amt", locked: false, editable: true, onLock: {})
            TrainerStatMetricCard(title: "StatOK", icon: "gauge.medium", text: $state.stat,
                focus: $state.focus, focusValue: "statok", suffix: "%", locked: true,
                supported: true, available: true, editable: true, onLock: {})
            TrainerStatMetricCard(title: "StatOff", icon: "gauge.low", text: $state.stat,
                focus: $state.focus, focusValue: "statoff", suffix: "%", locked: false,
                supported: true, available: false, editable: true, onLock: {})
            TrainerMultiplierMetricCard(title: "Dmg", icon: "flame.fill", text: $state.mult,
                focus: $state.focus, focusValue: "mult", suffix: "×", editable: true)
            TrainerCounterMetricCard(title: "This is a much longer wrapped metric card title", icon: "bolt.fill",
                tint: theme.accent, text: $state.counter, focus: $state.focus, focusValue: "cnt", detail: nil, editable: true)
            TrainerCounterMetricCard(title: "ResetSibling", icon: "star.fill",
                tint: theme.accent, text: $state.counter, focus: $state.focus, focusValue: "cnt2", detail: nil, editable: true)
        }
        return VStack(alignment: .leading, spacing: 12) {
            grid
            TrainerResetButton(title: "ResetRef", enabled: true) { state.resets += 1 }
                .accessibilityIdentifier("card.resetRef")
        }
        .frame(width: 780)
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .trainerSurface(.canvas)
    }
}

@MainActor
private func exerciseCardsStatsLocks(localization: TrainerLocalizationStore) {
    let theme = TrainerTheme.standard
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        let state = MetricGridFixtureState()

        let (win, host) = makeWindow(
            width: 820, height: 420,
            root: MetricGridFixtureView(state: state)
                .trainerTheme(theme)
                .environmentObject(localization)
        )
        let lockVitalLabel = localization.localized("host.lockValue", arguments: ["Vital"])
        let statLockLabel = localization.localized("host.unlockValue", arguments: ["StatOK"])
        waitWindow(host, "metric grid mounted in \(language)") {
            namedNativeControl(host, role: "AXButton", name: lockVitalLabel) != nil
                && namedNativeControl(host, role: "AXButton", name: statLockLabel) != nil
                && nativeAccessibilityControls(host).contains { $0.identifier == "card.resetRef" }
                && textFields(in: host).count == 8
        }

        check(!nativeAccessibilityControls(host).contains {
            $0.role == "AXSwitch" || $0.role == "AXCheckBox" || axSubrole($0) == "AXToggle"
        }, "TrainerStatControls or metric grid rendered a toggle")

        // Field widths & vital "/" spacing (alignmentRect strips AppKit's 2pt focus/bezel outset).
        let fields = textFields(in: host)
        let curField = fields.first { $0.stringValue == "50" }!
        let maxField = fields.first { $0.stringValue == "100" }!
        let curRect = curField.alignmentRect(forFrame: curField.convert(curField.bounds, to: host))
        let maxRect = maxField.alignmentRect(forFrame: maxField.convert(maxField.bounds, to: host))
        check(abs(curRect.width - 54) <= 2 && abs(maxRect.width - 54) <= 2,
              "TrainerVitalMetricCard field widths changed: \(curRect.width), \(maxRect.width)")
        check(maxRect.minX - curRect.maxX <= 18, "TrainerVitalMetricCard '/' spacing widened")

        let statFields = fields.filter { $0.accessibilityLabel() == "StatOK" || $0.accessibilityLabel() == "StatOff" }
        check(statFields.count == 2 && statFields.allSatisfy {
            abs($0.alignmentRect(forFrame: $0.convert($0.bounds, to: host)).width - theme.compactFieldWidth) <= 2
        }, "TrainerStatMetricCard lost compactFieldWidth 58")
        check(fields.first { $0.accessibilityLabel() == "StatOff" }?.isEnabled == false,
              "unavailable StatMetricCard kept field enabled")
        check(namedNativeControl(host, role: "AXButton",
              name: localization.localized("host.lockValue", arguments: ["StatOff"]))?.enabled == false,
              "unavailable StatMetricCard kept lock button enabled")

        let multField = fields.first { $0.accessibilityLabel() == "Dmg" }!
        let multFieldRect = multField.alignmentRect(forFrame: multField.convert(multField.bounds, to: host))
        check(abs(multFieldRect.width - theme.compactFieldWidth) <= 2,
              "TrainerMultiplierMetricCard lost compactFieldWidth 58: \(multFieldRect.width)")
        let multSuffix = localRect(nativeAccessibilityControls(host).first {
            $0.role == "AXStaticText" && $0.text == "×"
        }!.frame, in: host, window: win)
        check(multSuffix.minX - multFieldRect.maxX >= 1 && multSuffix.minX - multFieldRect.maxX <= 7,
              "TrainerMetricStatField suffix gap drifted: \(multSuffix.minX - multFieldRect.maxX)")

        // Lock button sizing, borderless pixels vs bordered ResetButton, painted card bounds & padding.
        let lockBtn = namedNativeControl(host, role: "AXButton", name: lockVitalLabel)!
        let lockRect = localRect(lockBtn.frame, in: host, window: win)
        check(abs(lockRect.width - 26) <= 1.5 && abs(lockRect.height - 24) <= 1.5,
              "TrainerLockButton lost 26x24 frame: \(lockRect)")
        check(lockBtn.help == lockVitalLabel, "TrainerLockButton lost localized help")

        let bitmap = rasterize(host)
        let canvasLuma = luminance(bitmap, ptX: 4, ptY: 4, host: host)
        let goldTitle = localRect(nativeAccessibilityControls(host).first {
            $0.role == "AXStaticText" && $0.text == "Gold"
        }!.frame, in: host, window: win)
        let goldCard = measureCardPaintedBounds(bitmap: bitmap, host: host, probeX: goldTitle.minX, insideY: goldTitle.midY, canvasLuma: canvasLuma)
        check(goldCard.height < 76, "TrainerMetricCard re-introduced minHeight >= 82 strip: \(goldCard.height)")
        let topGap = lockRect.minY - goldCard.minY
        check(topGap >= 4.5 && topGap <= 7.5,
              "TrainerMetricCard lost .padding(.top, 6): topGap=\(topGap)")
        let amtField = fields.first { $0.stringValue == "25" }!
        let amtRect = amtField.alignmentRect(forFrame: amtField.convert(amtField.bounds, to: host))
        let bottomGap = goldCard.maxY - amtRect.maxY
        check(bottomGap >= 6.0 && bottomGap <= 11.0,
              "TrainerMetricCard lost .padding(.bottom, 8): bottomGap=\(bottomGap)")

        // Mixed-height row 1 (wrapped long title vs single-line "Dmg").
        let dmgTitle = localRect(nativeAccessibilityControls(host).first {
            $0.role == "AXStaticText" && $0.text == "Dmg"
        }!.frame, in: host, window: win)
        let dmgCard = measureCardPaintedBounds(bitmap: bitmap, host: host, probeX: dmgTitle.minX, insideY: dmgTitle.midY, canvasLuma: canvasLuma)
        let wrapTitle = localRect(nativeAccessibilityControls(host).first {
            $0.role == "AXStaticText" && ($0.text ?? "").contains("wrapped metric")
        }!.frame, in: host, window: win)
        let wrapCard = measureCardPaintedBounds(bitmap: bitmap, host: host, probeX: wrapTitle.minX, insideY: wrapTitle.midY, canvasLuma: canvasLuma)
        check(abs(dmgCard.height - wrapCard.height) <= 1.5,
              "TrainerMetricCard lost maxHeight: .infinity equal-height stretching: \(dmgCard.height) vs \(wrapCard.height)")
        let goldTitleTopGap = goldTitle.minY - goldCard.minY
        let dmgTopGap = dmgTitle.minY - dmgCard.minY
        check(abs(dmgTopGap - goldTitleTopGap) <= 1.5,
              "TrainerMetricCard lost topLeading alignment in stretched row: dmgTopGap=\(dmgTopGap) gold=\(goldTitleTopGap)")

        // Borderless LockButton outer edge matches panel, unlike bordered ResetButton.
        let panelEmptyLuma = luminance(bitmap, ptX: goldTitle.minX + 4, ptY: goldCard.maxY - 3, host: host)
        let lockOuterEdgeLuma = luminance(bitmap, ptX: lockRect.minX + 1, ptY: lockRect.midY, host: host)
        let resetCtrl = nativeAccessibilityControls(host).first { $0.identifier == "card.resetRef" }!
        let resetRect = localRect(resetCtrl.frame, in: host, window: win)
        let resetCornerLuma = luminance(bitmap, ptX: resetRect.minX + 1, ptY: resetRect.midY, host: host)
        check(resetCornerLuma > canvasLuma + 0.05,
              "ResetButton positive bordered control check failed: reset=\(resetCornerLuma) canvas=\(canvasLuma)")
        check(abs(lockOuterEdgeLuma - panelEmptyLuma) < 0.015,
              "TrainerLockButton drew a border instead of .plain: panel=\(panelEmptyLuma) edge=\(lockOuterEdgeLuma)")

        // AX press toggles lock.
        check(lockBtn.press(), "TrainerLockButton refused AX press")
        let unlockedLabel = localization.localized("host.unlockValue", arguments: ["Vital"])
        waitWindow(host, "lock button updates label after toggle") {
            state.vitalLocked && namedNativeControl(host, role: "AXButton", name: unlockedLabel) != nil
        }

        win.contentView = nil
        win.close()
    }
    print("scenario3_cards_stats_locks_ok")
}

// MARK: - Scenario 4: Action Buttons, Badges, Section Button, Connection Card, Workbench Bar

@MainActor
private func exerciseButtonsBadgesSections(localization: TrainerLocalizationStore) {
    localization.language = .en
    let theme = TrainerTheme.standard
    check(theme.selectionMarkerWidth(for: .standard) == 2 && theme.selectionMarkerWidth(for: .increased) == 3,
          "selectionMarkerWidth contrast policy drifted")
    var selectedClicks = 0
    var search = "Potion"
    let sBinding = Binding(get: { search }, set: { search = $0 })

    let view = VStack(alignment: .leading, spacing: 10) {
        HStack(spacing: 8) {
            TrainerPrimaryActionButton(title: "Save", widthRole: .sheet) {}
                .accessibilityIdentifier("btn.primarySheet")
            TrainerSecondaryActionButton(title: "Very Long Action Label Text", widthRole: .compactRow) {}
                .accessibilityIdentifier("btn.longCompact")
            TrainerSecondaryActionButton(title: "DisableEffects", widthRole: .compactRow) {}
                .accessibilityIdentifier("btn.scaleCompact")
            TrainerSecondaryActionButton(title: "Go", widthRole: .compactRow) {}
                .accessibilityIdentifier("btn.shortCompact")
            TrainerSecondaryActionButton(title: "Standalone") {}
                .accessibilityIdentifier("btn.standalone")
        }
        TrainerConnectionStatusCard(
            connected: false, backendAvailable: true, actionsEnabled: true, restartEnabled: true,
            onRefresh: {}, onPrimary: {}, onRestart: {}
        )
        VStack(alignment: .leading, spacing: 2) {
            TrainerSectionButton(title: "SelectedSec", systemImage: "heart", selected: true) {
                selectedClicks += 1
            }.accessibilityIdentifier("sec.selected")
            TrainerSectionButton(title: "PlainSec", systemImage: "star", selected: false) {}
                .accessibilityIdentifier("sec.unselected")
        }
        .padding(.horizontal, 20)
        .frame(width: 240)
        HStack(spacing: 0) {
            Text("[")
            TrainerShortcutBadge(text: "⌃1")
            TrainerShortcutBadgeSlot(text: "⌃2")
            TrainerShortcutBadgeSlot(text: nil)
            TrainerShortcutBadgeSlot(text: "")
            TrainerShortcutBadgeSlot(text: "⌃⌥⇧⌘ F12 + Space")
            Text("]")
        }
        TrainerSaveEditorWorkbenchBar(
            search: sBinding, searchPlaceholder: "Search saves", clearLabel: "Clear saves",
            searchEnabled: true, loading: false, onSubmit: {}, scope: { EmptyView() }, trailing: { EmptyView() }
        )
    }
    .padding(16)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .trainerSurface(.canvas)
    .trainerTheme(theme)
    .environmentObject(localization)

    let (win, host) = makeWindow(width: 700, height: 420, root: view)
    func btn(_ id: String) -> NativeAccessibilityControl? {
        nativeAccessibilityControls(host).first { $0.identifier == id && $0.role == "AXButton" }
    }
    let connectTitle = localization.localized("host.connectGame")
    waitWindow(host, "buttons/badges/sections mounted") {
        btn("btn.primarySheet") != nil && btn("btn.longCompact") != nil
            && btn("btn.scaleCompact") != nil && btn("btn.shortCompact") != nil
            && btn("btn.standalone") != nil
            && btn("sec.selected") != nil
            && namedNativeControl(host, role: "AXButton", name: connectTitle) != nil
            && nativeAccessibilityControls(host).contains { $0.identifier == "trainer.search.clear" }
    }

    // Labeled action buttons are text-only (no AXImage and no leading icon inflating standalone width).
    for id in ["btn.primarySheet", "btn.shortCompact", "btn.standalone"] {
        let images = nativeAccessibilityControls(btn(id)!.object).filter { $0.role == "AXImage" }
        check(images.isEmpty, "labeled action button rendered an unexpected symbol image: \(id)")
    }
    let standaloneFrame = localRect(btn("btn.standalone")!.frame, in: host, window: win)
    check(standaloneFrame.width < 102,
          "TrainerActionButtonLabel grew wider than text-only button (unexpected leading icon): width=\(standaloneFrame.width)")

    // Long compact labels preserve the button's single-line height.
    let longFrame = localRect(btn("btn.longCompact")!.frame, in: host, window: win)
    let scaleFrame = localRect(btn("btn.scaleCompact")!.frame, in: host, window: win)
    let shortFrame = localRect(btn("btn.shortCompact")!.frame, in: host, window: win)
    check(longFrame.height <= shortFrame.height + 1.0 && abs(longFrame.width - theme.compactActionWidth) <= 1.5,
          "TrainerActionButtonLabel wrapped or grew past compactActionWidth: long=\(longFrame) short=\(shortFrame)")

    // Connection card uses TrainerPrimaryActionButton(widthRole: .connection) + bordered bezel (not plain).
    let connectBtn = namedNativeControl(host, role: "AXButton", name: connectTitle)!
    let connectRect = localRect(connectBtn.frame, in: host, window: win)
    check(abs(connectRect.width - theme.connectionActionWidth) <= 2,
          "TrainerConnectionStatusCard primary button lost connectionActionWidth 160: \(connectRect.width)")

    // Selected TrainerSectionButton: still clickable, leading purple marker, and .focusEffectDisabled() (no _FocusRingView).
    let selSec = btn("sec.selected")!
    let unselSec = btn("sec.unselected")!
    check(selSec.selected && !unselSec.selected, "TrainerSectionButton selection trait mismatch")
    check(selSec.press(), "selected TrainerSectionButton refused AX press (overlay outside plain button)")
    waitUntil("selected TrainerSectionButton press fires") { selectedClicks == 1 }

    let ringRects = focusRingViews(in: host).map { $0.convert($0.bounds, to: host) }
    let selRect = localRect(selSec.frame, in: host, window: win)
    let unselRect = localRect(unselSec.frame, in: host, window: win)
    check(ringRects.contains { $0.intersects(shortFrame) },
          "focusRingViews detector did not observe focusable TrainerSecondaryActionButton")
    check(!ringRects.contains { $0.intersects(selRect) || $0.intersects(unselRect) },
          "TrainerSectionButton gained an unwanted focus ring behind chevron: \(ringRects)")

    let bitmap = rasterize(host)
    func brightGlyphHeight(in rect: NSRect) -> CGFloat {
        var minY: CGFloat = 999, maxY: CGFloat = 0
        var x = rect.minX + 3
        while x <= rect.maxX - 3 {
            var y = rect.minY + 3
            while y <= rect.maxY - 3 {
                if luminance(bitmap, ptX: x, ptY: y, host: host) > 0.5 {
                    minY = min(minY, y); maxY = max(maxY, y)
                }
                y += 0.5
            }
            x += 0.5
        }
        return maxY - minY
    }
    let shortTextH = brightGlyphHeight(in: shortFrame)
    let scaleTextH = brightGlyphHeight(in: scaleFrame)
    check(shortTextH >= 9.0 && scaleTextH > 5.0 && scaleTextH <= shortTextH - 1.0,
          "TrainerActionButtonLabel minimumScaleFactor(0.78) did not scale text: short=\(shortTextH) scale=\(scaleTextH)")

    let canvasLuma = luminance(bitmap, ptX: 4, ptY: 4, host: host)
    let connectFillLuma = luminance(bitmap, ptX: connectRect.minX + 6, ptY: connectRect.midY, host: host)
    check(connectFillLuma > canvasLuma + 0.08,
          "TrainerConnectionStatusCard primary button lost filled borderedProminent bezel: luma=\(connectFillLuma) canvas=\(canvasLuma)")

    // Leading capsule at offset(x: -12) expands selRect's leading edge by ~12pt compared to unselRect.
    check(selRect.width >= unselRect.width + 8 && abs(selRect.maxX - unselRect.maxX) <= 1.5,
          "selected TrainerSectionButton missing leading offset marker expansion: sel=\(selRect) unsel=\(unselRect)")
    let step: CGFloat = 0.5
    let markerSamples = stride(from: selRect.minX - 2, through: selRect.minX + 10, by: step).filter { x in
        isPurple(rgba(bitmap, ptX: x, ptY: selRect.midY, host: host))
    }
    let markerWidth = CGFloat(markerSamples.count) * step
    let contrast: ColorSchemeContrast = NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast ? .increased : .standard
    let expectedMarkerWidth = theme.selectionMarkerWidth(for: contrast)
    check(abs(markerWidth - expectedMarkerWidth) <= 0.75,
          "selected section marker painted \(markerWidth) points; expected \(expectedMarkerWidth)")
    let unselMarkerRect = NSRect(x: unselRect.minX - 15, y: unselRect.minY + 6, width: 12, height: unselRect.height - 12)
    check(!hasMatchingPixel(bitmap, in: unselMarkerRect, host: host, step: 0.5, matching: isPurple),
          "unselected TrainerSectionButton drew leading marker")

    // Shortcut badge slots: nil and "" collapse to zero gap.
    func textRect(_ value: String) -> NSRect {
        localRect(nativeAccessibilityControls(host).first { $0.role == "AXStaticText" && $0.text == value }!.frame, in: host, window: win)
    }
    let openBr = textRect("[")
    let b1 = textRect("⌃1")
    let b2 = textRect("⌃2")
    let bLong = textRect("⌃⌥⇧⌘ F12 + Space")
    let slot2MidToB1Mid = b2.midX - b1.midX
    check(abs(slot2MidToB1Mid - theme.shortcutBadgeMinimumWidth) <= 2,
          "direct and slotted badges disagree on 52pt lane: delta=\(slot2MidToB1Mid)")
    check(b1.midX - openBr.maxX >= 20, "badge minimum width collapsed")
    let collapsedGap = bLong.minX - (b2.midX + theme.shortcutBadgeMinimumWidth / 2)
    check(collapsedGap >= -2 && collapsedGap <= 10,
          "nil or empty TrainerShortcutBadgeSlot left a phantom gap: \(collapsedGap)")

    // TrainerSaveEditorWorkbenchBar uses TrainerSearchField with clear button.
    let wbClear = nativeAccessibilityControls(host).first { $0.identifier == "trainer.search.clear" }!
    check(wbClear.label == "Clear saves" && wbClear.press(), "workbench clear button refused press")
    waitUntil("workbench clear empties search") { search.isEmpty }

    win.contentView = nil
    win.close()
    print("scenario4_buttons_badges_sections_ok")
}

// MARK: - Scenario 5: TrainerResourceControls

private struct ResourceOption: Identifiable {
    let id: String
    let title: String
}

@MainActor
private final class ResourceFixtureState: ObservableObject {
    @Published var search = "Gem"
    @Published var selection = "gems"
    @Published var amount = "50"
    @Published var locked = false
    @Published var enabled = true
    var actionCalls = 0
}

private struct ResourceFixtureView: View {
    @ObservedObject var state: ResourceFixtureState
    let options = [TrainerPickerSection(id: 0, title: "Cur", items: [ResourceOption(id: "gems", title: "Gems")])]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TrainerResourceEditor(
                title: "LockedRes", icon: "bag.fill",
                search: $state.search, selection: $state.selection, amount: $state.amount,
                sections: options, enabled: state.enabled,
                lock: TrainerResourceLock(locked: state.locked, toggle: { state.locked.toggle() }),
                itemLabel: { $0.title }
            )
            TrainerResourceEditor(
                title: "LocklessRes", icon: "cube.fill",
                search: .constant(""), selection: $state.selection, amount: $state.amount,
                sections: options, enabled: state.enabled, lock: nil,
                itemLabel: { $0.title }
            )
            TrainerGroupedOptionPicker(
                title: "InlineActive", icon: "wand.and.stars", pickerLabel: "InlinePicker",
                selection: $state.selection, sections: options,
                enabled: state.enabled, inline: true, emptyLabel: "Empty", actionTitle: "Spawn", shortcutText: nil,
                itemLabel: { $0.title }, onAction: { _ in state.actionCalls += 1 }
            )
            TrainerGroupedOptionPicker(
                title: "InlineBlocked", icon: "moon.fill", pickerLabel: "BlockedActionPicker",
                selection: $state.selection, sections: options,
                enabled: true, actionEnabled: false, inline: true, emptyLabel: "Empty", actionTitle: "Blocked", shortcutText: nil,
                itemLabel: { $0.title }, onAction: { _ in }
            )
            TrainerGroupedOptionPicker(
                title: "StackedOption", icon: "sparkles", pickerLabel: "StackedPicker",
                selection: $state.selection, sections: options,
                enabled: true, inline: false, emptyLabel: "Empty", actionTitle: "Run", shortcutText: nil,
                itemLabel: { $0.title }, onAction: { _ in }
            )
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .trainerSurface(.canvas)
    }
}

@MainActor
private func exerciseResourceControls(localization: TrainerLocalizationStore) {
    localization.language = .en
    let theme = TrainerTheme.standard
    let state = ResourceFixtureState()

    let (win, host) = makeWindow(
        width: 750, height: 500,
        root: ResourceFixtureView(state: state)
            .trainerTheme(theme)
            .environmentObject(localization)
    )
    let lockLabel = localization.localized("host.lockValue", arguments: ["LockedRes"])
    let unlockLabel = localization.localized("host.unlockValue", arguments: ["LockedRes"])
    let noLockLabel = localization.localized("host.lockValue", arguments: ["LocklessRes"])
    waitWindow(host, "resource controls mounted") {
        nativeAccessibilityControls(host).contains { $0.identifier == "trainer.search.clear" }
            && nativeAccessibilityControls(host).filter { $0.role == "AXPopUpButton" }.count == 5
            && namedNativeControl(host, role: "AXButton", name: "Spawn")?.enabled == true
            && namedNativeControl(host, role: "AXPopUpButton", name: "BlockedActionPicker")?.enabled == true
            && namedNativeControl(host, role: "AXButton", name: "Blocked")?.enabled == false
            && namedNativeControl(host, role: "AXButton", name: lockLabel) != nil
    }
    check(namedNativeControl(host, role: "AXButton", name: noLockLabel) == nil,
          "lockless TrainerResourceEditor unexpectedly rendered a lock button")

    // Lock button toggles state.locked on AX press.
    check(namedNativeControl(host, role: "AXButton", name: lockLabel)!.press(),
          "TrainerResourceEditor lock button refused AX press")
    waitWindow(host, "resource lock toggled") {
        state.locked && namedNativeControl(host, role: "AXButton", name: unlockLabel) != nil
    }

    // Inline vs stacked geometry.
    let inlineTitle = localRect(namedNativeControl(host, role: "AXStaticText", name: "InlineActive")!.frame, in: host, window: win)
    let inlinePicker = localRect(namedNativeControl(host, role: "AXPopUpButton", name: "InlinePicker")!.frame, in: host, window: win)
    let inlineBtn = localRect(namedNativeControl(host, role: "AXButton", name: "Spawn")!.frame, in: host, window: win)
    check(abs(inlineTitle.midY - inlinePicker.midY) < 12 && inlineTitle.maxX < inlinePicker.minX && inlinePicker.maxX < inlineBtn.minX,
          "inline TrainerGroupedOptionPicker is not laid out horizontally")

    let stackTitle = localRect(namedNativeControl(host, role: "AXStaticText", name: "StackedOption")!.frame, in: host, window: win)
    let stackPicker = localRect(namedNativeControl(host, role: "AXPopUpButton", name: "StackedPicker")!.frame, in: host, window: win)
    check(stackPicker.minY > stackTitle.maxY + 2,
          "non-inline TrainerGroupedOptionPicker did not stack picker below title")

    // The badge reflects the selected action's availability even while the picker stays enabled.
    let bitmap = rasterize(host)
    let activeBadgeRect = NSRect(x: inlineTitle.minX, y: inlineTitle.midY - 20, width: 42, height: 40)
    let blockedTitle = localRect(namedNativeControl(host, role: "AXStaticText", name: "InlineBlocked")!.frame, in: host, window: win)
    let blockedBadgeRect = NSRect(x: blockedTitle.minX, y: blockedTitle.midY - 20, width: 42, height: 40)
    check(hasMatchingPixel(bitmap, in: activeBadgeRect, host: host, step: 0.5, matching: isPurple),
          "active TrainerGroupedOptionPicker icon badge did not use theme.accent")
    check(!hasMatchingPixel(bitmap, in: blockedBadgeRect, host: host, step: 0.5, matching: isPurple),
          "blocked TrainerGroupedOptionPicker action kept a purple icon badge")
    check(hasMatchingPixel(bitmap, in: blockedBadgeRect.insetBy(dx: 10, dy: 8), host: host, step: 0.5) { color in
        let maximum = max(color.redComponent, color.greenComponent, color.blueComponent)
        let minimum = min(color.redComponent, color.greenComponent, color.blueComponent)
        return minimum > 0.3 && maximum - minimum < 0.08
    }, "blocked TrainerGroupedOptionPicker action lost its neutral icon glyph")

    // Clicking Spawn invokes onAction; clear button clears ResourceEditor search.
    check(namedNativeControl(host, role: "AXButton", name: "Spawn")!.press(), "Spawn refused press")
    check(nativeAccessibilityControls(host).first { $0.identifier == "trainer.search.clear" }!.press(), "Resource clear refused press")
    waitUntil("spawn and resource clear applied") { state.actionCalls == 1 && state.search.isEmpty }

    state.enabled = false
    waitWindow(host, "disabled resource controls disable their pickers, amount, and action") {
        let lockedPicker = namedNativeControl(host, role: "AXPopUpButton", name: "LockedRes")
        let amtFields = textFields(in: host).filter { $0.stringValue == "50" }
        return lockedPicker?.enabled == false && !amtFields.isEmpty && amtFields.allSatisfy { !$0.isEnabled }
            && namedNativeControl(host, role: "AXPopUpButton", name: "InlinePicker")?.enabled == false
            && namedNativeControl(host, role: "AXButton", name: "Spawn")?.enabled == false
    }

    win.contentView = nil
    win.close()
    print("scenario5_resource_controls_ok")
}

// MARK: - Scenario 6: DisclosureButton, ProfileManagerWarning, Picker, WorkbenchSearchPopover

private struct SearchEntry: Identifiable {
    let id: String
    let title: String
    let detail: String
    let icon: String
}

@MainActor
private final class DisclosureAndSearchModel: ObservableObject {
    @Published var expanded = false
    @Published var query = ""
}

private struct DisclosureSearchFixture: View {
    @ObservedObject var state: DisclosureAndSearchModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Leave room below the search anchor for the native popover.
            TrainerWorkbenchSearchField(
                text: $state.query,
                placeholder: "SearchWorkbench", clearLabel: "ClearWB", emptyLabel: "NoResults",
                search: { q in q.isEmpty ? [] : [SearchEntry(id: "e1", title: "Health", detail: "Vital", icon: "heart")] },
                title: { $0.title }, detail: { $0.detail }, icon: { $0.icon }, onNavigate: { _ in }
            )
            .frame(width: 320)

            HStack {
                TrainerDisclosureButton(
                    isExpanded: $state.expanded,
                    expandTitle: "ShowMore", collapseTitle: "ShowLess"
                )
                .accessibilityIdentifier("disc.btn")
                Spacer()
            }
            .padding(.horizontal, 16)

            TrainerProfileManagerView(
                labels: TrainerProfileManagerLabels(
                    title: "Profiles", explanation: "Manage profiles",
                    name: "Name", picker: "Saved", save: "SaveProfile", load: "LoadProfile", empty: "None"
                ),
                entries: [TrainerProfileEntry(name: "One", updatedAt: "Today")],
                busy: false, enabled: true,
                warning: "Hotkeys bound to active profiles will be overwritten on next save and reloaded immediately.",
                actions: TrainerProfileManagerActions(refresh: {}, save: { _, cb in cb(true) }, load: { _ in }, delete: { _ in }, dismiss: {})
            )
            .frame(width: 360)

            HStack(spacing: 12) {
                Picker("CompactP", selection: .constant("a")) { Text("A").tag("a") }
                    .labelsHidden()
                    .trainerPicker(.compactValue, state: .interactive)
                    .background(FrameProbe("picker.compact.alloc").allowsHitTesting(false).accessibilityHidden(true))
                    .accessibilityIdentifier("picker.compact")
                Picker("StandardP", selection: .constant("b")) { Text("B").tag("b") }
                    .labelsHidden()
                    .trainerPicker(.rowValue, state: .unavailable)
                    .background(FrameProbe("picker.standard.alloc").allowsHitTesting(false).accessibilityHidden(true))
                    .accessibilityIdentifier("picker.standardDisabled")
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .trainerSurface(.canvas)
    }
}

@MainActor
private func exerciseDisclosureProfilePickerPopover(localization: TrainerLocalizationStore) {
    localization.language = .en
    let theme = TrainerTheme.standard
    let state = DisclosureAndSearchModel()

    let (win, host) = makeWindow(
        width: 720, height: 680,
        root: DisclosureSearchFixture(state: state)
            .trainerTheme(theme)
            .environmentObject(localization)
    )
    func ctrl(_ id: String) -> NativeAccessibilityControl? {
        nativeAccessibilityControls(host).first { $0.identifier == id }
    }
    waitWindow(host, "disclosure/profile/picker/search mounted") {
        ctrl("disc.btn") != nil && ctrl("picker.compact") != nil && ctrl("picker.standardDisabled") != nil
            && probeFrame("picker.compact.alloc", in: host, to: host) != nil
            && probeFrame("picker.standard.alloc", in: host, to: host) != nil
            && textFields(in: host).contains { $0.placeholderString == "SearchWorkbench" }
    }

    // DisclosureButton: collapsed value + edge click inside padded Rectangle() contentShape toggles expanded.
    let discBtn = ctrl("disc.btn")!
    check(discBtn.valueText == localization.localized("host.disclosure.collapsed"),
          "disclosure button initial AX value wrong: \(String(describing: discBtn.valueText))")
    let discRect = localRect(discBtn.frame, in: host, window: win)
    // Click the top-right padding corner (outside the glyph & circular chevron) so only .contentShape(Rectangle()) covers it.
    clickLocal(NSPoint(x: discRect.maxX - 1, y: discRect.minY + 1), in: win, host: host)
    waitWindow(host, "disclosure edge click toggles expanded") {
        state.expanded && ctrl("disc.btn")?.valueText == localization.localized("host.disclosure.expanded")
    }

    // ProfileManagerView warning wraps + warm orange color, prominent Save/Load.
    let warnNode = nativeAccessibilityControls(host).first {
        $0.role == "AXStaticText" && ($0.text ?? "").contains("overwritten on next save")
    }!
    let warnRect = localRect(warnNode.frame, in: host, window: win)
    check(warnRect.height > 20, "profile warning did not wrap onto multiple lines: \(warnRect)")
    let bitmap = rasterize(host)
    check(hasMatchingPixel(bitmap, in: warnRect, host: host, step: 1.0, matching: isOrange),
          "profile warning text did not render in theme.warning orange")

    // Picker states & role widths.
    let compactPicker = ctrl("picker.compact")!
    let standardPicker = ctrl("picker.standardDisabled")!
    check(compactPicker.enabled && !standardPicker.enabled, "Picker state availability mismatch")
    let compactAlloc = probeFrame("picker.compact.alloc", in: host, to: host)!
    let standardAlloc = probeFrame("picker.standard.alloc", in: host, to: host)!
    check(abs(compactAlloc.width - theme.pickerCompactWidth) <= 1.5
          && abs(standardAlloc.width - theme.pickerStandardWidth) <= 1.5,
          "Picker role width allocation mismatch: compact=\(compactAlloc.width) standard=\(standardAlloc.width)")

    // Center the anchor on roomy displays. On shorter displays, reserve
    // room below for the 312-point result viewport and its native chrome.
    let wbField = textFields(in: host).first { $0.placeholderString == "SearchWorkbench" }!
    guard let display = win.screen ?? NSScreen.main else {
        fatalError("workbench search fixture needs a display")
    }
    let inputInWindow = wbField.convert(wbField.bounds, to: nil)
    let inputBeforeMove = win.convertToScreen(inputInWindow)
    let windowOrigin = win.frame.origin
    let anchorY = max(display.visibleFrame.midY, display.visibleFrame.minY + 380)
    win.setFrameOrigin(NSPoint(x: windowOrigin.x, y: windowOrigin.y + anchorY - inputBeforeMove.midY))
    let inputScreen = win.convertToScreen(inputInWindow)
    check(win.makeFirstResponder(wbField), "workbench field refused firstResponder")
    if let tv = wbField.currentEditor() as? NSTextView {
        tv.insertText("Health", replacementRange: tv.selectedRange())
    }
    func findPopoverWindow() -> NSWindow? {
        NSApp.windows.first { candidate in
            candidate !== win && candidate.isVisible && candidate.contentView.map {
                nativeAccessibilityControls($0).contains { $0.identifier == "trainer.workbench.result.e1" }
            } == true
        }
    }
    waitWindow(host, "workbench search popover appears below field") {
        findPopoverWindow() != nil
    }
    let popoverWin = findPopoverWindow()!
    check(popoverWin.frame.maxY <= inputScreen.minY + 18,
          "workbench popover did not present below input: popover=\(popoverWin.frame) input=\(inputScreen) display=\(display.visibleFrame)")

    popoverWin.close()
    win.contentView = nil
    win.close()
    print("scenario6_disclosure_profile_picker_popover_ok")
}

// MARK: - Scenario 7: TrainerSidebarCard & TrainerGamePages

final class StubPageModel: ObservableObject, TrainerHostModel {
    var connected: Bool { false }
    var statusTitle: TrainerTextToken { .init(key: "host.disconnected") }
    var connectionDetailText: TrainerTextToken { .init(key: "host.disconnected") }
    var hostActionsEnabled: Bool { true }
    func connectFromHost(reason: TrainerHostConnectReason) {}
    func disconnectFromHost() {}
    func refreshFromHost() {}
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
    func prepareForTermination(completion: @escaping () -> Void) { completion() }
}

private struct StubPageModuleA: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "stubA", displayName: "Stub A",
        targetProcessName: "NoneA", targetBundleIdentifier: "test.none.a",
        expectedHostProtocolVersion: 1, expectedModuleProtocolVersion: 1, supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation()
    static func makeModel(services: TrainerModuleServices) -> StubPageModel { StubPageModel() }
    static var pageATaps = 0
    static func makeContent(model: StubPageModel) -> some View {
        PageAView(onTap: { pageATaps += 1 })
    }
    static func makeSidebarActions(model: StubPageModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubPageModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubPageModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands { .init() }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

private struct PageAView: View {
    @State private var draft = "HelloA"
    let onTap: () -> Void
    var body: some View {
        VStack(alignment: .leading) {
            TextField("PageAField", text: $draft)
                .frame(width: 200)
            Spacer().frame(height: 160)
            Button("PageABtn", action: onTap)
                .accessibilityIdentifier("page.a.btn")
        }
        .padding(20)
        .frame(width: 400, height: 320, alignment: .topLeading)
        .background(Color.green)
    }
}

private struct StubPageModuleB: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "stubB", displayName: "Stub B",
        targetProcessName: "NoneB", targetBundleIdentifier: "test.none.b",
        expectedHostProtocolVersion: 1, expectedModuleProtocolVersion: 1, supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation()
    static func makeModel(services: TrainerModuleServices) -> StubPageModel { StubPageModel() }
    static func makeContent(model: StubPageModel) -> some View {
        VStack(alignment: .leading) {
            Button("PageBBtn") {}
                .accessibilityIdentifier("page.b.btn")
        }
        .padding(20)
        .frame(width: 400, height: 320, alignment: .topLeading)
        .background(Color.cyan)
    }
    static func makeSidebarActions(model: StubPageModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: StubPageModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: StubPageModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands { .init() }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

@MainActor
private func exerciseSidebarAndPages(localization: TrainerLocalizationStore) {
    localization.language = .en
    let theme = TrainerTheme.standard
    let desc = GameModuleDescriptor(
        id: "side", displayName: "Sidebar Game",
        targetProcessName: "NoneSide", targetBundleIdentifier: "test.none.side",
        expectedHostProtocolVersion: 1, expectedModuleProtocolVersion: 1, supportsSaveManagement: false
    )
    let pres = TrainerGamePresentation()
    var selects = 0
    var expandedActions = 0

    let view = VStack(alignment: .leading, spacing: 12) {
        TrainerSidebar {
            TrainerSidebarCard(
                descriptor: desc, presentation: pres,
                connected: false, busy: true, targetRunning: false,
                operationToken: .init(key: "host.backend.notice.recovering"),
                statusToken: .init(key: "host.disconnected"),
                detailToken: .init(key: "host.refreshStatus"),
                selected: true, onSelect: {}
            ) {
                Button("ExpandedAction") { expandedActions += 1 }
                    .frame(height: 50)
                    .accessibilityIdentifier("card.expandedAction")
            }
            .background(FrameProbe("card.expanded").allowsHitTesting(false).accessibilityHidden(true))

            TrainerSidebarCard(
                descriptor: desc, presentation: pres,
                connected: true, busy: false, targetRunning: true,
                operationToken: .init(key: "host.connected"),
                statusToken: .init(key: "host.connected"),
                detailToken: .init(key: "host.connected"),
                selected: true, onSelect: {}
            ) {
                Text("ConnectedAction")
            }

            TrainerSidebarCard(
                descriptor: desc, presentation: pres,
                connected: false, busy: false, targetRunning: true,
                operationToken: .init(key: "host.disconnected"),
                statusToken: .init(key: "host.disconnected"),
                detailToken: .init(key: "host.disconnected"),
                selected: false, onSelect: { selects += 1 }
            ) {
                Button("HiddenAction") {}
                    .accessibilityIdentifier("card.hiddenAction")
            }
            .background(FrameProbe("card.collapsed").allowsHitTesting(false).accessibilityHidden(true))

            TrainerSidebarCard(
                descriptor: desc, presentation: pres,
                connected: false, busy: false, targetRunning: false,
                operationToken: .init(key: "host.disconnected"),
                statusToken: .init(key: "host.disconnected"),
                detailToken: .init(key: "host.done"),
                selected: false, onSelect: {}
            ) {
                Text("IdleAction")
            }
        }
    }
    .trainerTheme(theme)
    .environmentObject(localization)

    let (win, host) = makeWindow(width: 280, height: 640, root: view)
    waitWindow(host, "sidebar cards mounted") {
        probeFrame("card.expanded", in: host, to: host) != nil
            && probeFrame("card.collapsed", in: host, to: host) != nil
            && nativeAccessibilityControls(host).contains { $0.identifier == "card.expandedAction" }
            && nativeAccessibilityControls(host).filter { $0.identifier == "host.game.side" }.count == 4
    }
    check(!nativeAccessibilityControls(host).contains { $0.role == "AXProgressIndicator" },
          "TrainerSidebarCard unexpectedly rendered a ProgressView spinner")
    check(!nativeAccessibilityControls(host).contains { $0.identifier == "card.hiddenAction" },
          "collapsed TrainerSidebarCard leaked inner action button into AX tree")

    let expandedRect = probeFrame("card.expanded", in: host, to: host)!
    let collapsedRect = probeFrame("card.collapsed", in: host, to: host)!
    check(expandedRect.height > collapsedRect.height + 40,
          "expanded card did not reveal its action area: expanded=\(expandedRect.height) collapsed=\(collapsedRect.height)")

    // Selected card expanded action is directly clickable/pressable; collapsed card header selects.
    // (Collapsed background .onTapGesture pointer click is verified under key-window activation in visual_hierarchy_harness.py.)
    let expBtn = nativeAccessibilityControls(host).first { $0.identifier == "card.expandedAction" }!
    check(expBtn.enabled && expBtn.press(), "selected card action button refused press")
    waitUntil("selected card expanded action fires") { expandedActions == 1 }

    let collapsedHeader = nativeAccessibilityControls(host)
        .filter { $0.identifier == "host.game.side" }
        .sorted { localRect($0.frame, in: host, window: win).minY < localRect($1.frame, in: host, window: win).minY }[2]
    check(collapsedHeader.press(), "collapsed header button refused AX press")
    waitUntil("collapsed header AX press invokes onSelect") { selects == 1 }

    // 4 indicator dot colors: busy(cyan), connected(green), targetRunning(orange), idle(neutral gray), plus raised vs panel surface & no leading stripe/focus ring.
    let headers = nativeAccessibilityControls(host)
        .filter { $0.identifier == "host.game.side" }
        .map { localRect($0.frame, in: host, window: win) }
        .sorted { $0.minY < $1.minY }
    let cardRings = focusRingViews(in: host).map { $0.convert($0.bounds, to: host) }
    check(headers.allSatisfy { header in !cardRings.contains { $0.intersects(header) } },
          "TrainerSidebarCard unexpectedly created a FocusRingView")

    // Verify header & status AX label, value, and multiline help for busy vs idle cards.
    let sortedHeaderNodes = nativeAccessibilityControls(host)
        .filter { $0.identifier == "host.game.side" }
        .sorted { localRect($0.frame, in: host, window: win).minY < localRect($1.frame, in: host, window: win).minY }
    let recoveringText = localization.localized("host.backend.notice.recovering")
    let disconnectedText = localization.localized("host.disconnected")
    let refreshText = localization.localized("host.refreshStatus")
    let doneText = localization.localized("host.done")
    check(sortedHeaderNodes[0].label == "Sidebar Game"
          && sortedHeaderNodes[0].valueText == disconnectedText
          && sortedHeaderNodes[0].help == [recoveringText, disconnectedText, refreshText].joined(separator: "\n"),
          "busy TrainerSidebarCard header/status AX metadata mismatch: \(String(describing: sortedHeaderNodes[0].help))")
    check(sortedHeaderNodes[3].help == [disconnectedText, doneText].joined(separator: "\n"),
          "idle TrainerSidebarCard header/status AX help mismatch: \(String(describing: sortedHeaderNodes[3].help))")

    let bitmap = rasterize(host)
    let raisedSurfaceLuma = luminance(bitmap, ptX: expandedRect.minX + 6, ptY: expandedRect.minY + 4, host: host)
    let panelSurfaceLuma = luminance(bitmap, ptX: collapsedRect.minX + 6, ptY: collapsedRect.minY + 4, host: host)
    check(raisedSurfaceLuma > panelSurfaceLuma + 0.02,
          "selected TrainerSidebarCard did not use raised surface vs panel: raised=\(raisedSurfaceLuma) panel=\(panelSurfaceLuma)")
    func checkStatusDot(_ header: NSRect, _ state: String, matching: (NSColor) -> Bool) {
        let step: CGFloat = 0.5
        var paintedBounds = CGRect.null
        var paintedSamples = 0
        for x in stride(from: header.maxX - 18, to: header.maxX + 2, by: step) {
            for y in stride(from: header.minY, to: header.maxY, by: step) {
                if matching(rgba(bitmap, ptX: x, ptY: y, host: host)) {
                    paintedBounds = paintedBounds.union(CGRect(x: x, y: y, width: step, height: step))
                    paintedSamples += 1
                }
            }
        }
        check(abs(paintedBounds.width - 8) <= 1 && abs(paintedBounds.height - 8) <= 1,
              "\(state) status dot must paint 8 × 8 points in its status color: \(paintedBounds)")
        // A filled circle covers about π/4 of its bounds. Allow for pixel rounding and antialiasing.
        let coverage = CGFloat(paintedSamples) * step * step / (paintedBounds.width * paintedBounds.height)
        check((0.65...0.92).contains(coverage), "\(state) status dot lost its circular paint: \(coverage)")
    }
    checkStatusDot(headers[0], "busy cyan", matching: isCyan)
    checkStatusDot(headers[1], "connected green", matching: isGreen)
    checkStatusDot(headers[2], "running orange", matching: isOrange)
    let idlePanelLuma = luminance(bitmap, ptX: collapsedRect.minX + 6, ptY: headers[3].minY, host: host)
    checkStatusDot(headers[3], "idle gray") { c in
        let luma = (c.redComponent + c.greenComponent + c.blueComponent) / 3.0
        let sat = max(c.redComponent, c.greenComponent, c.blueComponent) - min(c.redComponent, c.greenComponent, c.blueComponent)
        return luma > idlePanelLuma + 0.15 && sat < 0.08
    }
    let leadingStripeBox = NSRect(x: max(0, headers[0].minX - 16), y: headers[0].minY, width: 14, height: headers[0].height)
    check(!hasMatchingPixel(bitmap, in: leadingStripeBox, host: host, matching: isPurple),
          "TrainerSidebarCard unexpectedly drew a leading selection stripe")

    win.contentView = nil
    win.close()

    // TrainerGamePages: active clicks, opacity hiding, inactive click/AX isolation, firstResponder resignation on switch.
    StubPageModuleA.pageATaps = 0
    let fixtureHome = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
    let ctxA = TrainerGameContext<StubPageModuleA>(session: TrainerBackendSession(),
        logSink: TrainerLogSink(gameID: StubPageModuleA.descriptor.id, homeDirectory: fixtureHome))
    let ctxB = TrainerGameContext<StubPageModuleB>(session: TrainerBackendSession(),
        logSink: TrainerLogSink(gameID: StubPageModuleB.descriptor.id, homeDirectory: fixtureHome))
    let coordinator = TrainerApplicationCoordinator(
        contexts: [AnyTrainerGameContext(ctxA), AnyTrainerGameContext(ctxB)],
        localization: localization
    )
    let pagesView = TrainerGamePages(application: coordinator)
        .trainerTheme(theme)
        .environmentObject(localization)
    let (pWin, pHost) = makeWindow(width: 900, height: 600, root: pagesView)
    waitWindow(pHost, "TrainerGamePages initial page A") {
        nativeAccessibilityControls(pHost).contains { $0.identifier == "page.a.btn" }
            && !nativeAccessibilityControls(pHost).contains { $0.identifier == "page.b.btn" }
            && textFields(in: pHost).contains { $0.placeholderString == "PageAField" }
    }
    let pageABtnRect = localRect(
        nativeAccessibilityControls(pHost).first { $0.identifier == "page.a.btn" }!.frame,
        in: pHost, window: pWin
    )
    let activePageLuma = luminance(rasterize(pHost), ptX: pageABtnRect.midX, ptY: 160, host: pHost)
    check(activePageLuma > 0.4, "selected Page A green surface did not render: luma=\(activePageLuma)")
    clickLocal(NSPoint(x: pageABtnRect.midX, y: pageABtnRect.midY), in: pWin, host: pHost)
    waitUntil("active Page A button receives click") { StubPageModuleA.pageATaps == 1 }

    let fieldA = textFields(in: pHost).first { $0.placeholderString == "PageAField" }!
    check(pWin.makeFirstResponder(fieldA) && fieldA.currentEditor() != nil,
          "page A text field refused initial focus")

    coordinator.selectedGameID = "stubB"
    waitWindow(pHost, "TrainerGamePages switches to B and resigns Page A focus") {
        nativeAccessibilityControls(pHost).contains { $0.identifier == "page.b.btn" }
            && !nativeAccessibilityControls(pHost).contains { $0.identifier == "page.a.btn" }
            && fieldA.currentEditor() == nil
    }
    let pageBBtnRect = localRect(
        nativeAccessibilityControls(pHost).first { $0.identifier == "page.b.btn" }!.frame,
        in: pHost, window: pWin
    )
    let pageProbe = NSPoint(x: pageBBtnRect.minX + 5, y: pageBBtnRect.maxY + 20)
    func pagePaint() -> NSColor {
        rgba(rasterize(pHost), ptX: pageProbe.x, ptY: pageProbe.y, host: pHost)
    }
    waitWindow(pHost, "selected Page B paints its cyan surface") { isCyan(pagePaint()) }
    clickLocal(NSPoint(x: pageABtnRect.midX, y: pageABtnRect.midY), in: pWin, host: pHost)
    pump(0.05)
    check(StubPageModuleA.pageATaps == 1, "inactive Page A button remained clickable after switching to B")
    coordinator.selectedGameID = ""
    waitWindow(pHost, "TrainerGamePages hides unselected pages") {
        !nativeAccessibilityControls(pHost).contains { $0.identifier == "page.a.btn" || $0.identifier == "page.b.btn" }
    }
    waitWindow(pHost, "unselected pages stop painting their content") {
        let color = pagePaint()
        return (color.redComponent + color.greenComponent + color.blueComponent) / 3 < 0.2
    }
    pWin.contentView = nil
    pWin.close()
    print("scenario7_sidebar_pages_ok")
}

@main
struct Main {
    @MainActor
    static func main() {
        let components = CommandLine.arguments.dropFirst().compactMap(Double.init)
        check(components.count == 3, "fixture requires three asset accent components")
        let environment = EnvironmentValues()
        let accent = TrainerTheme.standard.accent.resolve(in: environment)
        let expected = Color(.sRGB, red: components[0], green: components[1], blue: components[2]).resolve(in: environment)
        check(abs(accent.red - expected.red) < 0.0005
              && abs(accent.green - expected.green) < 0.0005
              && abs(accent.blue - expected.blue) < 0.0005 && accent.opacity == 1,
              "compiled TrainerTheme accent \(accent) disagrees with application asset \(expected)")

        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        app.finishLaunching()
        enableNativeAccessibility()

        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        exerciseTogglesAndFeatures(localization: localization)
        exerciseRowAndLayout(localization: localization)
        exerciseCardsStatsLocks(localization: localization)
        exerciseButtonsBadgesSections(localization: localization)
        exerciseResourceControls(localization: localization)
        exerciseDisclosureProfilePickerPopover(localization: localization)
        exerciseSidebarAndPages(localization: localization)
        print("core_ui_primitives_macos_ok")
    }
}
'''

colorset_path = ROOT / "Resources/Assets.xcassets/AccentColor.colorset/Contents.json"
(accent_entry,) = json.loads(colorset_path.read_text(encoding="utf-8"))["colors"]
assert accent_entry["idiom"] == "universal"
assert "appearances" not in accent_entry, "the dark-only product declares one accent"
assert accent_entry["color"]["color-space"] == "srgb"
asset_accent = accent_entry["color"]["components"]
assert float(asset_accent["alpha"]) == 1.0

with tempfile.TemporaryDirectory(prefix="mgt-core-ui-primitives-") as temporary:
    root = Path(temporary)
    for language in ("zh-CN", "en"):
        localized = root / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(
            ROOT / f"Resources/Localization/{language}.lproj/Host.strings",
            localized / "Host.strings",
        )
    main = root / "CoreUIPrimitivesHarness.swift"
    main.write_text(HARNESS, encoding="utf-8")
    binary = root / "core-ui-primitives"
    compile_swift_test(
        harness_sources=[
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
            main,
        ],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    result = launch_fixture(
        [str(binary), *(str(asset_accent[name]) for name in ("red", "green", "blue"))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        journey="native.core_ui_primitives",
        budgets=JOURNEY_BUDGETS,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert "core_ui_primitives_macos_ok" in result.stdout, result.stdout
    print(result.stdout.strip())
