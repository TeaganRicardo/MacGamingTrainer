import SwiftUI

struct TrainerSectionHeading: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.title3.weight(.semibold))
            .foregroundStyle(.primary)
    }
}

struct TrainerPageHeader<Trailing: View>: View {
    let title: String
    let trailing: Trailing

    init(title: String, @ViewBuilder trailing: () -> Trailing) {
        self.title = title
        self.trailing = trailing()
    }

    var body: some View {
        HStack(alignment: .top) {
            Text(title)
                .font(.system(size: 34, weight: .bold, design: .rounded))
                .tracking(2)
            Spacer()
            trailing
        }
    }
}

/// Shared vertical section rhythm for every game module. Game-specific views
/// provide only their controls; heading typography and spacing stay global.
struct TrainerSectionHeader<Accessory: View>: View {
    let title: String
    let icon: String
    let accessory: Accessory

    init(title: String, icon: String, @ViewBuilder accessory: () -> Accessory) {
        self.title = title
        self.icon = icon
        self.accessory = accessory()
    }

    var body: some View {
        HStack {
            TrainerSectionHeading(title: title, icon: icon)
            Spacer()
            accessory
        }
    }
}

struct TrainerSection<Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let content: Content

    init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            TrainerSectionHeading(title: title, icon: icon)
            content
        }
    }
}
