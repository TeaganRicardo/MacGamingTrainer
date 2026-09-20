import SwiftUI

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
