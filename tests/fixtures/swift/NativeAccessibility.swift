import AppKit

/// Inspect the synthetic app's actual accessibility nodes. SwiftUI's nodes
/// implement AppKit's documented selectors without adopting the full modern
/// NSAccessibility protocol, so its protocol cast discards real controls.
struct NativeAccessibilityControl {
    let object: NSObject

    private func value(_ name: String) -> Any? {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector) else { return nil }
        return object.perform(selector)?.takeUnretainedValue()
    }

    private func boolean(_ name: String) -> Bool {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector) else { return false }
        typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
        return unsafeBitCast(object.method(for: selector), to: Getter.self)(object, selector)
    }

    var role: String? { value("accessibilityRole") as? String }
    var label: String? { value("accessibilityLabel") as? String }
    // AppKit exposes static text through AXValue, including its authored
    // accessibility label. Interactive controls retain their separate label.
    var text: String? { label ?? value("accessibilityValue") as? String }
    var valueText: String? { value("accessibilityValue") as? String }
    var help: String? { value("accessibilityHelp") as? String }
    var identifier: String? { value("accessibilityIdentifier") as? String }
    var enabled: Bool { boolean("isAccessibilityEnabled") }
    func press() -> Bool { boolean("accessibilityPerformPress") }
    var children: [Any] { value("accessibilityChildren") as? [Any] ?? [] }
    var frame: NSRect {
        let selector = NSSelectorFromString("accessibilityFrame")
        guard object.responds(to: selector) else { return .zero }
        typealias Getter = @convention(c) (AnyObject, Selector) -> NSRect
        return unsafeBitCast(object.method(for: selector), to: Getter.self)(object, selector)
    }
}

func nativeAccessibilityControls(_ root: Any) -> [NativeAccessibilityControl] {
    var seen = Set<ObjectIdentifier>()
    func visit(_ value: Any) -> [NativeAccessibilityControl] {
        guard let object = value as? NSObject,
              seen.insert(ObjectIdentifier(object)).inserted else { return [] }
        let control = NativeAccessibilityControl(object: object)
        return [control] + control.children.flatMap(visit)
    }
    return visit(root)
}

func namedNativeControl(_ root: Any, role: String, name: String) -> NativeAccessibilityControl? {
    nativeAccessibilityControls(root).first {
        $0.role == role && (role == "AXStaticText" ? $0.text : $0.label) == name
    }
}

func enableNativeAccessibility() {
    // Activate lazy SwiftUI AX nodes in this fixture process only. This neither
    // enables VoiceOver nor changes a user preference or another application.
    NSApp.accessibilitySetValue(true, forAttribute: .init(rawValue: "AXEnhancedUserInterface"))
}
