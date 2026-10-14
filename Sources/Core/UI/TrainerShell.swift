import SwiftUI

struct TrainerShell<Sidebar: View, Content: View, Feedback: View>: View {
    @Environment(\.trainerTheme) private var theme
    private let sidebar: Sidebar
    private let content: Content
    private let feedback: Feedback

    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content,
         @ViewBuilder feedback: () -> Feedback) {
        self.sidebar = sidebar()
        self.content = content()
        self.feedback = feedback()
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
            .overlay(alignment: .bottom) {
                feedback.padding(16)
            }
        }
        .background(theme.background.ignoresSafeArea())
        .trainerDismissTextEditingOnClickAway()
    }
}

extension TrainerShell where Feedback == EmptyView {
    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content) {
        self.init(sidebar: sidebar, content: content, feedback: { EmptyView() })
    }
}
