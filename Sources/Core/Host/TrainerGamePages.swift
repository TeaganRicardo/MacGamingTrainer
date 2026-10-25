import AppKit
import SwiftUI

struct TrainerGamePages: View {
    @ObservedObject var application: TrainerApplicationCoordinator
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        VStack(spacing: 0) {
            if application.contexts.count > 1 {
                HStack {
                    Picker(localization.localized("host.gameLibrary"), selection: $application.selectedGameID) {
                        ForEach(application.contexts) { context in
                            Text(context.descriptor.displayName).tag(context.id)
                        }
                    }
                    .frame(width: 300)
                    Spacer()
                    ForEach(application.contexts) { context in
                        Label(context.descriptor.displayName,
                              systemImage: context.connected ? "link" : "circle")
                            .foregroundStyle(context.connected ? Color.accentColor : Color.secondary)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                Divider()
            }
            ZStack(alignment: .topLeading) {
                ForEach(application.contexts) { context in
                    context.content
                        .opacity(context.id == application.selectedGameID ? 1 : 0)
                        .allowsHitTesting(context.id == application.selectedGameID)
                        .accessibilityHidden(context.id != application.selectedGameID)
                        .zIndex(context.id == application.selectedGameID ? 1 : 0)
                }
            }
        }
        .onChange(of: application.selectedGameID) { _, _ in
            NSApp.mainWindow?.makeFirstResponder(nil)
        }
    }
}

