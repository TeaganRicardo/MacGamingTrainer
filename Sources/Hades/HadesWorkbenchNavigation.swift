import SwiftUI

extension HadesFeature {
    var icon: String {
        switch self {
        case .invincibility: TrainerSemanticIcon.Concept.protection
        case .fullHealth: TrainerSemanticIcon.Concept.vitality
        case .infiniteAmmo: TrainerSemanticIcon.Concept.capacity
        case .forceRerolls: TrainerSemanticIcon.Concept.refresh
        case .incomingDamageMultiplier: TrainerSemanticIcon.Concept.defense
        case .moneyNoDecrease: TrainerSemanticIcon.Concept.currency
        case .rerollsNoDecrease: TrainerSemanticIcon.Concept.randomize
        case .fullGodGauge: HadesWorkbenchIcon.godGauge
        case .boonRarityEnabled: TrainerSemanticIcon.Concept.quality
        case .gameSpeed: TrainerSemanticIcon.Concept.timeScale
        case .damageMultiplier: TrainerSemanticIcon.Concept.impact
        case .moveSpeedMultiplier: TrainerSemanticIcon.Concept.movement
        case .attackSpeedMultiplier: TrainerSemanticIcon.Concept.actionSpeed
        case .dashBonus: TrainerSemanticIcon.Concept.dash
        }
    }
}

extension HadesShortcutAction {
    var icon: String {
        switch self {
        case .invincibility: TrainerSemanticIcon.Concept.protection
        case .fullHealth: TrainerSemanticIcon.Concept.vitality
        case .moneyNoDecrease: TrainerSemanticIcon.Concept.currency
        case .rerollsNoDecrease: TrainerSemanticIcon.Concept.randomize
        case .fullGodGauge: HadesWorkbenchIcon.godGauge
        case .infiniteAmmo: TrainerSemanticIcon.Concept.capacity
        case .forceRerolls: TrainerSemanticIcon.Concept.refresh
        case .boonRarityEnabled: TrainerSemanticIcon.Concept.quality
        case .generateFishing: TrainerSemanticIcon.Context.fishing
        case .generateChaosGate: TrainerSemanticIcon.Context.portal
        case .disableAll: TrainerSemanticIcon.Tool.disableAll
        }
    }
}

/// The visible workbench and shortcut registry follow the shared product order.
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
        case .values: TrainerSemanticIcon.Section.metrics
        case .common: TrainerSemanticIcon.Section.general
        case .boons: TrainerSemanticIcon.Section.effects
        case .resources: TrainerSemanticIcon.Section.inventory
        case .rooms: TrainerSemanticIcon.Section.navigation
        case .management: TrainerSemanticIcon.Section.settings
        }
    }

    static var visible: [Self] { allCases }
}

enum HadesWorkbenchIcon {
    static let godGauge = "bolt.heart.fill"
    static let catalog = TrainerSemanticIcon.Concept.precision
    static let level = TrainerSemanticIcon.Concept.level
    static let route = "arrow.triangle.branch"
    static let chamberObject = "shippingbox"
    static let refreshStatus = TrainerSemanticIcon.Tool.refreshStatus

    static func icon(for titleKey: String) -> String? {
        switch titleKey {
        case "hades.health", "hades.maxHealth": return TrainerSemanticIcon.Concept.vitality
        case "hades.money": return TrainerSemanticIcon.Concept.currency
        case "hades.rerolls": return TrainerSemanticIcon.Concept.randomize
        case "hades.godGauge": return godGauge
        case "host.timeWarp.title": return TrainerSemanticIcon.Concept.timeScale
        case "hades.currentTraits": return TrainerSemanticIcon.Concept.controls
        case "hades.catalog", "hades.exactSource": return catalog
        case "hades.rarity": return TrainerSemanticIcon.Concept.quality
        case "hades.level": return level
        case "hades.apply": return TrainerSemanticIcon.Action.apply
        case "hades.remove", "hades.cancelCurse": return TrainerSemanticIcon.Action.remove
        case "hades.chaosPair": return TrainerSemanticIcon.Context.portal
        case "hades.remainingUses", "hades.expireEffect": return TrainerSemanticIcon.Concept.duration
        case "hades.activateBlessing": return TrainerSemanticIcon.Concept.actionSpeed
        case "hades.refreshEffect": return TrainerSemanticIcon.Concept.refresh
        case "hades.resources": return TrainerSemanticIcon.Section.inventory
        case "hades.gainResource": return TrainerSemanticIcon.Action.acquire
        case "hades.spawnReward", "hades.doorReward": return TrainerSemanticIcon.Context.reward
        case "hades.doorRoute", "hades.route.thanatos": return route
        case "hades.restoreDoor": return TrainerSemanticIcon.Action.restore
        case "hades.chamberObject": return chamberObject
        case "host.refreshStatus": return refreshStatus
        case "hades.saveEditor.title": return TrainerSemanticIcon.Tool.saveEditor
        case "host.saveManagement": return TrainerSemanticIcon.Tool.saveManagement
        case "host.shortcutSettings": return TrainerSemanticIcon.Tool.shortcuts
        case "hades.manage.profiles": return TrainerSemanticIcon.Tool.profiles
        case "hades.manage.diagnostics": return TrainerSemanticIcon.Tool.diagnostics
        case "host.viewLog": return TrainerSemanticIcon.Tool.log
        case "host.viewLogHistory": return TrainerSemanticIcon.Tool.logHistory
        case "host.clearCompletedLogs": return TrainerSemanticIcon.Tool.clearLogs
        default: return nil
        }
    }
}

struct HadesWorkbenchEntry: Identifiable {
    let id: String
    let titleKey: String
    let section: HadesWorkbenchSection
    var shortcut: HadesShortcutAction? = nil
    var resource: HadesResourceDefinition? = nil
    var worldNames: [String: String]? = nil

    var requiresExpandedMetrics: Bool { id.hasPrefix("numeric.") }
    var icon: String {
        if let shortcut { return shortcut.icon }
        if resource != nil { return TrainerSemanticIcon.Concept.item }
        if worldNames != nil {
            if id == "world.fishing" { return TrainerSemanticIcon.Context.fishing }
            if id == "world.chaosGate" { return TrainerSemanticIcon.Context.portal }
            return section.icon
        }
        if let feature = HadesFeature.allCases.first(where: { $0.key == titleKey }) {
            return feature.icon
        }
        if let icon = HadesWorkbenchIcon.icon(for: titleKey) { return icon }
        return section.icon
    }

}
enum HadesWorkbenchCatalog {
    /// Single visible-order owner for shortcut defaults and the settings list.
    static let orderedShortcutActions: [HadesShortcutAction] = [
        .invincibility,
        .fullHealth,
        .moneyNoDecrease,
        .rerollsNoDecrease,
        .fullGodGauge,
        .infiniteAmmo,
        .forceRerolls,
        .boonRarityEnabled,
        .generateFishing,
        .generateChaosGate,
        .disableAll,
    ]

    static func shortcutActions(in section: HadesWorkbenchSection) -> [HadesShortcutAction] {
        orderedShortcutActions.filter { action in
            switch action {
            case .boonRarityEnabled: section == .boons
            case .generateFishing: section == .resources
            case .generateChaosGate: section == .rooms
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
                section: action == .disableAll ? .management
                    : (action == .boonRarityEnabled ? .boons
                       : (action == .generateFishing ? .resources
                          : (action == .generateChaosGate ? .rooms : .common))),
                shortcut: action
            )
        }
        let other: [(HadesWorkbenchSection, [String])] = [
            (.values, ["hades.health", "hades.maxHealth", "hades.money", "hades.rerolls",
                       "hades.godGauge"]),
            (.common, ["host.timeWarp.title"]),
            (.boons, ["hades.currentTraits", "hades.catalog", "hades.rarity",
                      "hades.level", "hades.apply", "hades.remove", "hades.chaosPair",
                      "hades.remainingUses", "hades.activateBlessing", "hades.expireEffect", "hades.refreshEffect"]),
            (.resources, ["hades.resources", "hades.gainResource"]),
            (.rooms, ["hades.spawnReward", "hades.doorReward", "hades.doorRoute", "hades.restoreDoor", "hades.route.thanatos", "hades.chamberObject"]),
            (.management, ["host.refreshStatus", "hades.saveEditor.title", "host.saveManagement", "host.shortcutSettings",
                           "hades.manage.profiles", "hades.manage.diagnostics", "host.viewLog",
                           "host.viewLogHistory", "host.clearCompletedLogs"]),
        ]
        let fixed = other.flatMap { section, keys in
            keys.map { HadesWorkbenchEntry(id: $0, titleKey: $0, section: section) }
        }
        let numbers = HadesFeature.allCases.filter { !$0.isToggle && $0 != .gameSpeed }.map {
            HadesWorkbenchEntry(id: "numeric.\($0.rawValue)", titleKey: $0.key, section: .values)
        }
        return actions + fixed + numbers
    }()

    static func matches(
        _ query: String,
        resources: [HadesResourceDefinition],
        worldTerms: [String: [String: String]] = [:],
        resolving labels: (String) -> [String]
    ) -> [HadesWorkbenchEntry] {
        let words = query.split(whereSeparator: \.isWhitespace).map { normalized(String($0)) }
        guard !words.isEmpty else { return [] }
        let dynamic = resources.map {
            HadesWorkbenchEntry(id: "resource.\($0.id)", titleKey: "hades.resources",
                                section: .resources, resource: $0)
        }
        let world = worldTerms.map { key, names in
            HadesWorkbenchEntry(id: "world.\(key)", titleKey: "hades.chamberObject",
                section: key == "fishing" ? .resources : .rooms, worldNames: names)
        }
        return (entries + dynamic + world).filter { entry in
            let names = labels(entry.titleKey) + labels(entry.section.titleKey)
                + (entry.resource.map { Array($0.names.values) + [$0.id] } ?? [])
                + (entry.worldNames.map { Array($0.values) } ?? [])
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
        HadesWorkbenchCatalog.matches(model.workbenchSearch, resources: model.resourceCatalog, worldTerms: model.worldTerms) { key in
            TrainerPresentationLanguage.allCases.map {
                HadesGameModule.resolveText(key: key, language: $0, localization: localization)
            }
        }
    }

    private func label(_ entry: HadesWorkbenchEntry) -> String {
        if let names = entry.worldNames {
            return names[localization.language.rawValue] ?? names["en"] ?? ""
        }
        if let resource = entry.resource {
            return resource.name(language: localization.language.rawValue)
        }
        return HadesGameModule.resolveText(key: entry.titleKey, localization: localization)
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
                                    detail: HadesGameModule.resolveText(
                                        key: entry.section.titleKey, localization: localization),
                                    systemImage: entry.icon
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
