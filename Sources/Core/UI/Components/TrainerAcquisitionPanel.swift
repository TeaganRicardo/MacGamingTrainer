import SwiftUI

/// Shared visual structure for searchable catalog selection panels.
/// The Host owns chrome, spacing and the search field; each game supplies
/// its selectable targets and validated settings controls.
package struct TrainerAcquisitionPanel<Settings: View, Rows: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var search: String
    let searchPlaceholder: String
    let clearLabel: String
    let settings: Settings
    let rows: Rows

    package init(
        title: String,
        icon: String,
        search: Binding<String>,
        searchPlaceholder: String,
        clearLabel: String,
        @ViewBuilder settings: () -> Settings,
        @ViewBuilder rows: () -> Rows
    ) {
        self.title = title
        self.icon = icon
        _search = search
        self.searchPlaceholder = searchPlaceholder
        self.clearLabel = clearLabel
        self.settings = settings()
        self.rows = rows()
    }

    package var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            HStack(spacing: 10) {
                TrainerIconLabel(
                    title: title,
                    icon: icon,
                    tint: theme.accent,
                    emphasized: true
                )
                .fixedSize(horizontal: true, vertical: false)
                Spacer(minLength: 0)
                settings
                TrainerSearchField(
                    text: $search,
                    placeholder: searchPlaceholder,
                    clearLabel: clearLabel
                )
                .frame(minWidth: 128, maxWidth: 280)
            }
            rows
        }
        .trainerPanel()
    }
}
