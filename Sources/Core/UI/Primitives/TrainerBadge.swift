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

/// Fixed shortcut column shared by normal and multiplier feature rows. This
/// keeps badge styling and the badge-to-switch spacing identical even when the
/// multiplier row inserts a numeric editor to the left.
struct TrainerShortcutBadgeSlot: View {
    let text: String?

    var body: some View {
        if let text, !text.isEmpty {
            TrainerShortcutBadge(text: text)
                .frame(minWidth: 52, alignment: .center)
        }
    }
}
