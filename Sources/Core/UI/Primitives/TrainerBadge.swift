import SwiftUI

struct TrainerShortcutBadge: View {
    @Environment(\.trainerTheme) private var theme
    let text: String

    var body: some View {
        Text(text)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 7)
            .padding(.vertical, 6)
            .background(theme.subtleFill, in: RoundedRectangle(cornerRadius: 6))
    }
}

/// Shared shortcut badge slot. Rows with a shortcut keep a stable minimum
/// badge width; rows without one collapse completely so no phantom gap remains
/// between numeric editors and their toggle/apply control.
struct TrainerShortcutBadgeSlot: View {
    let text: String?

    var body: some View {
        if let text, !text.isEmpty {
            TrainerShortcutBadge(text: text)
                .frame(minWidth: 52, alignment: .center)
        }
    }
}
