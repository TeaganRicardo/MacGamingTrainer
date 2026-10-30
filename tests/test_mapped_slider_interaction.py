"""Exercise the shared slider's real accessibility input and visible thumb."""
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
func pump() { RunLoop.current.run(until: Date().addingTimeInterval(0.35)) }

final class Model: ObservableObject {
    @Published var value = 1.0
    @Published var enabled = false
    var commits = 0
}
struct SliderFixture: View {
    @ObservedObject var model: Model
    var body: some View {
        TrainerMappedSlider(value: Binding(get: { model.value }, set: {
            model.value = $0; model.commits += 1
        }), mapping: .anchoredLogarithmic(values: [0.1, 1, 10], step: 0.1),
            accessibilityLabel: "Speed fixture", accessibilityHint: "Adjust speed", enabled: model.enabled)
            .frame(width: 240, height: 30).padding(12)
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
    return total / Double(count)
}
@main struct Main {
    @MainActor static func main() {
        _ = NSApplication.shared
        enableNativeAccessibility()
        let model = Model()
        let host = NSHostingView(rootView: SliderFixture(model: model))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 264, height: 54),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.orderFront(nil)
        pump()
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
        let before = thumbCenter(host)
        check(slider().enabled && increment(slider()), "enabled AX adjustment failed")
        pump()
        check(model.value > 1 && model.commits == 1, "AX input did not commit exactly once")
        check(thumbCenter(host) > before + 1, "AX commit left the visible thumb at the old value")
        let adjusted = thumbCenter(host)
        model.value = 0.2
        pump()
        check(thumbCenter(host) < adjusted - 5 && model.commits == 1,
              "external observation did not move the thumb or caused another commit")
        model.enabled = false
        pump()
        _ = increment(slider())
        pump()
        check(model.value == 0.2 && model.commits == 1, "disabling after an edit did not revoke AX input")
        window.close()
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
                   check=True, timeout=15)
