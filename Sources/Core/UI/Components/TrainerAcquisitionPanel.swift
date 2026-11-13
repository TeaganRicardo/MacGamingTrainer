import SwiftUI

/// Shared visual structure for game-owned exact acquisition controls.
/// The Host owns chrome, spacing and the search field; each game supplies
/// its native target choices and validated acquisition settings.
struct TrainerAcquisitionPanel<Settings: View, Rows: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var search: String
    let searchPlaceholder: String
    let clearLabel: String
    let settings: Settings
    let rows: Rows

    init(
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

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            HStack(spacing: 10) {
                TrainerIconLabel(
                    title: title,
                    icon: icon,
                    tint: theme.accent,
                    emphasized: true
                )
                settings
                Spacer(minLength: 0)
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
