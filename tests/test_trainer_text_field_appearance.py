"""Exercise the real shared SwiftUI/AppKit text control on macOS."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from native_picker_harness import NATIVE_PICKER

if sys.platform != "darwin":
    raise SystemExit("macOS-only AppKit text field presentation")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import AppKit
import QuartzCore
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func fields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

func pump(_ seconds: TimeInterval = 0.08) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

@MainActor
final class InputModel: ObservableObject {
    @Published var text = "12"
    @Published var enabled = true
    @Published var selection = "first"
    @Published var search = ""
    @Published var amounts = ["first": "20", "second": "80"]
    var commits: [String] = []
    var resourceCommits: [(String, String)] = []
}

struct InputOption: Identifiable {
    let id: String
    let title: String
}

// Read the actual production role's allocation independently of AppKit's
// native bezel. A localized popup can be narrower inside that allocation.
struct PickerAllocationProbe: NSViewRepresentable {
    final class Frame: NSView {}
    func makeNSView(context: Context) -> Frame { Frame() }
    func updateNSView(_ view: Frame, context: Context) {}
}

private func pickerAllocation(_ view: NSView) -> NSView? {
    if view is PickerAllocationProbe.Frame { return view }
    return view.subviews.lazy.compactMap(pickerAllocation).first
}

struct InputFixture: View {
    @ObservedObject var model: InputModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        let target = model.selection
        VStack(spacing: 16) {
            TrainerTextField(title: "Input", text: $model.text, onCommit: { completion in
                guard let value = Int(completion.text), value >= 0 else {
                    return completion.rejected(message: "Enter a whole number.")
                }
                if completion.changed { model.commits.append(String(value)) }
                return String(value)
            })
            .frame(width: 96)
            .disabled(!model.enabled)
            TrainerResourceEditor(title: "Resource", icon: "circle", search: $model.search,
                selection: $model.selection,
                amount: Binding(get: { model.amounts[target]! }, set: { model.amounts[target] = $0 }),
                sections: [.init(id: 0, title: "", items: [
                    InputOption(id: "first", title: localization.language == .en ? "First resource" : "第一种材料"),
                    InputOption(id: "second", title: localization.language == .en ? "Second resource with a longer name" : "名称较长的第二种材料")])],
                enabled: model.enabled, locked: false, itemLabel: { $0.title }, onLock: {},
                onCommit: { completion in
                    if completion.changed { model.resourceCommits.append((target, completion.text)) }
                    return completion.text
                })
        }
        .padding(12)
    }
}

func edit(_ field: NSTextField, _ text: String, in window: NSWindow) -> NSTextView {
    check(window.makeFirstResponder(field), "native field refused focus")
    guard let editor = field.currentEditor() as? NSTextView else { fatalError("native editor missing") }
    editor.selectAll(nil)
    editor.insertText(text, replacementRange: editor.selectedRange())
    return editor
}

@MainActor
func exerciseInput(appearance: NSAppearance.Name) {
    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    let model = InputModel()
    let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 250),
                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.appearance = NSAppearance(named: appearance)
    let host = NSHostingView(rootView: InputFixture(model: model).environmentObject(localization))
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    window.makeFirstResponder(nil)
    host.layoutSubtreeIfNeeded(); pump()
    window.makeFirstResponder(nil); pump()
    guard let field = fields(in: host).first(where: { $0.placeholderString == "Input" }) as? TrainerTextField.Field else {
        fatalError("shared interaction field missing")
    }
    check(field.presentation == .idle && field.focusRingType != .none, "default appearance removed native focus semantics")
    let bounds = field.bounds
    let hover = NSEvent.enterExitEvent(with: .mouseEntered, location: .zero, modifierFlags: [], timestamp: 0,
        windowNumber: window.windowNumber, context: nil, eventNumber: 1, trackingNumber: 0, userData: nil)!
    field.mouseEntered(with: hover)
    check(field.presentation == .hovered, "pointer entry did not reveal hover emphasis")
    field.mouseExited(with: hover)
    let editor = edit(field, "17", in: window)
    check(field.presentation == .focused, "native focus did not reveal focused appearance")
    model.text = "900"; pump()
    check(editor.string == "17" && field.currentEditor() === editor && model.commits.isEmpty,
          "external refresh stole focus, reset the draft, or submitted it")
    editor.doCommand(by: #selector(NSResponder.insertNewline(_:)))
    window.makeFirstResponder(nil); pump()
    check(model.commits == ["17"] && field.stringValue == "17" && field.currentEditor() == nil,
          "Return and subsequent blur did not complete exactly once")
    edit(field, "bad", in: window).doCommand(by: #selector(NSResponder.insertNewline(_:)))
    let invalidStroke = field.layer?.sublayers?.compactMap { $0 as? CAShapeLayer }.first
    check(invalidStroke?.opacity == 1 && invalidStroke?.lineDashPattern?.isEmpty == false
          && invalidStroke?.animation(forKey: "field.emphasis") == nil,
          "validation was delayed by motion or relied on color alone")
    pump(0.25)
    check(field.presentation == .invalid && field.validationMessage == "Enter a whole number."
          && field.accessibilityHelp() == field.validationMessage && field.toolTip == field.validationMessage,
          "rejected completion lost visible or accessible recovery feedback")
    check(field.bounds == bounds && field.stringValue == "bad" && model.commits == ["17"],
          "validation moved the control, erased the rejected draft, or committed it")
    edit(field, "bad", in: window).doCommand(by: #selector(NSResponder.insertNewline(_:)))
    check(field.presentation == .invalid, "unchanged invalid completion hid the error")
    edit(field, "18", in: window).doCommand(by: #selector(NSResponder.insertNewline(_:)))
    check(field.validationMessage == nil && model.commits == ["17", "18"], "correction did not recover once")
    edit(field, "19", in: window).doCommand(by: #selector(NSResponder.cancelOperation(_:)))
    window.makeFirstResponder(nil); pump()
    check(field.currentEditor() == nil && field.stringValue == "18" && model.text == "18"
          && model.commits == ["17", "18"], "Escape committed a generic numeric draft or lost its original value")
    model.enabled = false; pump()
    check(!field.isEnabled && field.presentation == .disabled && field.stringValue == "18",
          "disabled field lost its native appearance or displayed value")
    model.enabled = true; model.text = "21"; pump()
    check(field.stringValue == "21" && field.validationMessage == nil, "idle observation failed to replace the display")
    check(TrainerMotion.duration(.selection, reduceMotion: true) == 0
          && TrainerMotion.duration(.selection, reduceMotion: false) > 0,
          "native field emphasis ignored the shared Reduce Motion policy")
    print("trainer_field_actual_reduce_motion=\(field.reduceMotion)")

    // Exercise the actual SwiftUI Picker through its native AX popup and menu,
    // while the adjacent number field retains the selected resource identity.
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language; pump(); host.layoutSubtreeIfNeeded()
        guard let popup = namedNativeControl(host, role: "AXPopUpButton", name: "Resource") else {
            fatalError("SwiftUI Picker did not materialize its native popup")
        }
        let width = popup.frame.width
        let hostBounds = window.convertToScreen(host.convert(host.bounds, to: nil))
        guard let allocation = pickerAllocation(host) else { fatalError("production picker allocation probe missing") }
        let allocationFrame = window.convertToScreen(allocation.convert(allocation.bounds, to: nil))
        print("input_picker_geometry language=\(language.rawValue) allocation=\(allocationFrame) native=\(popup.frame)")
        check(allocationFrame.width >= TrainerTheme.standard.pickerStandardWidth && hostBounds.contains(allocationFrame),
              "picker role lost its visible minimum width allocation")
        check(!popup.frame.isEmpty && allocationFrame.contains(popup.frame) && hostBounds.contains(popup.frame),
              "native picker bezel is empty or clipped within its semantic allocation")
        guard let amount = fields(in: host).first(where: { $0.stringValue == model.amounts["first"]! }) else {
            fatalError("selected resource amount missing")
        }
        let before = model.resourceCommits.count
        _ = edit(amount, "34", in: window)
        let click = NSEvent.mouseEvent(with: .leftMouseDown,
            location: window.convertPoint(fromScreen: NSPoint(x: popup.frame.midX, y: popup.frame.midY)),
            modifierFlags: [], timestamp: 0, windowNumber: window.windowNumber,
            context: nil, eventNumber: 2, clickCount: 1, pressure: 1)!
        check(TrainerTextEditingDismissal.handle(click, in: window) === click,
              "click-away consumed the native picker event")
        let secondTitle = language == .en ? "Second resource with a longer name" : "名称较长的第二种材料"
        selectNativePicker(popup, in: window, moving: 1, opening: language == .en ? .pointer : .keyboard)
        pump()
        let selectedPopup = namedNativeControl(host, role: "AXPopUpButton", name: "Resource")!
        check(model.selection == "second" && selectedPopup.valueText == secondTitle,
              "native pointer/keyboard opening and Arrow/Return selection did not show the selected value")
        check(selectedPopup.frame.width == width, "a longer bilingual picker value changed its semantic width")
        check(window.convertToScreen(allocation.convert(allocation.bounds, to: nil)) == allocationFrame
              && allocationFrame.contains(selectedPopup.frame),
              "native selection moved its semantic allocation or clipped its new value")
        check(model.resourceCommits.count == before + (language == .en ? 1 : 0)
              && model.resourceCommits.first?.0 == "first" && model.resourceCommits.first?.1 == "34",
              "picker selection duplicated the old amount or sent it to the replacement resource")
        guard let replacement = fields(in: host).first(where: { $0.stringValue == "80" }) else {
            fatalError("picker selection did not replace the numeric field identity")
        }
        _ = edit(replacement, "99", in: window)
        model.selection = "first"; pump()
        window.makeFirstResponder(nil); pump()
        check(model.amounts["first"] == "34" && model.resourceCommits.count == 1,
              "a replaced numeric editor committed its abandoned draft")
        model.amounts["second"] = "80"
    }
    window.close()
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
        enableNativeAccessibility()
        for appearance in [NSAppearance.Name.aqua, .darkAqua] {
            exerciseInput(appearance: appearance)
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
    swift.write_text(HARNESS + NATIVE_PICKER)
    for language in ("zh-CN", "en"):
        localized = directory / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", localized / "Host.strings")
    # Observe the real ResourceEditor picker after its production width role.
    # The background neither sizes the picker nor handles input/accessibility;
    # it exists only in this temporary compilation, with no product test hook.
    resource_source = ROOT / "Sources/Core/UI/Components/TrainerResourceControls.swift"
    resource_text = resource_source.read_text()
    allocation_anchor = """                .trainerPickerWidth(.flexible)
                .disabled(!enabled || sections.allSatisfy({ $0.items.isEmpty }))"""
    assert resource_text.count(allocation_anchor) == 1, "actual resource picker role changed"
    observed_resource = directory / "TrainerResourceControls.swift"
    observed_resource.write_text(resource_text.replace(allocation_anchor, """                .trainerPickerWidth(.flexible)
                .background(PickerAllocationProbe().allowsHitTesting(false).accessibilityHidden(true))
                .disabled(!enabled || sections.allSatisfy({ $0.items.isEmpty }))"""))
    core_sources = [observed_resource if source == resource_source else source
                    for source in sorted((ROOT / "Sources/Core").rglob("*.swift"))]
    subprocess.run([
        SWIFTC, "-parse-as-library",
        *map(str, core_sources),
        str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
        str(ROOT / "tests/fixtures/swift/NativeAccessibility.swift"),
        str(swift), "-o", str(binary),
    ], cwd=ROOT, check=True)
    subprocess.run([str(binary)], cwd=ROOT, check=True, timeout=15)
