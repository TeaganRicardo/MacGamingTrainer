import AppKit
import QuartzCore
import SwiftUI

private struct TrainerDisclosureExpandedKey: EnvironmentKey {
    static let defaultValue = true
}

extension EnvironmentValues {
    var trainerDisclosureExpanded: Bool {
        get { self[TrainerDisclosureExpandedKey.self] }
        set { self[TrainerDisclosureExpandedKey.self] = newValue }
    }
}

/// The native field owns a draft until editing ends. The caller validates one
/// completed value and returns the text to display; no keystroke is a commit.
struct TrainerTextField: NSViewRepresentable {
    enum Style { case plain, rounded }
    struct Completion {
        let text: String
        let changed: Bool
        private final class Validation { var message: String? }
        private let validation = Validation()

        init(text: String, changed: Bool) {
            self.text = text
            self.changed = changed
        }

        /// The game validates once at its existing completion owner. Returning
        /// the display text preserves its recovery policy while this result
        /// gives the originating field an explicit, localized rejection.
        func rejected(message: String, restoring text: String? = nil) -> String {
            validation.message = message
            return text ?? self.text
        }

        fileprivate var validationMessage: String? { validation.message }
    }
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.trainerDisclosureExpanded) private var disclosureExpanded
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
        private enum NativeLifetime { case live, suspending, retired }
        private struct SuspendedDraft {
            let generation: UInt
            let initial: String
            let text: String
            var publicationPending = true
        }
        struct Edit {
            let initial: String
            let initialValidationMessage: String?
            let text: Binding<String>
            let onEditingChanged: (Bool) -> Void
            let onCommit: (Completion) -> String
            let onCancel: (() -> Void)?
            var draftBeforeNativeDisable: String? = nil
        }
        var parent: TrainerTextField
        var edit: Edit?
        private var nativeLifetime: NativeLifetime = .live
        private var suspensionGeneration: UInt = 0
        private var suspendedDraft: SuspendedDraft?
        private static var pendingCancellations: [() -> Void] = []
        init(_ parent: TrainerTextField) { self.parent = parent }

        var acceptsSourceObservation: Bool {
            guard case .live = nativeLifetime else { return false }
            return edit == nil && suspendedDraft?.publicationPending != true
        }

        func observeSource(_ text: String) {
            if let suspendedDraft, !suspendedDraft.publicationPending, suspendedDraft.text != text {
                self.suspendedDraft = nil
            }
        }

        func captureDraftBeforeNativeDisable(_ field: NSTextField) {
            guard case .live = nativeLifetime, edit != nil,
                  let editor = field.currentEditor(), editor.delegate as? NSTextField === field else { return }
            // SwiftUI can disable AppKit's control before updateNSView delivers
            // the collapsed disclosure environment. Read its still-owned editor
            // before AppKit discards an unfinished composition; reading a control
            // or cell value here would itself validate the edit.
            edit?.draftBeforeNativeDisable = editor.string
        }

        func discardDraftBeforeNativeDisable() {
            edit?.draftBeforeNativeDisable = nil
        }

        private static func finishPendingCancellations() {
            let notifications = pendingCancellations
            pendingCancellations.removeAll()
            for notify in notifications { notify() }
        }

        func begin(validationMessage: String? = nil) {
            guard case .live = nativeLifetime, edit == nil else { return }
            // A replacement can acquire native focus before the queued teardown
            // callback runs. End the old edit before announcing the new one.
            Self.finishPendingCancellations()
            // Disclosure did not complete this edit. Keep its original
            // comparison value only while the same native field still shows
            // that draft, and capture callbacks from the current parent.
            let initial = suspendedDraft.flatMap { $0.text == parent.text ? $0.initial : nil } ?? parent.text
            suspendedDraft = nil
            edit = Edit(initial: initial, initialValidationMessage: validationMessage, text: parent.$text,
                onEditingChanged: parent.onEditingChanged, onCommit: parent.onCommit,
                onCancel: parent.onCancel)
            edit?.onEditingChanged(true)
        }
        func control(_ control: NSControl, textShouldBeginEditing fieldEditor: NSText) -> Bool {
            begin(validationMessage: (control as? Field)?.validationMessage)
            return true
        }
        func controlTextDidBeginEditing(_ notification: Notification) {
            begin(validationMessage: (notification.object as? Field)?.validationMessage)
        }
        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField, let edit else { return }
            discardDraftBeforeNativeDisable()
            edit.text.wrappedValue = field.stringValue
        }
        func controlTextDidEndEditing(_ notification: Notification) {
            guard let field = notification.object as? NSTextField, let completed = edit else { return }
            edit = nil
            let draft = field.stringValue
            let completion = Completion(text: draft, changed: draft != completed.initial)
            let normalized = completed.onCommit(completion)
            completed.text.wrappedValue = normalized
            field.stringValue = normalized
            if let field = field as? Field {
                // Revisiting a rejected draft without changing it is not a new
                // validation success. Keep its recovery cue until correction,
                // cancellation, or a replacement observation.
                let previousError = !completion.changed && normalized == draft ? field.validationMessage : nil
                field.finishEditing(validationMessage: completion.validationMessage ?? previousError)
            }
            completed.onEditingChanged(false)
        }
        func control(_ control: NSControl, textView: NSTextView, doCommandBy command: Selector) -> Bool {
            if command == #selector(NSResponder.cancelOperation(_:)), !textView.hasMarkedText(),
               let cancelled = edit,
               let field = control as? NSTextField {
                edit = nil
                field.window?.makeFirstResponder(nil)
                cancelled.text.wrappedValue = cancelled.initial
                field.stringValue = cancelled.initial
                (field as? Field)?.finishEditing(validationMessage: cancelled.initialValidationMessage)
                cancelled.onEditingChanged(false)
                cancelled.onCancel?()
                return true
            }
            guard command == #selector(NSResponder.insertNewline(_:)), !textView.hasMarkedText() else { return false }
            // Consume Return after a real resignation; AppKit otherwise reselects
            // the field after its normal Return action and keeps the editor open.
            return control.window?.makeFirstResponder(nil) == true
        }
        func cancel(_ field: NSTextField) {
            nativeLifetime = .retired
            suspensionGeneration &+= 1
            suspendedDraft = nil
            let cancelled = edit
            edit = nil
            field.delegate = nil
            (field as? Field)?.finishEditing(validationMessage: nil)
            if field.currentEditor() != nil { field.window?.makeFirstResponder(nil) }
            if let notify = cancelled?.onEditingChanged {
                // Dismantling runs inside a SwiftUI update. Its owner may mutate
                // State or a published model when this edit ends.
                Self.pendingCancellations.append { notify(false) }
                DispatchQueue.main.async { Self.finishPendingCancellations() }
            }
        }

        func suspendForDisclosure(_ field: NSTextField) -> Bool {
            guard case .live = nativeLifetime, let suspended = edit else { return false }
            // Resigning AppKit's editor can synchronously call becomeFirstResponder
            // or delegate begin again. That callback cannot recreate edit authority.
            nativeLifetime = .suspending
            defer { if case .suspending = nativeLifetime { nativeLifetime = .live } }
            let draft = suspended.draftBeforeNativeDisable ?? field.currentEditor()?.string ?? field.stringValue
            suspensionGeneration &+= 1
            let generation = suspensionGeneration
            suspendedDraft = SuspendedDraft(generation: generation, initial: suspended.initial, text: draft)
            edit = nil
            // Layout retirement is not edit completion. Keep the visible draft,
            // including an unfinished input-method composition, without sending
            // an onCommit or redirecting the captured edit to another target.
            if field.currentEditor() != nil { field.window?.makeFirstResponder(nil) }
            field.stringValue = draft
            if let field = field as? Field {
                field.finishEditing(validationMessage: field.validationMessage)
            }
            Self.pendingCancellations.append { [weak self] in
                // A native replacement may reuse the module's draft binding.
                // Only this still-live suspension may publish to that binding;
                // its old editing owner must end even when publication retires.
                if let self, let pending = self.suspendedDraft, pending.generation == generation {
                    suspended.text.wrappedValue = pending.text
                    if self.suspendedDraft?.generation == generation { self.suspendedDraft?.publicationPending = false }
                }
                suspended.onEditingChanged(false)
            }
            DispatchQueue.main.async { Self.finishPendingCancellations() }
            return true
        }
    }

    final class Field: NSTextField {
        enum Presentation: Equatable { case idle, hovered, focused, invalid, disabled }
        var focusOnAppear = false
        var onFocus: (() -> Void)?
        var reduceMotion = false {
            didSet {
                if reduceMotion { emphasis.removeAnimation(forKey: "field.emphasis") }
            }
        }
        private(set) var validationMessage: String?
        private(set) var presentation = Presentation.idle
        private var editing = false
        private var hovered = false
        private var tracking: NSTrackingArea?
        private let emphasis = CAShapeLayer()
        private var didRequestFocus = false
        override var isEnabled: Bool {
            get { super.isEnabled }
            set {
                if newValue != super.isEnabled, let owner = delegate as? Coordinator {
                    if newValue { owner.discardDraftBeforeNativeDisable() }
                    else { owner.captureDraftBeforeNativeDisable(self) }
                }
                super.isEnabled = newValue
            }
        }
        override func becomeFirstResponder() -> Bool {
            let acquired = super.becomeFirstResponder()
            if acquired {
                editing = true
                updatePresentation()
                onFocus?()
            }
            return acquired
        }

        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            if let tracking { removeTrackingArea(tracking) }
            let area = NSTrackingArea(rect: bounds,
                options: [.mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
                owner: self, userInfo: nil)
            addTrackingArea(area)
            tracking = area
        }

        override func mouseEntered(with event: NSEvent) { hovered = true; updatePresentation() }
        override func mouseExited(with event: NSEvent) { hovered = false; updatePresentation() }

        override func layout() {
            super.layout()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            emphasis.frame = bounds
            emphasis.path = CGPath(roundedRect: bounds.insetBy(dx: 0.75, dy: 0.75),
                                  cornerWidth: isBezeled ? 5 : 3, cornerHeight: isBezeled ? 5 : 3,
                                  transform: nil)
            CATransaction.commit()
        }

        override func viewDidChangeEffectiveAppearance() {
            super.viewDidChangeEffectiveAppearance()
            updatePresentation(force: true)
        }

        func finishEditing(validationMessage: String?) {
            editing = false
            self.validationMessage = validationMessage
            toolTip = validationMessage
            setAccessibilityHelp(validationMessage)
            updatePresentation()
        }

        func refreshObservation() {
            // A replacement of this unfocused displayed value supersedes its
            // old input error; unrelated view updates do not hide that error.
            guard !editing else { return }
            finishEditing(validationMessage: nil)
        }

        func updatePresentation(force: Bool = false) {
            let next: Presentation = !isEnabled ? .disabled
                : validationMessage != nil ? .invalid : editing ? .focused : hovered ? .hovered : .idle
            guard force || emphasis.superlayer == nil || next != presentation else { return }
            wantsLayer = true
            if emphasis.superlayer == nil {
                emphasis.fillColor = nil
                emphasis.opacity = 0
                layer?.addSublayer(emphasis)
            }
            presentation = next
            let opacity: Float = next == .hovered || next == .invalid ? 1 : 0
            let previous = emphasis.presentation()?.opacity ?? emphasis.opacity
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            effectiveAppearance.performAsCurrentDrawingAppearance {
                emphasis.strokeColor = (next == .invalid ? NSColor.systemOrange : NSColor.separatorColor).cgColor
            }
            emphasis.lineWidth = next == .invalid ? 1.5 : 1
            emphasis.lineDashPattern = next == .invalid ? [3, 2] : nil
            emphasis.opacity = opacity
            CATransaction.commit()
            emphasis.removeAnimation(forKey: "field.emphasis")
            let duration = TrainerMotion.duration(.selection, reduceMotion: reduceMotion)
            // Rejection is immediately legible. Only decorative hover emphasis
            // fades; native focus rings, text, and validation never wait for it.
            if duration > 0 && previous != opacity && next != .invalid {
                let animation = CABasicAnimation(keyPath: "opacity")
                animation.fromValue = previous
                animation.toValue = opacity
                animation.duration = duration
                emphasis.add(animation, forKey: "field.emphasis")
            }
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
        field.onFocus = { [weak coordinator = context.coordinator, weak field] in
            coordinator?.begin(validationMessage: field?.validationMessage)
        }
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
        if !disclosureExpanded {
            _ = context.coordinator.suspendForDisclosure(field)
        }
        configure(field)
        if disclosureExpanded {
            // Busy/capability disabling keeps its existing native semantics.
            // Only a confirmed disclosure retirement may consume the snapshot.
            context.coordinator.discardDraftBeforeNativeDisable()
        }
        context.coordinator.observeSource(text)
        // A background observation can update the source without replacing the
        // native draft or the callback/target captured when editing began.
        // Keep that ownership across every update until deferred suspension
        // publication completes, including a rapid reopen before its callback.
        if context.coordinator.acceptsSourceObservation && field.stringValue != text {
            field.stringValue = text
            (field as? Field)?.refreshObservation()
        }
    }
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextField, context: Context) -> CGSize? {
        CGSize(width: proposal.width ?? nsView.intrinsicContentSize.width, height: nsView.intrinsicContentSize.height)
    }
    static func dismantleNSView(_ field: NSTextField, coordinator: Coordinator) { coordinator.cancel(field) }

    private func configure(_ field: NSTextField) {
        // Assigning unchanged AppKit properties during a SwiftUI update can
        // invalidate layout and re-enter the AttributeGraph after edit blur.
        if field.placeholderString != title {
            field.placeholderString = title
        }
        if field.accessibilityLabel() != (accessibilityLabel ?? title) {
            field.setAccessibilityLabel(accessibilityLabel ?? title)
        }
        if field.font != font {
            field.font = font
        }
        if field.alignment != alignment {
            field.alignment = alignment
        }
        if field.isEnabled != enabled {
            field.isEnabled = enabled
        }
        if let field = field as? Field {
            field.reduceMotion = reduceMotion
            field.updatePresentation()
        }
        // AppKit clears a bezel when isBordered is assigned, even false.
        // The native rounded bezel draws its own background.
        if field.isBezeled != (style == .rounded) {
            field.isBezeled = style == .rounded
        }
        if style == .rounded && field.bezelStyle != .roundedBezel {
            field.bezelStyle = .roundedBezel
        }
        if field.drawsBackground {
            field.drawsBackground = false
        }
        if field.textColor != .labelColor {
            field.textColor = .labelColor
        }
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
