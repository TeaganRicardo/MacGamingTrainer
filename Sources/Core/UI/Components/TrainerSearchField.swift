import SwiftUI

/// One shared search-field treatment for feature panels and larger workbenches.
struct TrainerSearchField: View {
    @Environment(\.trainerTheme) private var theme
    @Binding var text: String
    let placeholder: String
    let clearLabel: String?
    let onSubmit: () -> Void

    init(
        text: Binding<String>,
        placeholder: String,
        clearLabel: String? = nil,
        onSubmit: @escaping () -> Void = {}
    ) {
        self._text = text
        self.placeholder = placeholder
        self.clearLabel = clearLabel
        self.onSubmit = onSubmit
    }

    var body: some View {
        HStack(spacing: theme.compactControlSpacing) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            TextField(placeholder, text: $text)
                .textFieldStyle(.plain)
                .onSubmit(onSubmit)
                .accessibilityLabel(placeholder)
            if !text.isEmpty, let clearLabel {
                Button {
                    text = ""
                    onSubmit()
                } label: {
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
    }
}
