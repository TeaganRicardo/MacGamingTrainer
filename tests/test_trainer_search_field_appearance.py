"""Exercise the shared SwiftUI search control and its clear-action contract on macOS."""
import shutil
import subprocess
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

func buttons(in view: NSView) -> [NSButton] {
    (view as? NSButton).map { [$0] } ?? view.subviews.flatMap(buttons)
}

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
            .frame(width: 320)
            TrainerSearchField(text: .constant(""), placeholder: "No clear action")
                .frame(width: 320)
        }
        .trainerTheme(.standard)
    }
}

@main
struct Main {
    @MainActor
    static func main() {
        _ = NSApplication.shared
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            let model = SearchModel()
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 400, height: 220),
                styleMask: [.titled], backing: .buffered, defer: false
            )
            window.appearance = NSAppearance(named: appearance)
            let host = NSHostingView(rootView: Fixture(model: model))
            host.frame = window.contentView!.bounds
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.10))
            host.layoutSubtreeIfNeeded()

            let rendered = fields(in: host)
            check(rendered.count == 2, "both shared search fields must materialize")
            guard let search = rendered.first(where: { $0.placeholderString == "Search entries" }) else {
                fatalError("search field is missing")
            }
            check(!search.isBezeled && !search.drawsBackground,
                  "search field must use the shared plain-field treatment")
            check(search.textColor != NSColor.clear && search.bounds.height > 0,
                  "search field text must remain visible and laid out")

            check(buttons(in: host).isEmpty, "clear action must stay hidden for an empty query")
            model.query = "Nemesis"
            RunLoop.current.run(until: Date().addingTimeInterval(0.10))
            host.layoutSubtreeIfNeeded()
            let clearButtons = buttons(in: host)
            check(clearButtons.count == 1, "one clear action must appear for a non-empty query")
            clearButtons[0].performClick(nil)
            RunLoop.current.run(until: Date().addingTimeInterval(0.10))
            host.layoutSubtreeIfNeeded()
            check(model.query.isEmpty, "clear action did not clear the bound query")
            check(model.submits == 1, "clear action must submit exactly once")
            check(buttons(in: host).isEmpty, "clear action must disappear after clearing")
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
    subprocess.run([
        SWIFTC, "-parse-as-library",
        str(ROOT / "Sources/Core/UI/TrainerTheme.swift"),
        str(ROOT / "Sources/Core/UI/Components/TrainerSearchField.swift"),
        str(swift), "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=15)
