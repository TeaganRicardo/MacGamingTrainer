import SwiftUI

struct TrainerMessageBanner: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let text: String
    let icon: String
    let color: Color

    var body: some View {
        Label(localization.presentation(text), systemImage: icon)
            .font(.callout)
            .foregroundStyle(color)
            .textSelection(.enabled)
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: theme.controlCornerRadius))
    }
}
