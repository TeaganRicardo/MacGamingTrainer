import SwiftUI

/// A live permission check belongs to the action itself, so a menu/button
/// captured before a busy or shutdown transition cannot rely on stale state.
package struct TrainerManagementAction: Identifiable {
    package enum Common: String {
        case refreshStatus, disableAll, shortcuts, log, logHistory, clearLogs, saveManagement

        var titleKey: String {
            switch self {
            case .refreshStatus: "host.refreshStatus"
            case .disableAll: "host.disableAll"
            case .shortcuts: "host.shortcutSettings"
            case .log: "host.viewLog"
            case .logHistory: "host.viewLogHistory"
            case .clearLogs: "host.clearCompletedLogs"
            case .saveManagement: "host.saveManagement"
            }
        }

        var icon: String {
            switch self {
            case .refreshStatus: TrainerSemanticIcon.Tool.refreshStatus
            case .disableAll: TrainerSemanticIcon.Tool.disableAll
            case .shortcuts: TrainerSemanticIcon.Tool.shortcuts
            case .log: TrainerSemanticIcon.Tool.log
            case .logHistory: TrainerSemanticIcon.Tool.logHistory
            case .clearLogs: TrainerSemanticIcon.Tool.clearLogs
            case .saveManagement: TrainerSemanticIcon.Tool.saveManagement
            }
        }
    }

    package let id: String
    let title: String
    let icon: String
    private let availability: () -> Bool
    private let handler: () -> Void

    package init(id: String, title: String, icon: String,
         enabled: @escaping () -> Bool = { true }, action: @escaping () -> Void) {
        self.id = id
        self.title = title
        self.icon = icon
        availability = enabled
        handler = action
    }

    @MainActor
    package init(_ common: Common, localization: TrainerLocalizationStore,
         enabled: @escaping () -> Bool = { true }, action: @escaping () -> Void) {
        self.init(id: common.rawValue, title: localization.localized(common.titleKey),
                  icon: common.icon, enabled: enabled, action: action)
    }

    var isEnabled: Bool { availability() }

    func perform() {
        guard isEnabled else { return }
        handler()
    }
}

package struct TrainerManagementGroup: Identifiable {
    struct Row {
        let actions: [TrainerManagementAction]
        var note: String? = nil
    }

    package let id: String
    let title: String
    let rows: [Row]
    var actions: [TrainerManagementAction] { rows.flatMap(\.actions) }
}

/// One common grouping for the page and app menu. Optional document actions
/// are supplied only where the owning Host/tool-window capability is available.
package struct TrainerManagementCatalog {
    package struct Titles {
        let daily: String
        let settings: String
        let maintenance: String

        package init(daily: String, settings: String, maintenance: String) {
            self.daily = daily
            self.settings = settings
            self.maintenance = maintenance
        }
    }

    let titles: Titles
    let refresh: TrainerManagementAction
    let disableAll: TrainerManagementAction
    let profiles: TrainerManagementAction
    let shortcuts: TrainerManagementAction
    let log: TrainerManagementAction
    let diagnostics: TrainerManagementAction
    let logHistory: TrainerManagementAction
    let clearLogs: TrainerManagementAction
    var saveEditor: TrainerManagementAction? = nil
    var saveManagement: TrainerManagementAction? = nil
    var additionalMaintenance: [TrainerManagementAction] = []
    var maintenanceNote: String? = nil

    package init(titles: TrainerManagementCatalog.Titles, refresh: TrainerManagementAction, disableAll: TrainerManagementAction, profiles: TrainerManagementAction, shortcuts: TrainerManagementAction, log: TrainerManagementAction, diagnostics: TrainerManagementAction, logHistory: TrainerManagementAction, clearLogs: TrainerManagementAction, saveEditor: TrainerManagementAction? = nil, saveManagement: TrainerManagementAction? = nil, additionalMaintenance: [TrainerManagementAction] = [], maintenanceNote: String? = nil) {
        self.titles = titles
        self.refresh = refresh
        self.disableAll = disableAll
        self.profiles = profiles
        self.shortcuts = shortcuts
        self.log = log
        self.diagnostics = diagnostics
        self.logHistory = logHistory
        self.clearLogs = clearLogs
        self.saveEditor = saveEditor
        self.saveManagement = saveManagement
        self.additionalMaintenance = additionalMaintenance
        self.maintenanceNote = maintenanceNote
    }

    package var groups: [TrainerManagementGroup] {
        var maintenance: [TrainerManagementGroup.Row] = [
            .init(actions: [log, diagnostics]), .init(actions: [logHistory, clearLogs]),
        ]
        if !additionalMaintenance.isEmpty {
            maintenance.append(.init(actions: additionalMaintenance, note: maintenanceNote))
        }
        return [
            .init(id: "daily", title: titles.daily,
                  rows: [.init(actions: [refresh] + [saveEditor, saveManagement].compactMap { $0 } + [disableAll])]),
            .init(id: "settings", title: titles.settings, rows: [.init(actions: [profiles, shortcuts])]),
            .init(id: "maintenance", title: titles.maintenance, rows: maintenance),
        ]
    }
}

package struct TrainerManagementGroups: View {
    @Environment(\.trainerTheme) private var theme
    let groups: [TrainerManagementGroup]

    package init(groups: [TrainerManagementGroup]) {
        self.groups = groups
    }

    private func buttons(_ actions: [TrainerManagementAction]) -> some View {
        ForEach(actions) { action in
            TrainerSecondaryActionButton(title: action.title,
                                         enabled: action.isEnabled, action: action.perform)
                .accessibilityIdentifier("trainer.management.\(action.id)")
        }
    }

    package var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            ForEach(groups.indices, id: \.self) { index in
                if index > 0 { Divider() }
                let group = groups[index]
                VStack(alignment: .leading, spacing: theme.controlPadding) {
                    Text(group.title).font(.subheadline.weight(.semibold)).accessibilityAddTraits(.isHeader)
                    ForEach(group.rows.indices, id: \.self) { rowIndex in
                        let row = group.rows[rowIndex]
                        if let note = row.note {
                            Text(note).font(.caption).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        ViewThatFits(in: .horizontal) {
                            HStack(spacing: theme.controlPadding) { buttons(row.actions) }
                            VStack(alignment: .leading, spacing: theme.controlPadding) { buttons(row.actions) }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

package struct TrainerManagementCommandMenu: Commands {
    let title: String
    let groups: [TrainerManagementGroup]

    package init(title: String, groups: [TrainerManagementGroup]) {
        self.title = title
        self.groups = groups
    }

    package var body: some Commands {
        CommandMenu(title) {
            ForEach(groups.indices, id: \.self) { index in
                if index > 0 { Divider() }
                ForEach(groups[index].actions) { action in
                    Button(action: action.perform) {
                        Label(action.title, systemImage: action.icon)
                    }
                    .disabled(!action.isEnabled)
                }
            }
        }
    }
}
