import AppKit
import SwiftUI

struct TrainerResetButton: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let title: String
    let enabled: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "arrow.uturn.backward")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .frame(width: 14, height: 16)
        }
        .buttonStyle(.bordered)
        .controlSize(.mini)
        .frame(width: 26, height: 24)
        .disabled(!enabled)
        .transaction { transaction in
            TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
        }
        .help(title)
        .accessibilityLabel(title)
    }
}

struct TrainerSectionButton: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let title: String
    let detail: String?
    let systemImage: String
    let selected: Bool
    let action: () -> Void

    init(title: String, detail: String? = nil, systemImage: String, selected: Bool = false,
         action: @escaping () -> Void) {
        self.title = title
        self.detail = detail
        self.systemImage = systemImage
        self.selected = selected
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: systemImage).frame(width: 20)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.callout).fixedSize(horizontal: false, vertical: true)
                    if let detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
            .background {
                RoundedRectangle(cornerRadius: theme.compactCornerRadius, style: .continuous)
                    .fill(selected ? theme.accent.opacity(0.12) : .clear)
                    .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)
            }
        }
        .buttonStyle(.plain)
        .overlay(alignment: .leading) {
            if selected {
                Capsule()
                    .fill(theme.accent)
                    .frame(width: theme.selectionMarkerWidth(for: contrast), height: 20)
                    .offset(x: -12)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

enum TrainerActionWidthRole {
    case automatic
    case compactRow
    case connection
    case sheet
}

private struct TrainerActionButtonLabel: View {
    let title: String
    let fillsWidth: Bool

    // Labeled actions already describe their purpose. Core renders verb
    // buttons as text only; section icons and icon-only commands stay distinct.
    var body: some View {
        Text(title)
            .lineLimit(1)
            .allowsTightening(true)
            .minimumScaleFactor(0.78)
            .frame(maxWidth: fillsWidth ? .infinity : nil)
    }
}

private struct TrainerActionWidthModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerActionWidth) private var inheritedRowWidth
    let role: TrainerActionWidthRole

    @ViewBuilder
    func body(content: Content) -> some View {
        switch role {
        case .automatic:
            if let inheritedRowWidth {
                content.frame(width: inheritedRowWidth)
            } else {
                content
            }
        case .compactRow:
            content.frame(width: theme.compactActionWidth)
        case .connection:
            content.frame(width: theme.connectionActionWidth)
        case .sheet:
            content.frame(minWidth: theme.compactActionWidth)
        }
    }
}

struct TrainerPrimaryActionButton: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerActionWidth) private var inheritedRowWidth
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let title: String
    let systemImage: String?
    let enabled: Bool
    let widthRole: TrainerActionWidthRole
    let action: () -> Void

    init(
        title: String,
        systemImage: String? = nil,
        enabled: Bool = true,
        widthRole: TrainerActionWidthRole = .automatic,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.systemImage = systemImage
        self.enabled = enabled
        self.widthRole = widthRole
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            TrainerActionButtonLabel(title: title, fillsWidth: widthRole != .sheet && (widthRole != .automatic || inheritedRowWidth != nil))
        }
        .buttonStyle(.borderedProminent)
        .tint(theme.accent)
        .disabled(!enabled)
        .transaction { transaction in
            TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
        }
        .modifier(TrainerActionWidthModifier(role: widthRole))
    }
}

struct TrainerSecondaryActionButton: View {
    @Environment(\.trainerActionWidth) private var inheritedRowWidth
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let title: String
    let systemImage: String?
    let enabled: Bool
    let widthRole: TrainerActionWidthRole
    let helpText: String?
    let accessibilityLabel: String?
    let action: () -> Void

    init(
        title: String,
        systemImage: String? = nil,
        enabled: Bool = true,
        widthRole: TrainerActionWidthRole = .automatic,
        helpText: String? = nil,
        accessibilityLabel: String? = nil,
        action: @escaping () -> Void
    ) {
        self.title = title
        self.systemImage = systemImage
        self.enabled = enabled
        self.widthRole = widthRole
        self.helpText = helpText
        self.accessibilityLabel = accessibilityLabel
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            TrainerActionButtonLabel(title: title, fillsWidth: widthRole != .sheet && (widthRole != .automatic || inheritedRowWidth != nil))
        }
        .buttonStyle(.bordered)
        .disabled(!enabled)
        .transaction { transaction in
            TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
        }
        .help(helpText ?? "")
        .accessibilityLabel(accessibilityLabel ?? title)
        .modifier(TrainerActionWidthModifier(role: widthRole))
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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
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
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(selected ? theme.accent : .secondary)
                .frame(width: 12, height: 16)
                .contentShape(Rectangle())
                .contentTransition(.opacity)
                .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)
        }
        .buttonStyle(.bordered)
        .controlSize(.mini)
        .frame(width: 24, height: 24)
        .disabled(!enabled)
        .transaction { transaction in
            TrainerMotion.nativeControlTransaction(&transaction, reduceMotion: reduceMotion)
        }
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
        .accessibilityLabel(localization.localized("host.more"))
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
        content
            .clipShape(RoundedRectangle(cornerRadius: theme.panelCornerRadius, style: .continuous))
            .trainerSurface(.panel, cornerRadius: theme.panelCornerRadius)
    }
}

extension View {
    func trainerGroupedRows() -> some View {
        modifier(TrainerGroupedRowsModifier())
    }
}
