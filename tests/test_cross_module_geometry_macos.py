"""Render both real game modules via AppKit and enforce visual geometry parity."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from macos_fixture_policy import launch_fixture
from fixture_budgets.multi_game import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test

if sys.platform != "darwin":
    raise SystemExit("macOS-only cross-module UI geometry verification")

ROOT = Path(__file__).resolve().parents[1]

STUB_WORKER = r"""
import sys
for _ in sys.stdin:
    pass
"""

HARNESS = r'''
import AppKit
import SwiftUI

private func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError("cross-module geometry failed: " + message) }
}

@MainActor
private func pump(_ duration: TimeInterval = 0.05) {
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

private func localRect(from screenRect: NSRect, host: NSView, window: NSWindow) -> NSRect {
    let windowRect = window.convertFromScreen(screenRect)
    return host.convert(windowRect, from: nil)
}

private func textFields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(textFields)
}

private func rasterize(_ host: NSView) -> NSBitmapImageRep {
    host.layoutSubtreeIfNeeded()
    guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else {
        fatalError("bitmap allocation failed")
    }
    host.cacheDisplay(in: host.bounds, to: bitmap)
    return bitmap
}

private func rgba(_ bitmap: NSBitmapImageRep, ptX: CGFloat, ptY: CGFloat, host: NSView) -> NSColor {
    let bounds = host.bounds
    let scaleX = CGFloat(bitmap.pixelsWide) / bounds.width
    let scaleY = CGFloat(bitmap.pixelsHigh) / bounds.height
    let px = max(0, min(bitmap.pixelsWide - 1, Int((ptX * scaleX).rounded())))
    // NSBitmapImageRep.colorAt(x:y:) uses top-left pixel coordinates; when `host.isFlipped == true` (NSHostingView),
    // host ptY=0 is already at visual top.
    let rawY = host.isFlipped ? ptY : (bounds.height - ptY)
    let py = max(0, min(bitmap.pixelsHigh - 1, Int((rawY * scaleY).rounded())))
    return bitmap.colorAt(x: px, y: py)?.usingColorSpace(.deviceRGB) ?? .black
}

private func luminance(_ bitmap: NSBitmapImageRep, ptX: CGFloat, ptY: CGFloat, host: NSView) -> CGFloat {
    let color = rgba(bitmap, ptX: ptX, ptY: ptY, host: host)
    return (color.redComponent + color.greenComponent + color.blueComponent) / 3.0
}

private func colorDelta(_ a: NSColor, _ b: NSColor) -> CGFloat {
    abs(a.redComponent - b.redComponent) + abs(a.greenComponent - b.greenComponent) + abs(a.blueComponent - b.blueComponent)
}

private func findStaticText(
    _ controls: [NativeAccessibilityControl],
    title: String,
    host: NSView,
    window: NSWindow
) -> NSRect {
    let matches = controls.filter { $0.role == "AXStaticText" && $0.text == title }
    check(!matches.isEmpty, "missing AXStaticText '\(title)'")
    return localRect(from: matches[0].frame, host: host, window: window)
}

/// Measure painted card bounds vertically through `probeX`.
private func measureCardPaintedBounds(
    bitmap: NSBitmapImageRep,
    host: NSView,
    probeX: CGFloat,
    titleMidY: CGFloat,
    canvasLuma: CGFloat
) -> (minY: CGFloat, maxY: CGFloat, height: CGFloat) {
    let threshold = canvasLuma + 0.012
    var minY = titleMidY
    while minY > 2 && luminance(bitmap, ptX: probeX, ptY: minY - 0.5, host: host) > threshold {
        minY -= 0.5
    }
    var maxY = titleMidY
    while maxY < host.bounds.height - 2 && luminance(bitmap, ptX: probeX, ptY: maxY + 0.5, host: host) > threshold {
        maxY += 0.5
    }
    return (minY, maxY, maxY - minY)
}

/// Measure non-panel icon badge bounding box immediately to the left of an `AXStaticText` title.
private func measureIconBadgeSpan(
    bitmap: NSBitmapImageRep,
    host: NSView,
    labelRect: NSRect
) -> (width: CGFloat, height: CGFloat) {
    let bounds = host.bounds
    let bgSample = rgba(bitmap, ptX: labelRect.maxX + 4, ptY: labelRect.midY, host: host)
    let minX = max(2, labelRect.minX - 60)
    let maxX = max(minX + 1, labelRect.minX - 2)
    let minY = max(2, labelRect.midY - 26)
    let maxY = min(bounds.height - 2, labelRect.midY + 26)
    var leftEdge: CGFloat?
    var rightEdge: CGFloat?
    var bottomEdge: CGFloat?
    var topEdge: CGFloat?
    var x = minX
    while x <= maxX {
        var y = minY
        while y <= maxY {
            let sample = rgba(bitmap, ptX: x, ptY: y, host: host)
            if colorDelta(sample, bgSample) > 0.010 {
                leftEdge = min(leftEdge ?? x, x)
                rightEdge = max(rightEdge ?? x, x)
                bottomEdge = min(bottomEdge ?? y, y)
                topEdge = max(topEdge ?? y, y)
            }
            y += 1.0
        }
        x += 1.0
    }
    guard let l = leftEdge, let r = rightEdge, let b = bottomEdge, let t = topEdge else {
        return (0, 0)
    }
    return (r - l + 1, t - b + 1)
}

@MainActor
private func renderAndMeasure<V: View>(
    rootView: V,
    localization: TrainerLocalizationStore,
    width: CGFloat = 1144,
    documentHeight: CGFloat = 1500,
    onWindow: (NSView, NSWindow) -> Void
) {
    let windowHeight = min(CGFloat(780), (NSScreen.main?.visibleFrame.height ?? 900) - 60)
    let container = rootView
        .frame(width: width - 44, alignment: .topLeading)
        .padding(22)
        .frame(width: width, height: documentHeight, alignment: .topLeading)
        .trainerSurface(.canvas)
        .preferredColorScheme(.dark)
        .trainerTheme(.standard)
        .environmentObject(localization)
    let host = NSHostingView(rootView: container)
    host.frame = NSRect(x: 0, y: 0, width: width, height: documentHeight)
    let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: width, height: windowHeight))
    scrollView.hasVerticalScroller = true
    scrollView.documentView = host
    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: width, height: windowHeight),
        styleMask: [.titled],
        backing: .buffered,
        defer: false
    )
    window.isReleasedWhenClosed = false
    window.appearance = NSAppearance(named: .darkAqua)
    window.contentView = scrollView
    window.orderFront(nil)
    window.layoutIfNeeded()
    host.layoutSubtreeIfNeeded()
    pump(0.10)
    host.layoutSubtreeIfNeeded()
    onWindow(host, window)
    window.contentView = nil
    window.close()
}

@MainActor
private func runGeometryVerification(workerURL: URL, tmpDir: URL) {
    NSApp.setActivationPolicy(.regular)
    NSApp.finishLaunching()
    enableNativeAccessibility()

    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    localization.registerModulePresentation(
        prefix: HadesGameModule.presentationKeyPrefix,
        resolver: HadesGameModule.presentationText
    )
    localization.registerModulePresentation(
        prefix: Hades2GameModule.presentationKeyPrefix,
        resolver: Hades2GameModule.presentationText
    )

    let h1Session = TrainerBackendSession(client: BackendClient())
    let h1Model = HadesTrainerModel(
        session: h1Session,
        backendScriptURL: workerURL,
        defaults: InMemoryDefaults(),
        logSink: TrainerLogSink(url: tmpDir.appendingPathComponent("h1.log"))
    )

    let h2Session = TrainerBackendSession(client: BackendClient())
    let h2Model = Hades2TrainerModel(
        session: h2Session,
        logSink: TrainerLogSink(url: tmpDir.appendingPathComponent("h2.log")),
        backendScriptURL: workerURL,
        runLogDirectoryURL: tmpDir.appendingPathComponent("h2-run-logs"),
        shortcutDefaults: InMemoryDefaults()
    )

    for language in [TrainerPresentationLanguage.zhCN, .en] {
        localization.language = language

        // --- Hades I measurements ---
        h1Model.numericControlsExpanded = false
        var h1HeaderToCardGap: CGFloat = 0
        renderAndMeasure(rootView: HadesTrainerView(model: h1Model), localization: localization) { host, window in
            let controls = nativeAccessibilityControls(host)
            let bitmap = rasterize(host)
            let canvasLuma = luminance(bitmap, ptX: 8, ptY: 8, host: host)

            let sectionTitle = findStaticText(
                controls,
                title: HadesPresentation.text(HadesWorkbenchSection.values.titleKey, language: language),
                host: host,
                window: window
            )
            let healthTitle = findStaticText(
                controls,
                title: HadesPresentation.text("hades.health", language: language),
                host: host,
                window: window
            )
            let moneyTitle = findStaticText(
                controls,
                title: HadesPresentation.text("hades.money", language: language),
                host: host,
                window: window
            )
            let rerollsTitle = findStaticText(
                controls,
                title: HadesPresentation.text("hades.rerolls", language: language),
                host: host,
                window: window
            )
            let godGaugeTitle = findStaticText(
                controls,
                title: HadesPresentation.text("hades.godGauge", language: language),
                host: host,
                window: window
            )

            // Probe just inside each card's title row X so we measure pure canvas->panel vertical bounds.
            let cardRects = [healthTitle, moneyTitle, rerollsTitle, godGaugeTitle].map {
                measureCardPaintedBounds(
                    bitmap: bitmap,
                    host: host,
                    probeX: $0.minX - 2,
                    titleMidY: $0.midY,
                    canvasLuma: canvasLuma
                )
            }
            let minH = cardRects.map(\.height).min() ?? 0
            let maxH = cardRects.map(\.height).max() ?? 0
            check(maxH > 40 && maxH - minH <= 1.5,
                  "Hades I Row 1 card heights differ (God Gauge mismatch): \(cardRects.map(\.height)) language=\(language.rawValue)")

            // On NSHostingView (isFlipped=true), top card edge is minY below sectionTitle.maxY.
            h1HeaderToCardGap = host.isFlipped ? (cardRects[0].minY - sectionTitle.maxY) : (sectionTitle.minY - cardRects[0].maxY)
            check(h1HeaderToCardGap >= 8 && h1HeaderToCardGap <= 18,
                  "Hades I header-to-card gap unexpected: \(h1HeaderToCardGap) flipped=\(host.isFlipped) section=\(sectionTitle) card=\(cardRects[0])")

            // Single-value fields in Row 1 (Gold, Relic Rerolls, God Gauge) must align vertically.
            let allFields = textFields(in: host)
            let row1FieldMidYs = ["hades.money", "hades.rerolls", "hades.godGauge"].map { key -> CGFloat in
                let label = HadesPresentation.text(key, language: language)
                guard let field = allFields.first(where: { $0.accessibilityLabel() == label }) else {
                    fatalError("missing NSTextField for \(key)")
                }
                return field.convert(field.bounds, to: host).midY
            }
            check((row1FieldMidYs.max()! - row1FieldMidYs.min()!) <= 1.0,
                  "Hades I Row 1 metric field baselines diverged (God Gauge vs Money/Rerolls): \(row1FieldMidYs)")

            // "祝福管理" (hades.currentTraits) must render the shared 40x40 TrainerIconLabel badge box.
            let traitsTitle = findStaticText(
                controls,
                title: HadesPresentation.text("hades.currentTraits", language: language),
                host: host,
                window: window
            )
            let traitsBadge = measureIconBadgeSpan(
                bitmap: bitmap, host: host, labelRect: traitsTitle
            )
            check(traitsBadge.width >= 36 && traitsBadge.height >= 36,
                  "Hades I currentTraits missing 40x40 icon badge box: span=\(traitsBadge) language=\(language.rawValue)")

            print("h1_geometry lang=\(language.rawValue) gap=\(h1HeaderToCardGap) cardHeights=\(cardRects.map(\.height)) traitsBadge=\(traitsBadge)")
        }

        // --- Hades II measurements (collapsed & expanded) ---
        h2Model.numericControlsExpanded = true
        var h2HeaderToCardGap: CGFloat = 0
        renderAndMeasure(rootView: Hades2TrainerView(model: h2Model), localization: localization) { host, window in
            let controls = nativeAccessibilityControls(host)
            let bitmap = rasterize(host)
            let canvasLuma = luminance(bitmap, ptX: 8, ptY: 8, host: host)

            let sectionTitle = findStaticText(
                controls,
                title: Hades2GameModule.presentationText(key: "hades2.section.runData", arguments: [], language: language),
                host: host,
                window: window
            )
            let healthTitle = findStaticText(
                controls,
                title: Hades2GameModule.presentationText(key: "hades2.vital.health", arguments: [], language: language),
                host: host,
                window: window
            )
            let healthCard = measureCardPaintedBounds(
                bitmap: bitmap,
                host: host,
                probeX: healthTitle.minX - 2,
                titleMidY: healthTitle.midY,
                canvasLuma: canvasLuma
            )
            h2HeaderToCardGap = host.isFlipped ? (healthCard.minY - sectionTitle.maxY) : (sectionTitle.minY - healthCard.maxY)
            check(abs(h1HeaderToCardGap - h2HeaderToCardGap) <= 1.5,
                  "Header-to-card gap diverged between Hades I (\(h1HeaderToCardGap)) and Hades II (\(h2HeaderToCardGap)) in \(language.rawValue)")

            // Expanded Row 1 includes lockless Damage Multiplier and Spell Charge (detail == nil when offline).
            let expandedRow1Titles = [
                Hades2GameModule.presentationText(key: "hades2.feature.damageMultiplier", arguments: [], language: language),
                Hades2GameModule.presentationText(key: "hades2.stat.grasp", arguments: [], language: language),
                Hades2GameModule.presentationText(key: "hades2.metric.rerolls", arguments: [], language: language),
                Hades2GameModule.presentationText(key: "hades2.metric.spellCharge", arguments: [], language: language),
            ].map { findStaticText(controls, title: $0, host: host, window: window) }
            let expandedRow1Rects = expandedRow1Titles.map {
                measureCardPaintedBounds(
                    bitmap: bitmap,
                    host: host,
                    probeX: $0.minX - 2,
                    titleMidY: $0.midY,
                    canvasLuma: canvasLuma
                )
            }
            let minH2 = expandedRow1Rects.map(\.height).min() ?? 0
            let maxH2 = expandedRow1Rects.map(\.height).max() ?? 0
            check(maxH2 > 40 && maxH2 - minH2 <= 1.5,
                  "Hades II expanded Row 1 card heights differ (Spell Charge vs siblings): \(expandedRow1Rects.map(\.height)) language=\(language.rawValue)")

            let allFields = textFields(in: host)
            let h2Row1FieldMidYs = ["hades2.feature.damageMultiplier", "hades2.stat.grasp", "hades2.metric.rerolls", "hades2.metric.spellCharge"].map { key -> CGFloat in
                let label = Hades2GameModule.presentationText(key: key, arguments: [], language: language)
                guard let field = allFields.first(where: { $0.accessibilityLabel() == label }) else {
                    fatalError("missing NSTextField for \(key)")
                }
                return field.convert(field.bounds, to: host).midY
            }
            check((h2Row1FieldMidYs.max()! - h2Row1FieldMidYs.min()!) <= 1.0,
                  "Hades II expanded Row 1 metric field baselines diverged: \(h2Row1FieldMidYs)")

            print("h2_geometry lang=\(language.rawValue) gap=\(h2HeaderToCardGap) expandedRow1Heights=\(expandedRow1Rects.map(\.height))")

            let traitsTitle = findStaticText(
                controls,
                title: Hades2GameModule.presentationText(key: "hades2.traits.manager", arguments: [], language: language),
                host: host,
                window: window
            )
            let traitsBadge = measureIconBadgeSpan(
                bitmap: bitmap, host: host, labelRect: traitsTitle
            )
            check(traitsBadge.width >= 36 && traitsBadge.height >= 36,
                  "Hades II currentRunTraitsPanel missing 40x40 icon badge box: span=\(traitsBadge) language=\(language.rawValue)")
            print("h2_traits_badge lang=\(language.rawValue) traitsBadge=\(traitsBadge)")
        }
    }

    h1Session.stop()
    h2Session.stop()
    print("cross_module_geometry_ok")
}

@main
struct CrossModuleGeometryRunner {
    static func main() {
        let args = CommandLine.arguments
        guard args.count == 3 else { fatalError("usage: <binary> <worker.py> <tmpDir>") }
        let workerURL = URL(fileURLWithPath: args[1])
        let tmpDir = URL(fileURLWithPath: args[2], isDirectory: true)
        DispatchQueue.main.async {
            runGeometryVerification(workerURL: workerURL, tmpDir: tmpDir)
            NSApp.terminate(nil)
        }
        NSApplication.shared.run()
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-cross-geometry-") as directory:
    folder = Path(directory)
    for language in ("en", "zh-CN"):
        lproj = folder / f"{language}.lproj"
        lproj.mkdir()
        shutil.copy2(
            ROOT / "Resources/Localization" / f"{language}.lproj/Host.strings",
            lproj / "Host.strings",
        )
    worker = folder / "stub_worker.py"
    worker.write_text(STUB_WORKER, encoding="utf-8")
    main = folder / "main.swift"
    main.write_text(HARNESS, encoding="utf-8")
    binary = folder / "cross_module_geometry"
    compile_swift_test(
        games=("hades", "hades2"),
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
                         ROOT / "tests/fixtures/swift/NativeAccessibility.swift", main],
        output=binary,
        cwd=ROOT,
    )
    home = folder / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    result = launch_fixture(
        [str(binary), str(worker), str(folder)],
        journey="multi_game.cross_module_geometry",
        budgets=JOURNEY_BUDGETS,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)
    assert "cross_module_geometry_ok" in result.stdout, result.stdout + "\n" + result.stderr

print("test_cross_module_geometry_macos_ok")
