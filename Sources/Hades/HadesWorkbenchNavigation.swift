import SwiftUI

/// The visible workbench follows the same order as Hades II. Rooms stays
/// reserved for the native room/reward implementation (#572); no empty panel
/// or nonfunctional navigation destination is exposed before that delivery.
enum HadesWorkbenchSection: String, CaseIterable, Identifiable {
    case values, common, boons, resources, rooms, management

    var id: String { "hades-workbench-\(rawValue)" }
    var titleKey: String {
        switch self {
        case .values: "hades.section.runData"
        case .common: "hades.section.common"
        case .boons: "hades.section.boonsAndEffects"
        case .resources: "hades.section.resourcesAndGathering"
        case .rooms: "hades.section.roomsAndRewards"
        case .management: "hades.management"
        }
    }
    var icon: String {
        switch self {
        case .values: "gauge.with.dots.needle.67percent"
        case .common: "bolt.fill"
        case .boons: "sparkles"
        case .resources: "shippingbox.fill"
        case .rooms: "door.left.hand.open"
        case .management: "gearshape.2.fill"
        }
    }

    static var visible: [Self] { allCases.filter { $0 != .rooms } }
}

struct HadesWorkbenchEntry: Identifiable {
    let id: String
    let titleKey: String
    let section: HadesWorkbenchSection
    var resource: HadesResourceDefinition? = nil

    var requiresExpandedMetrics: Bool { id.hasPrefix("numeric.") }
}

enum HadesWorkbenchCatalog {
    /// Single visible-order owner for shortcut defaults and the settings list.
    static let orderedShortcutActions: [HadesShortcutAction] = [
        .heal,
        .invincibility,
        .moneyNoDecrease,
        .rerollsNoDecrease,
        .fullGodGauge,
        .disableAll,
    ]

    static func shortcutActions(in section: HadesWorkbenchSection) -> [HadesShortcutAction] {
        orderedShortcutActions.filter { action in
            switch action {
            case .heal: section == .values
            case .disableAll: section == .management
            default: section == .common
            }
        }
    }

    static let entries: [HadesWorkbenchEntry] = {
        let actions = orderedShortcutActions.map { action in
            HadesWorkbenchEntry(
                id: "shortcut.\(action.rawValue)",
                titleKey: action.key,
                section: action == .heal ? .values : (action == .disableAll ? .management : .common)
            )
        }
        let other: [(HadesWorkbenchSection, [String])] = [
            (.values, ["hades.health", "hades.maxHealth", "hades.money", "hades.rerolls",
                       "hades.godGauge"]),
            (.boons, ["hades.currentTraits", "hades.catalog", "hades.rarity",
                      "hades.level", "hades.apply", "hades.remove"]),
            (.resources, ["hades.resources"]),
            (.management, ["host.refreshStatus", "host.saveManagement", "host.shortcutSettings"]),
        ]
        let fixed = other.flatMap { section, keys in
            keys.map { HadesWorkbenchEntry(id: $0, titleKey: $0, section: section) }
        }
        let numbers = HadesFeature.allCases.filter { !$0.isToggle }.map {
            HadesWorkbenchEntry(id: "numeric.\($0.rawValue)", titleKey: $0.key, section: .values)
        }
        return actions + fixed + numbers
    }()

    static func matches(
        _ query: String,
        resources: [HadesResourceDefinition],
        resolving labels: (String) -> [String]
    ) -> [HadesWorkbenchEntry] {
        let words = query.split(whereSeparator: \.isWhitespace).map { normalized(String($0)) }
        guard !words.isEmpty else { return [] }
        let dynamic = resources.map {
            HadesWorkbenchEntry(id: "resource.\($0.id)", titleKey: "hades.resources",
                                section: .resources, resource: $0)
        }
        return (entries + dynamic).filter { entry in
            let names = labels(entry.titleKey) + labels(entry.section.titleKey)
                + (entry.resource.map { Array($0.names.values) + [$0.id] } ?? [])
            let searchable = normalized(names.joined(separator: " "))
            return words.allSatisfy { searchable.contains($0) }
        }
    }

    private static func normalized(_ value: String) -> String {
        value.folding(options: [.caseInsensitive, .diacriticInsensitive],
                      locale: Locale(identifier: "en_US_POSIX"))
    }
}

struct HadesSidebarActions: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Divider().padding(.vertical, 2)
            ForEach(HadesWorkbenchSection.visible) { section in
                if section == .management { Divider().padding(.vertical, 2) }
                TrainerSectionButton(
                    title: HadesPresentation.text(section.titleKey, language: localization.language),
                    systemImage: section.icon
                ) {
                    navigate(section.id)
                }
                .focusEffectDisabled()
            }
        }
    }
}

struct HadesHeaderActions: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    @Environment(\.trainerGamePageVisible) private var pageVisible
    @State private var resultsPresented = false

    private var results: [HadesWorkbenchEntry] {
        HadesWorkbenchCatalog.matches(model.workbenchSearch, resources: model.resourceCatalog) { key in
            TrainerPresentationLanguage.allCases.map {
                HadesPresentation.text(key, language: $0)
            }
        }
    }

    private func label(_ entry: HadesWorkbenchEntry) -> String {
        if let resource = entry.resource {
            return resource.name(language: localization.language.rawValue)
        }
        return HadesPresentation.text(entry.titleKey, language: localization.language)
    }

    private func locate(_ entry: HadesWorkbenchEntry) {
        if entry.requiresExpandedMetrics { model.numericControlsExpanded = true }
        navigate(entry.section.id)
        resultsPresented = false
    }

    var body: some View {
        TrainerSearchField(
            text: $model.workbenchSearch,
            placeholder: HadesPresentation.text("hades.workbench.search", language: localization.language),
            clearLabel: localization.localized("host.search.clear")
        ) {
            if let first = results.first { locate(first) }
            else { resultsPresented = false }
        }
        .popover(isPresented: $resultsPresented, arrowEdge: .bottom) {
            Group {
                if results.isEmpty {
                    TrainerEmptyState(text: HadesPresentation.text("hades.workbench.searchEmpty",
                                                                  language: localization.language))
                } else {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(results) { entry in
                                TrainerSectionButton(
                                    title: label(entry),
                                    detail: HadesPresentation.text(entry.section.titleKey,
                                                                   language: localization.language),
                                    systemImage: entry.section.icon
                                ) {
                                    locate(entry)
                                }
                            }
                        }
                    }
                    .frame(height: min(CGFloat(results.count) * 52, 312))
                }
            }
            .frame(width: 420)
            .padding(8)
        }
        .onChange(of: model.workbenchSearch) { _, query in
            guard pageVisible else { return }
            resultsPresented = !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        .onChange(of: pageVisible) { _, visible in
            if !visible { resultsPresented = false }
        }
    }
}
