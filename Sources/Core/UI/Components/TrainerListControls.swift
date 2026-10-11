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

    var body: some View {
        TrainerTextField(title: placeholder, text: $text, onCommit: { draft in
            text = draft.text
            onCommit()
            return text
        }, onCancel: onCancel, focusOnAppear: true,
            style: .plain, font: .systemFont(ofSize: NSFont.systemFontSize, weight: .semibold))
            .trainerDismissTextEditingOnClickAway()
    }
}

struct TrainerSelectionControl: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
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
        .accessibilityLabel(localization.localized(selected ? "host.selection.deselect" : "host.selection.select"))
        .accessibilityValue(localization.localized(selected ? "host.selection.selected" : "host.selection.notSelected"))
    }
}

struct TrainerOverflowMenu<Content: View>: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
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
        .help(localization.localized("host.more"))
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
