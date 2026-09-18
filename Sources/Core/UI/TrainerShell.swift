import SwiftUI

struct TrainerShell<Sidebar: View, Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    private let sidebar: Sidebar
    private let content: Content

    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content) {
        self.sidebar = sidebar()
        self.content = content()
    }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider().overlay(theme.separator)
            ScrollView {
                content
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(theme.pagePadding)
            }
        }
        .background(theme.background.ignoresSafeArea())
    }
}
