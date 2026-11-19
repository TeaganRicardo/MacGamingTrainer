import SwiftUI

package struct TrainerShortcutBadge: View {
    @Environment(\.trainerTheme) private var theme
    let text: String

    package init(text: String) {
        self.text = text
    }

    package var body: some View {
        Text(text)
            .font(.system(.caption, design: .monospaced))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 7)
            .padding(.vertical, 6)
            .frame(minWidth: theme.shortcutBadgeMinimumWidth, alignment: .center)
            .background(theme.subtleFill, in: RoundedRectangle(cornerRadius: theme.compactCornerRadius))
    }
}

/// Shared shortcut badge slot. Rows with a shortcut keep a stable minimum
/// badge width; rows without one collapse completely so no phantom gap remains
/// between numeric editors and their toggle/apply control.
package struct TrainerShortcutBadgeSlot: View {
    let text: String?

    package init(text: String?) {
        self.text = text
    }

    package var body: some View {
        if let text, !text.isEmpty {
            TrainerShortcutBadge(text: text)
        }
    }
}
