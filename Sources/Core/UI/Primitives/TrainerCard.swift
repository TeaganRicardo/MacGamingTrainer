import SwiftUI

struct TrainerMetricCard<Content: View, Accessory: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let tint: Color
    let content: Content
    let accessory: Accessory

    init(
        title: String,
        icon: String,
        tint: Color,
        @ViewBuilder accessory: () -> Accessory,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.accessory = accessory()
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                Label(title, systemImage: icon)
                    .font(.caption)
                    .foregroundStyle(tint.opacity(0.9))
                Spacer()
                accessory
            }
            content
                .frame(maxWidth: .infinity, alignment: .center)
        }
        // Let the header/value pair determine the card height.  A previous
        // minHeight centered the padded stack inside extra vertical space,
        // which showed up as a conspicuous empty strip above the title row.
        .padding(.horizontal, 14)
        .padding(.top, 6)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.panel, in: RoundedRectangle(cornerRadius: theme.cardCornerRadius))
    }
}

extension TrainerMetricCard where Accessory == EmptyView {
    init(title: String, icon: String, tint: Color, @ViewBuilder content: () -> Content) {
        self.init(title: title, icon: icon, tint: tint, accessory: { EmptyView() }, content: content)
    }
}
