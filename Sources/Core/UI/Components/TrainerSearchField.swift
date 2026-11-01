import AppKit
import SwiftUI

/// One shared search-field treatment for feature panels and larger workbenches.
struct TrainerSearchField: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @FocusState private var localFocus: Bool
    @State private var hovered = false
    @State private var nativeInput = TrainerSearchNativeInput()
    @Binding var text: String
    let placeholder: String
    let clearLabel: String?
    let focus: FocusState<Bool>.Binding?
    let onSubmit: () -> Void
    let onMoveSelection: ((Int) -> Bool)?

    init(
        text: Binding<String>,
        placeholder: String,
        clearLabel: String? = nil,
        focus: FocusState<Bool>.Binding? = nil,
        onSubmit: @escaping () -> Void = {},
        onMoveSelection: ((Int) -> Bool)? = nil
    ) {
        self._text = text
        self.placeholder = placeholder
        self.clearLabel = clearLabel
        self.focus = focus
        self.onSubmit = onSubmit
        self.onMoveSelection = onMoveSelection
    }

    var showsClearAction: Bool { !text.isEmpty && clearLabel != nil }

    func clearSearch() {
        text = ""
        onSubmit()
    }

    private var textField: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.plain)
            .onSubmit {
                guard !nativeInput.consumeComposition(.submit) else { return }
                onSubmit()
            }
            .onKeyPress(.upArrow) { moveSelection(by: -1) }
            .onKeyPress(.downArrow) { moveSelection(by: 1) }
            .accessibilityLabel(placeholder)
            .background {
                if onMoveSelection != nil {
                    TrainerSearchInputObserver(input: nativeInput, enabled: enabled)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }
    }

    private var focused: Bool { focus?.wrappedValue ?? localFocus }

    private func moveSelection(by offset: Int) -> KeyPress.Result {
        // Let the input method handle its own candidate list. Ordinary fields
        // without discovery results also keep native text-navigation behavior.
        guard let onMoveSelection,
              !nativeInput.consumeComposition(.moveSelection(offset)),
              (NSApp.keyWindow?.firstResponder as? NSTextView)?.hasMarkedText() != true else { return .ignored }
        return onMoveSelection(offset) ? .handled : .ignored
    }

    var body: some View {
        HStack(spacing: theme.compactControlSpacing) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            textField.focused(focus ?? $localFocus)
            if showsClearAction, let clearLabel {
                Button(action: clearSearch) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help(clearLabel)
                .accessibilityLabel(clearLabel)
                .accessibilityIdentifier("trainer.search.clear")
            }
        }
        .padding(theme.controlPadding)
        .trainerSurface(.subtle, cornerRadius: theme.controlCornerRadius)
        .overlay {
            RoundedRectangle(cornerRadius: theme.controlCornerRadius)
                .strokeBorder(focused ? theme.accent : Color.secondary.opacity(0.5), lineWidth: focused ? 1.5 : 1)
                .opacity(enabled && (focused || hovered) ? 1 : 0)
                .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: focused)
                .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: hovered)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
        .onHover { hovered = $0 }
    }
}

/// AppKit can finish marked text before SwiftUI invokes an application command.
/// Record only commands this field owns, and retire the record when its callback
/// consumes it. A later AX Confirm is a separate action even without a new key.
private final class TrainerSearchNativeInput {
    enum Command: Equatable {
        case submit
        case moveSelection(Int)
    }

    private var composingCommand: Command?

    func recordComposingCommand(_ event: NSEvent) {
        let characters = [event.characters, event.charactersIgnoringModifiers].compactMap { $0 }
        if characters.contains(where: { $0 == "\r" || $0 == "\n" || $0 == "\u{3}" }) {
            composingCommand = .submit
        } else if characters.contains(String(UnicodeScalar(NSUpArrowFunctionKey)!)) {
            composingCommand = .moveSelection(-1)
        } else if characters.contains(String(UnicodeScalar(NSDownArrowFunctionKey)!)) {
            composingCommand = .moveSelection(1)
        } else {
            composingCommand = nil
        }
    }

    func consumeComposition(_ command: Command) -> Bool {
        let captured = composingCommand
        composingCommand = nil
        return captured == command
    }

    func reset() { composingCommand = nil }
}

private struct TrainerSearchInputObserver: NSViewRepresentable {
    let input: TrainerSearchNativeInput
    let enabled: Bool

    final class Observer: NSView {
        weak var input: TrainerSearchNativeInput?
        private var monitor: Any?
        private var enabled = false

        func configure(input: TrainerSearchNativeInput, enabled: Bool) {
            if self.input !== input || self.enabled != enabled { stop() }
            self.input = input
            self.enabled = enabled
            start()
        }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            stop()
            start()
        }

        private func start() {
            guard enabled, window != nil, monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .leftMouseDown, .rightMouseDown, .otherMouseDown]) {
                [weak self] event in
                guard let self else { return event }
                // A new input replaces the previous command's ownership. Do
                // not clear it on a timer: input methods can run nested loops
                // before the same key's eventual submit callback.
                self.input?.reset()
                guard event.type == .keyDown, event.window === self.window,
                      !self.isHiddenOrHasHiddenAncestor,
                      let editor = self.window?.firstResponder as? NSTextView,
                      editor.isFieldEditor, let field = editor.delegate as? NSTextField,
                      field.window === self.window,
                      self.bounds.contains(self.convert(NSPoint(x: field.bounds.midX, y: field.bounds.midY), from: field))
                else { return event }
                if editor.hasMarkedText() { self.input?.recordComposingCommand(event) }
                return event
            }
        }

        func stop() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
            input?.reset()
        }

        deinit { stop() }
    }

    func makeNSView(context: Context) -> Observer {
        let view = Observer()
        view.configure(input: input, enabled: enabled)
        return view
    }

    func updateNSView(_ view: Observer, context: Context) {
        view.configure(input: input, enabled: enabled)
    }

    static func dismantleNSView(_ view: Observer, coordinator: ()) { view.stop() }
}
