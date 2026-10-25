import AppKit
import SwiftUI

struct TrainerGamePages: View {
    @ObservedObject var application: TrainerApplicationCoordinator

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(application.contexts) { context in
                context.content
                    .opacity(context.id == application.selectedGameID ? 1 : 0)
                    .allowsHitTesting(context.id == application.selectedGameID)
                    .accessibilityHidden(context.id != application.selectedGameID)
                    .zIndex(context.id == application.selectedGameID ? 1 : 0)
            }
        }
        .environment(\.trainerGameLibrary, AnyView(TrainerGameLibrary(application: application)))
        .disabled(application.terminationRequested)
        .onChange(of: application.selectedGameID) { _, _ in
            NSApp.mainWindow?.makeFirstResponder(nil)
        }
    }
}

private struct TrainerGameLibrary: View {
    @ObservedObject var application: TrainerApplicationCoordinator
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        if application.contexts.count > 1 {
            VStack(alignment: .leading, spacing: 6) {
                Text(localization.localized("host.gameLibrary"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 10)
                ForEach(application.contexts) { context in
                    Button {
                        application.selectedGameID = context.id
                    } label: {
                        HStack(spacing: 10) {
                            Circle()
                                .fill(context.connected ? theme.success : theme.inactive)
                                .frame(width: 6, height: 6)
                            Text(context.descriptor.displayName)
                            Spacer()
                            if application.selectedGameID == context.id {
                                Image(systemName: "checkmark").foregroundStyle(theme.accent)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(application.selectedGameID == context.id ? theme.mutedFill : .clear,
                                    in: RoundedRectangle(cornerRadius: theme.compactCornerRadius))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("host.game.\(context.id)")
                    .accessibilityAddTraits(application.selectedGameID == context.id ? .isSelected : [])
                }
            }
        }
    }
}
