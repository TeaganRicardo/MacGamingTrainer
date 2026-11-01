import SwiftUI

private struct TrainerSectionNavigationKey: EnvironmentKey {
    static let defaultValue: (String) -> Void = { _ in }
}

extension EnvironmentValues {
    var trainerNavigateToSection: (String) -> Void {
        get { self[TrainerSectionNavigationKey.self] }
        set { self[TrainerSectionNavigationKey.self] = newValue }
    }
}

struct TrainerShell<Sidebar: View, Content: View, Feedback: View>: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
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
        ScrollViewReader { proxy in
            HStack(spacing: 0) {
                sidebar
                Rectangle()
                    .fill(theme.boundaryColor(for: contrast))
                    .frame(width: 1)
                    .accessibilityHidden(true)
                ScrollView {
                    content
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(theme.pagePadding)
                }
                .overlay(alignment: .bottom) {
                    feedback.padding(16)
                }
            }
            .environment(\.trainerNavigateToSection) { destination in
                withAnimation(.easeInOut(duration: 0.18)) { proxy.scrollTo(destination, anchor: .top) }
            }
        }
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
    }
}

extension TrainerShell where Feedback == EmptyView {
    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content) {
        self.init(sidebar: sidebar, content: content, feedback: { EmptyView() })
    }
}
