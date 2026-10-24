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

struct MetricFixture: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var focus: String?
    @State private var current = "11"
    @State private var maximum = "22"
    @State private var amount = "33"
    @State private var counter = "44"
    @State private var stat = "55"
    @State private var inline = "66"
    @State private var multiplier = "77"
    @State private var gain = "88"

    private func title(_ zh: String, _ en: String) -> String {
        localization.language == .en ? en : zh
    }
    private var state: TrainerFeatureControlState {
        TrainerFeatureControlState(isOn: true, isInteractive: true, canEditValue: true,
            opacity: 1, indicatorColor: .blue, helpText: "", isWarning: false)
    }
    var body: some View {
        VStack {
            TrainerVitalMetricCard(title: title("能量", "Energy"), icon: "bolt", tint: .blue,
                current: $current, maximum: $maximum, focus: $focus, currentField: "current",
                maximumField: "maximum", locked: false, editable: true, onLock: {})
            TrainerAmountMetricCard(title: title("数量", "Amount"), icon: "circle", tint: .blue,
                text: $amount, focus: $focus, focusValue: "amount", locked: false, editable: true, onLock: {})
            TrainerCounterMetricCard(title: title("计数", "Counter"), icon: "circle", tint: .blue,
                text: $counter, focus: $focus, focusValue: "counter", detail: nil, editable: true)
            TrainerStatMetricCard(title: title("属性", "Stat"), icon: "circle", text: $stat,
                focus: $focus, focusValue: "stat", suffix: "%", locked: false,
                supported: true, available: true, editable: false, onLock: {})
            TrainerInlineStatEditor(title: title("行内属性", "Inline"), text: $inline,
                focus: $focus, focusValue: "inline", suffix: "%", locked: false,
                supported: true, available: true, editable: true, onLockChange: { _ in })
            TrainerFeatureMultiplierRow(title: title("倍率", "Multiplier"), icon: "circle",
                state: state, text: $multiplier, shortcutText: nil, action: {})
            TrainerFeatureMultiplierRow(title: title("增益倍率", "Gain multiplier"), icon: "circle",
                state: state, text: $gain, shortcutText: nil, action: {})
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
            check(rounded.accessibilityLabel() == "rounded",
                  "a field without a separate semantic name lost its title fallback")
            window.close()

            let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
            let metricWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 850),
                styleMask: [.titled], backing: .buffered, defer: false)
            metricWindow.appearance = NSAppearance(named: appearance)
            let metrics = NSHostingView(rootView: MetricFixture().environmentObject(localization))
            metricWindow.contentView = metrics
            for language in [TrainerPresentationLanguage.zhCN, .en] {
                localization.language = language
                metrics.layoutSubtreeIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.10))
                let inputs = Dictionary(uniqueKeysWithValues: fields(in: metrics).map { ($0.stringValue, $0) })
                let expected = language == .en
                    ? ["11": "Current Energy", "22": "Maximum Energy", "33": "Amount", "44": "Counter",
                       "55": "Stat", "66": "Inline", "77": "Multiplier", "88": "Gain multiplier"]
                    : ["11": "当前能量", "22": "能量上限", "33": "数量", "44": "计数",
                       "55": "属性", "66": "行内属性", "77": "倍率", "88": "增益倍率"]
                check(inputs.count == expected.count, "shared metric fixture did not mount every numeric input")
                for (value, name) in expected {
                    check(inputs[value]?.accessibilityLabel() == name,
                          "numeric field \(value) exposes its placeholder instead of \(name): \(String(describing: inputs[value]?.accessibilityLabel()))")
                }
                check(inputs["11"]?.placeholderString == "—" && inputs["77"]?.placeholderString == "2",
                      "semantic field names changed the visual placeholders")
                check(inputs["55"]?.isEnabled == false, "naming a disabled field changed its capability")
            }
            let amount = fields(in: metrics).first { $0.stringValue == "33" }!
            check(metricWindow.makeFirstResponder(amount), "could not focus the named amount input")
            let editor = amount.currentEditor() as! NSTextView
            editor.selectAll(nil); editor.insertText("39", replacementRange: editor.selectedRange())
            localization.language = .zhCN
            RunLoop.current.run(until: Date().addingTimeInterval(0.10))
            check(editor.string == "39" && amount.accessibilityLabel() == "数量",
                  "live label localization replaced the focused native draft")
            metricWindow.makeFirstResponder(nil)
            metricWindow.close()
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
    for language in ("zh-CN", "en"):
        localized = directory / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", localized / "Host.strings")
    subprocess.run([
        SWIFTC, "-parse-as-library",
        *map(str, sorted((ROOT / "Sources/Core").rglob("*.swift"))),
        str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
        str(swift), "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=15)
