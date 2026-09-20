import SwiftUI

/// Standard modal/sheet chrome shared by game modules. Width is intentionally a
/// content decision; title typography, outer padding and vertical rhythm are not.
struct TrainerSheetScaffold<HeaderActions: View, Content: View, Footer: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String?
    let width: CGFloat
    let headerActions: HeaderActions
    let content: Content
    let footer: Footer

    init(
        title: String,
        icon: String? = nil,
        width: CGFloat,
        @ViewBuilder headerActions: () -> HeaderActions,
        @ViewBuilder content: () -> Content,
        @ViewBuilder footer: () -> Footer
    ) {
        self.title = title
        self.icon = icon
        self.width = width
        self.headerActions = headerActions()
        self.content = content()
        self.footer = footer()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            HStack {
                if let icon {
                    Label(title, systemImage: icon).font(.title2.bold())
                } else {
                    Text(title).font(.title2.bold())
                }
                Spacer()
                headerActions
            }
            content
            footer
        }
        .padding(theme.sheetPadding)
        .frame(width: width)
        .background(theme.background.ignoresSafeArea())
    }
}
