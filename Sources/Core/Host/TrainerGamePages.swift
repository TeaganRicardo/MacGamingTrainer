import AppKit
import SwiftUI

private struct TrainerGamePageVisibilityKey: EnvironmentKey {
    static let defaultValue = true
}

extension EnvironmentValues {
    var trainerGamePageVisible: Bool {
        get { self[TrainerGamePageVisibilityKey.self] }
        set { self[TrainerGamePageVisibilityKey.self] = newValue }
    }
}

struct TrainerGamePages: View {
    @ObservedObject var application: TrainerApplicationCoordinator

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(application.contexts) { context in
                context.content
                    .environment(\.trainerSidebarAdditionalCards, additionalCards(for: context))
                    .environment(\.trainerGamePageVisible, context.id == application.selectedGameID)
                    .opacity(context.id == application.selectedGameID ? 1 : 0)
                    .allowsHitTesting(context.id == application.selectedGameID)
                    .accessibilityHidden(context.id != application.selectedGameID)
                    .zIndex(context.id == application.selectedGameID ? 1 : 0)
            }
        }
        .disabled(application.terminationRequested)
        .onChange(of: application.selectedGameID) { _, _ in
            NSApp.mainWindow?.makeFirstResponder(nil)
        }
    }

    private func additionalCards(for context: AnyTrainerGameContext) -> TrainerSidebarAdditionalCards {
        let before = application.contexts.prefix { $0.id != context.id }
        let after = application.contexts.drop { $0.id != context.id }.dropFirst()
        return TrainerSidebarAdditionalCards(
            before: AnyView(collapsedCards(before)), after: AnyView(collapsedCards(after))
        )
    }

    @ViewBuilder private func collapsedCards(_ contexts: ArraySlice<AnyTrainerGameContext>) -> some View {
        if !contexts.isEmpty {
            VStack(spacing: 12) {
                ForEach(Array(contexts)) { context in
                    context.makeCollapsedSidebarCard { application.selectedGameID = context.id }
                }
            }
        }
    }
}
