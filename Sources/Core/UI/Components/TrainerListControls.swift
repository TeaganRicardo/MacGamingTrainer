import AppKit
import SwiftUI

struct TrainerPrimaryActionButton: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let systemImage: String?
    let enabled: Bool
    let action: () -> Void

    init(
        title: String,
        systemImage: String? = nil,
        enabled: Bool = true,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.systemImage = systemImage
        self.enabled = enabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            if let systemImage {
                Label(title, systemImage: systemImage)
            } else {
                Text(title)
            }
        }
        .buttonStyle(.borderedProminent)
        .tint(theme.accent)
        .disabled(!enabled)
    }
}

struct TrainerInlineNameEditor: View {
    @Binding var text: String
    let placeholder: String
    let onCommit: () -> Void
    let onCancel: () -> Void

    @FocusState private var focused: Bool
    @State private var eventMonitor: Any?
    @State private var finished = false

    var body: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.plain)
            .font(.headline.weight(.semibold))
            .focused($focused)
            .onSubmit { finish(commit: true) }
            .onExitCommand { finish(commit: false) }
            .onAppear {
                installClickAwayMonitor()
                DispatchQueue.main.async { focused = true }
            }
            .onDisappear { removeClickAwayMonitor() }
            .onChange(of: focused) { wasFocused, isFocused in
                if wasFocused && !isFocused {
                    finish(commit: true)
                }
            }
    }

    private func installClickAwayMonitor() {
        guard eventMonitor == nil else { return }
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: .leftMouseDown) { event in
            guard !clickIsInsideActiveTextField(event) else { return event }
            DispatchQueue.main.async { finish(commit: true) }
            return event
        }
    }

    private func clickIsInsideActiveTextField(_ event: NSEvent) -> Bool {
        guard let window = event.window,
              let editor = window.firstResponder as? NSTextView,
              let field = editor.delegate as? NSTextField else {
            return false
        }
        let point = field.convert(event.locationInWindow, from: nil)
        return field.bounds.contains(point)
    }

    private func finish(commit: Bool) {
        guard !finished else { return }
        finished = true
        removeClickAwayMonitor()
        focused = false
        if commit {
            onCommit()
        } else {
            onCancel()
        }
    }

    private func removeClickAwayMonitor() {
        guard let eventMonitor else { return }
        NSEvent.removeMonitor(eventMonitor)
        self.eventMonitor = nil
    }
}

struct TrainerSelectionControl: View {
    @Environment(\.trainerTheme) private var theme
    let selected: Bool
    let enabled: Bool
    let helpText: String
    let action: () -> Void

    init(selected: Bool, enabled: Bool = true, helpText: String = "", action: @escaping () -> Void) {
        self.selected = selected
        self.enabled = enabled
        self.helpText = helpText
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: selected ? "checkmark.square.fill" : "square")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(selected ? theme.accent : .secondary)
                .frame(width: 24, height: 24)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(helpText)
        .accessibilityLabel(selected ? "取消选择" : "选择")
        .accessibilityValue(selected ? "已选择" : "未选择")
    }
}

struct TrainerOverflowMenu<Content: View>: View {
    let enabled: Bool
    let content: Content

    init(enabled: Bool = true, @ViewBuilder content: () -> Content) {
        self.enabled = enabled
        self.content = content()
    }

    var body: some View {
        Menu {
            content
        } label: {
            Image(systemName: "ellipsis")
                .font(.body.weight(.semibold))
                .frame(width: 24, height: 24)
                .contentShape(Rectangle())
        }
        .menuIndicator(.hidden)
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(!enabled)
        .help("更多")
    }
}

struct TrainerEmptyState: View {
    @Environment(\.trainerTheme) private var theme
    let text: String

    var body: some View {
        Text(text)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, theme.emptyStatePadding)
    }
}

struct TrainerInlineNotice<Content: View>: View {
    let color: Color
    let content: Content

    init(color: Color, @ViewBuilder content: () -> Content) {
        self.color = color
        self.content = content()
    }

    var body: some View {
        content
            .padding(10)
            .background(color.opacity(0.09), in: RoundedRectangle(cornerRadius: 9))
    }
}

struct TrainerListCard<Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content
            .padding(12)
            .background(theme.subtleFill.opacity(0.875), in: RoundedRectangle(cornerRadius: theme.controlCornerRadius))
    }
}

private struct TrainerGroupedRowsModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme

    func body(content: Content) -> some View {
        content.clipShape(RoundedRectangle(cornerRadius: theme.panelCornerRadius))
    }
}

extension View {
    func trainerGroupedRows() -> some View {
        modifier(TrainerGroupedRowsModifier())
    }
}
