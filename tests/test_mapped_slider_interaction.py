"""Exercise actual mouse, keyboard and accessibility input on the shared slider."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != "darwin":
    raise SystemExit("macOS-only native mapped-slider interaction")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import AppKit
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs(message + "\n", stderr); exit(1) }
}
func pump(_ duration: TimeInterval = 0.08) {
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

final class Model: ObservableObject {
    @Published var value = 1.0
    @Published var enabled = false
    @Published var parentDisabled = false
    @Published var width: CGFloat = 240
    @Published var preview: Double?
    var commits = 0
}
struct SliderFixture: View {
    @ObservedObject var model: Model
    var body: some View {
        TrainerMappedSlider(value: Binding(get: { model.value }, set: {
            model.value = $0; model.commits += 1
        }), mapping: .anchoredLogarithmic(values: [0.1, 1, 10], step: 0.1),
            accessibilityLabel: "Speed fixture", accessibilityHint: "Adjust speed", enabled: model.enabled,
            onPreviewValue: { model.preview = $0 })
            .frame(width: model.width, height: 30).padding(12)
            .disabled(model.parentDisabled)
            .background(Color.black)
            .trainerTheme(.standard)
    }
}
func increment(_ control: NativeAccessibilityControl) -> Bool {
    let selector = NSSelectorFromString("accessibilityPerformIncrement")
    check(control.object.responds(to: selector), "actual accessible slider lacks Increment")
    typealias Perform = @convention(c) (AnyObject, Selector) -> Bool
    return unsafeBitCast(control.object.method(for: selector), to: Perform.self)(control.object, selector)
}
func thumbCenter(_ view: NSView) -> Double {
    view.layoutSubtreeIfNeeded()
    let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: bitmap)
    var total = 0.0
    var count = 0
    for y in 0..<bitmap.pixelsHigh {
        for x in 0..<bitmap.pixelsWide {
            guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB),
                  min(color.redComponent, color.greenComponent, color.blueComponent) > 0.9 else { continue }
            total += Double(x); count += 1
        }
    }
    check(count > 0, "native fixture did not draw the slider thumb")
    return total / Double(count) * Double(view.bounds.width) / Double(bitmap.pixelsWide)
}

func mouse(_ type: NSEvent.EventType, x: Double, in window: NSWindow) {
    let event = NSEvent.mouseEvent(with: type, location: NSPoint(x: x, y: 27),
        modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
        windowNumber: window.windowNumber, context: nil, eventNumber: 0,
        clickCount: 1, pressure: type == .leftMouseUp ? 0 : 1)!
    NSApp.sendEvent(event)
    pump()
}

func key(_ code: UInt16, characters: String, in window: NSWindow) {
    let event = NSEvent.keyEvent(with: .keyDown, location: .zero, modifierFlags: [],
        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
        context: nil, characters: characters, charactersIgnoringModifiers: characters,
        isARepeat: false, keyCode: code)!
    NSApp.sendEvent(event)
    pump()
}
@main struct Main {
    @MainActor static func main() {
        let application = NSApplication.shared
        application.setActivationPolicy(.regular)
        application.finishLaunching()
        application.activate(ignoringOtherApps: true)
        enableNativeAccessibility()
        let model = Model()
        let host = NSHostingView(rootView: SliderFixture(model: model))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 264, height: 54),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.makeKeyAndOrderFront(nil)
        application.activate(ignoringOtherApps: true)
        pump(0.3)
        func slider() -> NativeAccessibilityControl {
            guard let control = namedNativeControl(host, role: "AXSlider", name: "Speed fixture") else {
                check(false, "missing actual native accessibility slider"); fatalError()
            }
            return control
        }
        check(!slider().enabled, "disabled visual control remained accessible as enabled")
        _ = increment(slider())
        pump()
        check(model.value == 1 && model.commits == 0, "disabled AX input committed a value")
        model.enabled = true
        pump()
        // A click far from the thumb previews while pressed and commits once.
        mouse(.leftMouseDown, x: 220, in: window)
        check(model.commits == 0 && model.preview != nil,
              "pointer-down must preview without committing")
        mouse(.leftMouseUp, x: 220, in: window)
        pump(0.3)
        check(model.value > 5 && model.commits == 1,
              "track click did not seek and commit exactly once")
        check(model.preview == nil, "committed pointer edit retained its preview")
        let mapping = TrainerSliderMapping.anchoredLogarithmic(values: [0.1, 1, 10], step: 0.1)
        func expectedThumb() -> Double { 22 + Double(model.width - 20) * mapping.position(for: model.value) }
        check(abs(thumbCenter(host) - expectedThumb()) < 1.5,
              "settled thumb differs from its quantized committed value")

        let start = thumbCenter(host) + 6
        mouse(.leftMouseDown, x: start, in: window)
        let grabbed = thumbCenter(host)
        mouse(.leftMouseDragged, x: start - 37, in: window)
        check(model.commits == 1 && abs(thumbCenter(host) - (grabbed - 37)) < 1.5,
              "thumb drag lost grab offset or lagged behind pointer")
        mouse(.leftMouseDragged, x: start - 14, in: window)
        check(model.commits == 1 && abs(thumbCenter(host) - (grabbed - 14)) < 1.5,
              "rapid reversal lagged or committed prematurely")
        mouse(.leftMouseUp, x: start - 14, in: window)
        pump(0.3)
        check(model.commits == 2 && model.preview == nil,
              "thumb release did not commit once and clear its preview")
        check(abs(thumbCenter(host) - expectedThumb()) < 1.5,
              "drag release did not settle on committed value")

        let same = thumbCenter(host)
        mouse(.leftMouseDown, x: same, in: window)
        mouse(.leftMouseUp, x: same, in: window)
        check(model.commits == 2 && model.preview == nil,
              "unchanged click leaked preview or emitted another mutation")

        // Background observations preserve an active draft. Revoking input
        // cancels it and restores the latest observation, without a mutation.
        mouse(.leftMouseDown, x: thumbCenter(host), in: window)
        mouse(.leftMouseDragged, x: 170, in: window)
        let duringDrag = thumbCenter(host)
        model.value = 0.2
        pump()
        check(abs(thumbCenter(host) - duringDrag) < 1.5 && model.preview != nil,
              "external observation replaced an active pointer draft")
        model.parentDisabled = true
        pump()
        model.parentDisabled = false
        pump()
        mouse(.leftMouseUp, x: 170, in: window)
        pump(0.3)
        check(model.commits == 2 && model.value == 0.2 && model.preview == nil,
              "cancelled gesture committed after input was re-enabled")
        check(abs(thumbCenter(host) - expectedThumb()) < 1.5,
              "cancel did not restore the latest observation")

        let before = thumbCenter(host)
        check(slider().enabled && increment(slider()), "enabled AX adjustment failed")
        pump(0.3)
        check(abs(model.value - 0.3) < 0.000001 && model.commits == 3,
              "AX input did not commit one legal numeric step")
        check(thumbCenter(host) > before + 1, "AX commit left the visible thumb at the old value")
        let adjusted = thumbCenter(host)
        model.value = 0.1
        pump(0.02)
        check(thumbCenter(host) < adjusted - 5 && model.commits == 3,
              "external observation did not move the thumb or caused another commit")
        check(abs(thumbCenter(host) - expectedThumb()) < 1.5,
              "unrelated observation acquired a settling animation")

        // Exercise the native system setting as found. SwiftUI's accessibility
        // environment is read-only; this fixture never changes user preferences.
        mouse(.leftMouseDown, x: thumbCenter(host), in: window)
        mouse(.leftMouseUp, x: thumbCenter(host), in: window)
        key(124, characters: String(UnicodeScalar(NSRightArrowFunctionKey)!), in: window)
        pump(0.3)
        check(abs(model.value - 0.2) < 0.000001 && model.commits == 4,
              "focused right-arrow did not commit one numeric step")
        check(abs(thumbCenter(host) - expectedThumb()) < 1.5,
              "keyboard input did not settle on its committed value")
        mouse(.leftMouseDown, x: 200, in: window)
        key(53, characters: "\u{1b}", in: window)
        mouse(.leftMouseUp, x: 200, in: window)
        check(model.value == 0.2 && model.commits == 4 && model.preview == nil,
              "Escape did not cancel pointer preview without committing")

        model.width = 80
        window.setContentSize(NSSize(width: 104, height: 54))
        pump()
        let narrowBounds = window.convertFromScreen(slider().frame)
        check(abs(narrowBounds.width - 80) < 1, "narrow fixture did not resize its actual slider")
        // The drawing's track endpoints are thumb-center positions inside the
        // control. maxX itself is outside AppKit's half-open hit-test bounds.
        let upperEndpoint = Double(narrowBounds.maxX - 10)
        let lowerEndpoint = Double(narrowBounds.minX + 10)
        mouse(.leftMouseDown, x: upperEndpoint, in: window)
        mouse(.leftMouseUp, x: upperEndpoint, in: window)
        check(model.value == 10 && model.commits == 5 && model.preview == nil,
              "narrow slider did not reach its upper endpoint")
        mouse(.leftMouseDown, x: lowerEndpoint, in: window)
        mouse(.leftMouseUp, x: lowerEndpoint, in: window)
        check(model.value == 0.1 && model.commits == 6,
              "narrow slider did not reach its lower endpoint")
        model.enabled = false
        pump()
        _ = increment(slider())
        pump()
        mouse(.leftMouseDown, x: upperEndpoint, in: window)
        mouse(.leftMouseUp, x: upperEndpoint, in: window)
        check(model.value == 0.1 && model.commits == 6 && model.preview == nil,
              "disabled pointer or AX input changed the value")
        window.close()
        print("mapped_slider_system_reduce_motion=\(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion)")
        print("mapped_slider_interaction_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-slider-interaction-") as temporary:
    directory = Path(temporary)
    harness = directory / "main.swift"
    harness.write_text(HARNESS)
    binary = directory / "slider"
    sources = [
        ROOT / "Sources/Core/UI/TrainerTheme.swift",
        ROOT / "Sources/Core/UI/Primitives/TrainerSliderMapping.swift",
        ROOT / "Sources/Core/UI/Primitives/TrainerMappedSlider.swift",
        ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
    ]
    subprocess.run([SWIFTC, "-parse-as-library", *map(str, sources), str(harness), "-o", str(binary)],
                   cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, env=dict(os.environ, HOME=str(directory)),
                   check=True, timeout=20)
