import SwiftUI

struct TrainerSectionHeading: View {
    let title: String
    let icon: String

    var body: some View {
        Label(title, systemImage: icon)
            .font(.headline)
            .foregroundStyle(.primary)
            .fixedSize(horizontal: false, vertical: true)
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
                .font(.largeTitle.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
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

package struct TrainerSection<Accessory: View, Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let accessory: Accessory
    let content: Content

    package init(
        title: String,
        icon: String,
        @ViewBuilder accessory: () -> Accessory,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.icon = icon
        self.accessory = accessory()
        self.content = content()
    }

    package var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            TrainerSectionHeader(title: title, icon: icon) {
                accessory
            }
            content
        }
    }
}

extension TrainerSection where Accessory == EmptyView {
    package init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.init(title: title, icon: icon, accessory: { EmptyView() }, content: content)
    }
}
