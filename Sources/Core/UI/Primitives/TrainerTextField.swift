import AppKit
import SwiftUI

/// The native field owns a draft until editing ends. The caller validates one
/// completed value and returns the text to display; no keystroke is a commit.
struct TrainerTextField: NSViewRepresentable {
    enum Style { case plain, rounded }
    struct Completion {
        let text: String
        let changed: Bool
    }
    @Environment(\.isEnabled) private var enabled
    let title: String
    @Binding var text: String
    var accessibilityLabel: String? = nil
    var onEditingChanged: (Bool) -> Void = { _ in }
    var onCommit: (Completion) -> String = { $0.text }
    var onCancel: (() -> Void)?
    var focusOnAppear = false
    var style: Style = .rounded
    var alignment: NSTextAlignment = .left
    var font: NSFont = .systemFont(ofSize: NSFont.systemFontSize)

    final class Coordinator: NSObject, NSTextFieldDelegate {
        struct Edit {
            let initial: String
            let text: Binding<String>
            let onEditingChanged: (Bool) -> Void
            let onCommit: (Completion) -> String
            let onCancel: (() -> Void)?
        }
        var parent: TrainerTextField
        var edit: Edit?
        private static var pendingCancellations: [() -> Void] = []
        init(_ parent: TrainerTextField) { self.parent = parent }

        private static func finishPendingCancellations() {
            let notifications = pendingCancellations
            pendingCancellations.removeAll()
            for notify in notifications { notify() }
        }

        func begin() {
            guard edit == nil else { return }
            // A replacement can acquire native focus before the queued teardown
            // callback runs. End the old edit before announcing the new one.
            Self.finishPendingCancellations()
            edit = Edit(initial: parent.text, text: parent.$text,
                onEditingChanged: parent.onEditingChanged, onCommit: parent.onCommit,
                onCancel: parent.onCancel)
            edit?.onEditingChanged(true)
        }
        func control(_ control: NSControl, textShouldBeginEditing fieldEditor: NSText) -> Bool {
            begin()
            return true
        }
        func controlTextDidBeginEditing(_ notification: Notification) { begin() }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField, let edit else { return }
            edit.text.wrappedValue = field.stringValue
        }
        func controlTextDidEndEditing(_ notification: Notification) {
            guard let field = notification.object as? NSTextField, let completed = edit else { return }
            edit = nil
            let draft = field.stringValue
            let normalized = completed.onCommit(Completion(text: draft, changed: draft != completed.initial))
            completed.text.wrappedValue = normalized
            field.stringValue = normalized
            completed.onEditingChanged(false)
        }
        func control(_ control: NSControl, textView: NSTextView, doCommandBy command: Selector) -> Bool {
            if command == #selector(NSResponder.cancelOperation(_:)), !textView.hasMarkedText(),
               let cancelled = edit, let onCancel = cancelled.onCancel,
               let field = control as? NSTextField {
                edit = nil
                field.window?.makeFirstResponder(nil)
                cancelled.text.wrappedValue = cancelled.initial
                field.stringValue = cancelled.initial
                cancelled.onEditingChanged(false)
                onCancel()
                return true
            }
            guard command == #selector(NSResponder.insertNewline(_:)), !textView.hasMarkedText() else { return false }
            // Consume Return after a real resignation; AppKit otherwise reselects
            // the field after its normal Return action and keeps the editor open.
            return control.window?.makeFirstResponder(nil) == true
        }
        func cancel(_ field: NSTextField) {
            let cancelled = edit
            edit = nil
            field.delegate = nil
            if field.currentEditor() != nil { field.window?.makeFirstResponder(nil) }
            if let notify = cancelled?.onEditingChanged {
                // Dismantling runs inside a SwiftUI update. Its owner may mutate
                // State or a published model when this edit ends.
                Self.pendingCancellations.append { notify(false) }
                DispatchQueue.main.async { Self.finishPendingCancellations() }
            }
        }
    }

    final class Field: NSTextField {
        var focusOnAppear = false
        var onFocus: (() -> Void)?
        private var didRequestFocus = false
        override func becomeFirstResponder() -> Bool {
            let acquired = super.becomeFirstResponder()
            if acquired { onFocus?() }
            return acquired
        }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            guard focusOnAppear, !didRequestFocus, let window else { return }
            didRequestFocus = true
            DispatchQueue.main.async { [weak self, weak window] in
                guard let self, let window, self.window === window else { return }
                window.makeFirstResponder(self)
            }
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeNSView(context: Context) -> NSTextField {
        let field = Field(frame: .zero)
        field.focusOnAppear = focusOnAppear
        field.onFocus = { [weak coordinator = context.coordinator] in coordinator?.begin() }
        field.delegate = context.coordinator
        field.isEditable = true
        field.isSelectable = true
        field.usesSingleLineMode = true
        field.lineBreakMode = .byClipping
        field.setContentHuggingPriority(.defaultLow, for: .horizontal)
        configure(field)
        field.stringValue = text
        return field
    }
    func updateNSView(_ field: NSTextField, context: Context) {
        context.coordinator.parent = self
        configure(field)
        // A background observation can update the source without replacing the
        // native draft or the callback/target captured when editing began.
        if context.coordinator.edit == nil && field.stringValue != text { field.stringValue = text }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextField, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? nsView.intrinsicContentSize.width, height: nsView.intrinsicContentSize.height)
    }
    static func dismantleNSView(_ field: NSTextField, coordinator: Coordinator) { coordinator.cancel(field) }

    private func configure(_ field: NSTextField) {
        // Assigning an unchanged AppKit control property can invalidate the
        // intrinsic size while SwiftUI is measuring this representable. Keep
        // configuration idempotent during a completed edit's state refresh.
        if field.placeholderString != title { field.placeholderString = title }
        let label = accessibilityLabel ?? title
        if field.accessibilityLabel() != label { field.setAccessibilityLabel(label) }
        if field.font != font { field.font = font }
        if field.alignment != alignment { field.alignment = alignment }
        if field.isEnabled != enabled { field.isEnabled = enabled }
        // AppKit clears a bezel when isBordered is assigned, even false.
        // The native rounded bezel draws its own background.
        let rounded = style == .rounded
        if field.isBezeled != rounded { field.isBezeled = rounded }
        if rounded && field.bezelStyle != .roundedBezel { field.bezelStyle = .roundedBezel }
        if field.drawsBackground { field.drawsBackground = false }
        if field.textColor != .labelColor { field.textColor = .labelColor }
    }

    static func editingTracker<Field: Hashable>(_ focus: Binding<Field?>, equals field: Field) -> (Bool) -> Void {
        { active in
            if active { focus.wrappedValue = field }
            else if focus.wrappedValue == field { focus.wrappedValue = nil }
        }
    }

    static func metricFont(size: CGFloat) -> NSFont {
        let font = NSFont.monospacedDigitSystemFont(ofSize: size, weight: .semibold)
        return font.fontDescriptor.withDesign(.rounded).flatMap { NSFont(descriptor: $0, size: size) } ?? font
    }
}

/// Observe clicks without consuming them or installing a gesture over controls.
enum TrainerTextEditingDismissal {
    static func handle(_ event: NSEvent, in window: NSWindow) -> NSEvent {
        guard event.window === window, event.type == .leftMouseDown,
              let editor = window.firstResponder as? NSTextView,
              editor.isFieldEditor, let field = editor.delegate as? NSTextField else { return event }
        let point = field.convert(event.locationInWindow, from: nil)
        if !field.bounds.contains(point) { window.makeFirstResponder(nil) }
        return event
    }
}

private struct TrainerTextEditingClickObserver: NSViewRepresentable {
    final class Observer: NSView {
        private var monitor: Any?
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            guard let window else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { [weak window] event in
                guard let window else { return event }
                return TrainerTextEditingDismissal.handle(event, in: window)
            }
        }
        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }
        deinit { stop() }
    }
    func makeNSView(context: Context) -> Observer { Observer() }
    func updateNSView(_ view: Observer, context: Context) {}
    static func dismantleNSView(_ view: Observer, coordinator: ()) { view.stop() }
}

extension View {
    func trainerDismissTextEditingOnClickAway() -> some View {
        background(TrainerTextEditingClickObserver().allowsHitTesting(false))
    }
}
