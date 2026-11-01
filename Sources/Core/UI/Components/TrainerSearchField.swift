import SwiftUI

/// One shared search-field treatment for feature panels and larger workbenches.
struct TrainerSearchField: View {
    @Environment(\.trainerTheme) private var theme
    @Binding var text: String
    let placeholder: String
    let clearLabel: String?
    let focus: FocusState<Bool>.Binding?
    let onSubmit: () -> Void

    init(
        text: Binding<String>,
        placeholder: String,
        clearLabel: String? = nil,
        focus: FocusState<Bool>.Binding? = nil,
        onSubmit: @escaping () -> Void = {}
    ) {
        self._text = text
        self.placeholder = placeholder
        self.clearLabel = clearLabel
        self.focus = focus
        self.onSubmit = onSubmit
    }

    var showsClearAction: Bool { !text.isEmpty && clearLabel != nil }

    func clearSearch() {
        text = ""
        onSubmit()
    }

    private var textField: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.plain)
            .onSubmit(onSubmit)
            .accessibilityLabel(placeholder)
    }

    @ViewBuilder private var searchInput: some View {
        if let focus { textField.focused(focus) }
        else { textField }
    }

    var body: some View {
        HStack(spacing: theme.compactControlSpacing) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            searchInput
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
    }
}
