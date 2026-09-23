import SwiftUI

struct TrainerSidebar<Actions: View>: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let descriptor: GameModuleDescriptor
    let presentation: TrainerGamePresentation
    let connected: Bool
    let actions: Actions

    init(descriptor: GameModuleDescriptor, presentation: TrainerGamePresentation, connected: Bool, @ViewBuilder actions: () -> Actions) {
        self.descriptor = descriptor
        self.presentation = presentation
        self.connected = connected
        self.actions = actions()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            HStack(spacing: 10) {
                Image(systemName: "gamecontroller.fill")
                    .font(.title2)
                    .foregroundStyle(theme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text("MAC GAMING").font(.system(size: 11, weight: .bold, design: .rounded)).tracking(1.5)
                    Text("Trainer").font(.title3.weight(.bold))
                }
            }
            .padding(.top, 14)

            VStack(alignment: .leading, spacing: 12) {
                Text(localization.language == .en ? "Game Library" : "游戏库")
                    .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                HStack(spacing: 12) {
                    Image(systemName: presentation.sidebarIconSystemName).font(.title2).foregroundStyle(theme.accent)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(descriptor.displayName).font(.headline)
                        if !presentation.platformLabel.isEmpty { Text(presentation.platformLabel).font(.caption2).foregroundStyle(.secondary) }
                    }
                    Spacer()
                    Circle().fill(connected ? theme.success : theme.inactive).frame(width: 6, height: 6)
                }
                .padding(14)
                .background(theme.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: theme.cardCornerRadius))
            }

            Spacer()
            actions.buttonStyle(.plain)
        }
        .padding(22)
        .frame(width: 218)
        .background(theme.sidebarBackground)
    }
}
