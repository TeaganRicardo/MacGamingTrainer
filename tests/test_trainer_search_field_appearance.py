MGT_PLATFORM = "macos"

from macos_fixture_policy import launch_fixture
from fixture_budgets.core_ui import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test
"""Exercise shared search-field appearance and clear-action semantics on macOS."""
import shutil
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only AppKit search field presentation")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import AppKit
import SwiftUI

@MainActor
final class SearchModel: ObservableObject {
    @Published var query = ""
    @Published var submits = 0
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func fields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

@MainActor
func pump(_ duration: TimeInterval = 0.02) {
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
func waitWindow(_ host: NSView, message: String, timeout: TimeInterval = 3.0, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        pump(0.01)
    }
    fatalError("search field timeout: \(message)")
}

struct SearchContainerProbe: NSViewRepresentable {
    final class Marker: NSView {}
    func makeNSView(context: Context) -> Marker { Marker() }
    func updateNSView(_ view: Marker, context: Context) {}
}

func probeViews(in root: NSView) -> [NSView] {
    (root is SearchContainerProbe.Marker ? [root] : []) + root.subviews.flatMap(probeViews)
}

func rasterize(_ host: NSView) -> NSBitmapImageRep {
    host.layoutSubtreeIfNeeded()
    let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
    host.cacheDisplay(in: host.bounds, to: bitmap)
    return bitmap
}

func luminance(_ bitmap: NSBitmapImageRep, ptX: CGFloat, ptY: CGFloat, host: NSView) -> CGFloat {
    let bounds = host.bounds
    let scaleX = CGFloat(bitmap.pixelsWide) / bounds.width
    let scaleY = CGFloat(bitmap.pixelsHigh) / bounds.height
    let px = max(0, min(bitmap.pixelsWide - 1, Int((ptX * scaleX).rounded())))
    let rawY = host.isFlipped ? ptY : (bounds.height - ptY)
    let py = max(0, min(bitmap.pixelsHigh - 1, Int((rawY * scaleY).rounded())))
    let c = bitmap.colorAt(x: px, y: py)?.usingColorSpace(.deviceRGB) ?? .black
    return (c.redComponent + c.greenComponent + c.blueComponent) / 3.0
}

@MainActor
struct Fixture: View {
    @ObservedObject var model: SearchModel

    var body: some View {
        VStack(spacing: 12) {
            TrainerSearchField(
                text: $model.query,
                placeholder: "Search entries",
                clearLabel: "Clear search",
                onSubmit: { model.submits += 1 }
            )
            .background(SearchContainerProbe().allowsHitTesting(false).accessibilityHidden(true))
            .frame(width: 320)
            TrainerSearchField(text: .constant("Retained"), placeholder: "No clear action")
                .frame(width: 320)
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .trainerSurface(.canvas)
        .trainerTheme(.standard)
    }
}

@main
struct Main {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        app.finishLaunching()
        enableNativeAccessibility()
        let theme = TrainerTheme.standard
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            let model = SearchModel()
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 400, height: 220),
                styleMask: [.titled], backing: .buffered, defer: false
            )
            window.isReleasedWhenClosed = false
            window.appearance = NSAppearance(named: appearance)
            let host = NSHostingView(rootView: Fixture(model: model))
            host.frame = window.contentView!.bounds
            window.contentView = host
            window.orderBack(nil)

            waitWindow(host, message: "search fields mounted in \(appearance.rawValue)") {
                fields(in: host).count == 2 && !probeViews(in: host).isEmpty
            }

            let rendered = fields(in: host)
            check(rendered.count == 2, "both shared search fields must materialize")
            guard let search = rendered.first(where: { $0.placeholderString == "Search entries" }),
                  let noClear = rendered.first(where: { $0.placeholderString == "No clear action" }) else {
                fatalError("search field is missing")
            }
            check(!search.isBezeled && !search.drawsBackground,
                  "search field must use the shared plain-field treatment")
            check(search.textColor != NSColor.clear && search.bounds.height > 0,
                  "search field text must remain visible and laid out")
            check(noClear.stringValue == "Retained", "second search field lost its initial value")

            let outerFrame = probeViews(in: host)[0].convert(probeViews(in: host)[0].bounds, to: host)
            let fieldFrame = search.convert(search.bounds, to: host)
            check(outerFrame.height >= fieldFrame.height + 2 * theme.controlPadding - 2,
                  "search field lost its controlPadding: outer=\(outerFrame) inner=\(fieldFrame)")
            let trailingInset = outerFrame.maxX - fieldFrame.maxX
            let leadingInset = fieldFrame.minX - outerFrame.minX
            check(trailingInset >= theme.controlPadding - 2,
                  "search field lost its trailing controlPadding: inset=\(trailingInset)")
            check(leadingInset >= theme.controlPadding + theme.compactControlSpacing + 10,
                  "search field lost its compactControlSpacing or magnifying glass: leadingInset=\(leadingInset)")
            if appearance == .darkAqua {
                let bitmap = rasterize(host)
                let canvasLuma = luminance(bitmap, ptX: 4, ptY: 4, host: host)
                let subtleLuma = luminance(bitmap, ptX: outerFrame.maxX - 4, ptY: outerFrame.midY, host: host)
                check(subtleLuma > canvasLuma + 0.006,
                      "search field lost subtle surface background: canvas=\(canvasLuma) surface=\(subtleLuma)")
            }

            func clearButtons() -> [NativeAccessibilityControl] {
                nativeAccessibilityControls(host).filter {
                    $0.role == "AXButton" && $0.identifier == "trainer.search.clear"
                }
            }
            check(clearButtons().isEmpty,
                  "clear button appeared when query empty or when clearLabel is nil")

            model.query = "Nemesis"
            waitWindow(host, message: "clear button exposed in AX tree") {
                clearButtons().count == 1
            }
            let clear = clearButtons()[0]
            check(clear.label == "Clear search" && clear.help == "Clear search",
                  "clear button lost localized label or help: label=\(String(describing: clear.label)) help=\(String(describing: clear.help))")
            check(clear.press(), "native clear button refused AX press")
            waitWindow(host, message: "clear button resets query, submits, and hides") {
                model.query.isEmpty && model.submits == 1 && clearButtons().isEmpty
            }

            window.contentView = nil
            window.close()
        }
        print("trainer_search_field_appearance_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-search-field-appearance-") as temporary:
    directory = Path(temporary)
    swift = directory / "main.swift"
    binary = directory / "search_field_appearance"
    swift.write_text(HARNESS)
    compile_swift_test(
        harness_sources=[ROOT / "tests/fixtures/swift/NativeAccessibility.swift", swift],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    launch_fixture([str(binary)], cwd=ROOT, check=True, journey='native.trainer_search_field_appearance', budgets=JOURNEY_BUDGETS)
