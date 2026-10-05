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
            VStack(spacing: 0) {
                ScrollView {
                    content
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(theme.pagePadding)
                }
                // An optional module slot remains outside the scroll viewport.
                // Its stable height keeps a notice from covering an editor or
                // changing the content position when it appears or fades.
                feedback
            }
        }
        .background(theme.background.ignoresSafeArea())
    }
}

extension TrainerShell where Feedback == EmptyView {
    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content) {
        self.init(sidebar: sidebar, content: content, feedback: { EmptyView() })
    }
}
