"""Exercise the real shared SwiftUI/AppKit text control on macOS."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only AppKit text field presentation")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import AppKit
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func fields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

struct Fixture: View {
    @State private var rounded = "123"
    @State private var plain = "456"
    @State private var disabled = "789"

    var body: some View {
        VStack(spacing: 16) {
            TrainerTextField(title: "rounded", text: $rounded)
                .frame(width: 96)
            TrainerTextField(title: "plain", text: $plain, style: .plain)
                .frame(width: 96)
            TrainerTextField(title: "disabled", text: $disabled)
                .frame(width: 96)
                .disabled(true)
        }
    }
}

@main
struct Main {
    @MainActor
    static func main() {
        _ = NSApplication.shared
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 400, height: 250),
                styleMask: [.titled], backing: .buffered, defer: false
            )
            window.appearance = NSAppearance(named: appearance)
            let host = NSHostingView(rootView: Fixture())
            host.frame = window.contentView!.bounds
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.10))
            host.layoutSubtreeIfNeeded()

            let rendered = Dictionary(uniqueKeysWithValues: fields(in: host).compactMap { field in
                field.placeholderString.map { ($0, field) }
            })
            check(rendered.count == 3, "SwiftUI did not materialize all three native text controls")
            guard let rounded = rendered["rounded"],
                  let plain = rendered["plain"],
                  let disabled = rendered["disabled"] else {
                fatalError("missing shared text field instance")
            }

            // A rounded input must actually draw its native bezel. AppKit's
            // bezeled and manually painted backgrounds are mutually exclusive.
            check(rounded.isBezeled && rounded.bezelStyle == .roundedBezel,
                  "rounded input has no visible bezel in \(appearance.rawValue)")
            check(!rounded.drawsBackground,
                  "rounded bezel must own its background in \(appearance.rawValue)")
            check(rounded.stringValue == "123" && rounded.bounds.height > 0,
                  "rounded input lost its displayed value or layout")

            // Metric-style fields intentionally have no box, but still show
            // their values; disabling a field does not erase its native bezel.
            check(!plain.isBezeled && !plain.drawsBackground && plain.stringValue == "456",
                  "plain metric input changed display semantics")
            check(plain.textColor != NSColor.clear, "plain metric text is transparent")
            check(disabled.isBezeled && !disabled.isEnabled && disabled.stringValue == "789",
                  "disabled numeric input lost its visible control")
            window.close()
        }
        print("trainer_text_field_appearance_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-field-appearance-") as temporary:
    directory = Path(temporary)
    swift = directory / "main.swift"
    binary = directory / "field_appearance"
    swift.write_text(HARNESS)
    subprocess.run([
        SWIFTC, "-parse-as-library",
        str(ROOT / "Sources/Core/UI/Primitives/TrainerTextField.swift"),
        str(swift), "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=15)
