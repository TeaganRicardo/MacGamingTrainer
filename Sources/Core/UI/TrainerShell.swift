import SwiftUI

private struct TrainerSectionNavigationKey: EnvironmentKey {
    static let defaultValue: (String) -> Void = { _ in }
}

private struct TrainerSelectedSectionKey: EnvironmentKey {
    static let defaultValue: String? = nil
}

extension EnvironmentValues {
    var trainerNavigateToSection: (String) -> Void {
        get { self[TrainerSectionNavigationKey.self] }
        set { self[TrainerSectionNavigationKey.self] = newValue }
    }

    var trainerSelectedSection: String? {
        get { self[TrainerSelectedSectionKey.self] }
        set { self[TrainerSelectedSectionKey.self] = newValue }
    }
}

struct TrainerShell<Sidebar: View, Content: View, Feedback: View>: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    @StateObject private var navigation = TrainerSectionNavigation()
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
            Rectangle()
                .fill(theme.boundaryColor(for: contrast))
                .frame(width: 1)
                .accessibilityHidden(true)
            TrainerWorkbenchViewport(navigation: navigation) {
                content
            } feedback: {
                feedback
            }
        }
        .environment(\.trainerNavigateToSection, navigation.navigate)
        .environment(\.trainerSelectedSection, navigation.selection)
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
    }
}

/// Each retained page keeps its own scroll viewport. The shared sidebar sends
/// requests to this owner instead of storing a proxy from a disappearing page.
struct TrainerWorkbenchViewport<Content: View, Feedback: View>: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerGamePageVisible) private var pageVisible
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @StateObject private var sectionScroll = TrainerSectionScroll()
    @ObservedObject var navigation: TrainerSectionNavigation
    let content: Content
    let feedback: Feedback

    init(navigation: TrainerSectionNavigation, @ViewBuilder content: () -> Content,
         @ViewBuilder feedback: () -> Feedback) {
        self.navigation = navigation
        self.content = content()
        self.feedback = feedback()
    }

    var body: some View {
        ScrollView {
            content
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(theme.pagePadding)
                .background(TrainerSectionViewportProbe().allowsHitTesting(false).accessibilityHidden(true))
        }
        .overlay(alignment: .bottom) { feedback.padding(16) }
        .task(id: navigation.request) {
            guard let request = navigation.request else { return }
            // Newly revealed targets register after their native layout exists.
            // Keep only the current request across that presentation update.
            await Task.yield()
            guard !Task.isCancelled, pageVisible else { return }
            sectionScroll.scroll(request, navigation: navigation)
        }
        .onChange(of: pageVisible) { _, visible in
            navigation.setVisible(visible)
            if !visible { sectionScroll.cancel() }
        }
        .onChange(of: reduceMotion, initial: true) { _, reduced in sectionScroll.setReduceMotion(reduced) }
        .onDisappear { sectionScroll.cancel() }
        .environment(\.trainerSectionScroll, sectionScroll)
        .environment(\.trainerNavigateToSection, navigation.navigate)
        .environment(\.trainerSelectedSection, navigation.selection)
    }
}

extension TrainerShell where Feedback == EmptyView {
    init(@ViewBuilder sidebar: () -> Sidebar, @ViewBuilder content: () -> Content) {
        self.init(sidebar: sidebar, content: content, feedback: { EmptyView() })
    }
}
