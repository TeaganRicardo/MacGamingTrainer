import AppKit
import SwiftUI

enum HadesWorkbenchSection: String, CaseIterable, Identifiable {
    case combat, values, resources, catalog, currentTraits, management
    var id: String { "hades.section.\(rawValue)" }
    var key: String { "hades.\(rawValue)" }
    var icon: String {
        switch self {
        case .combat: return "shield.fill"
        case .values: return "person.fill"
        case .resources: return "shippingbox.fill"
        case .catalog: return "sparkles"
        case .currentTraits: return "list.bullet.rectangle"
        case .management: return "gearshape.fill"
        }
    }
}

struct HadesSidebarActions: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Divider().padding(.vertical, 2)
            ForEach(HadesWorkbenchSection.allCases) { section in
                TrainerSectionButton(title: HadesPresentation.text(section.key, language: localization.language), systemImage: section.icon) {
                    navigate(section.id)
                }
                .focusEffectDisabled()
            }
        }
    }
}

struct HadesOperationFeedback: View {
    @ObservedObject var model: HadesTrainerModel
    var body: some View { TrainerFeedbackOverlay(notice: model.feedback, onDismiss: model.dismissFeedback) }
}

struct HadesTrainerView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerGamePageVisible) private var pageVisible
    @Environment(\.trainerManagementActions) private var managementActions

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    private var error: String { model.localError.isEmpty ? model.backendStatus.error : model.localError }
    private func state(_ feature: HadesFeature) -> TrainerFeatureControlState {
        let enabled = model.isEnabled(feature)
        return TrainerFeatureControlState(isOn: enabled, isInteractive: model.canMutate,
            canEditValue: model.canMutate, opacity: model.heroReady ? 1 : 0.6,
            indicatorColor: enabled ? theme.accent : theme.inactive, helpText: feature == .fullGodGauge ? text("hades.fullGodGaugeHelp") : (feature == .invincibility ? text("hades.invincibilityHelp") : text("hades.noConsumptionHelp")), isWarning: false)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            if !error.isEmpty {
                TrainerMessageBanner(text: localization.presentation(error, arguments: model.backendStatus.errorArguments),
                    icon: "exclamationmark.triangle.fill", color: theme.warning)
            }
            if !model.heroReady {
                TrainerMessageBanner(text: text("hades.waitingForHero"), icon: "person.crop.circle.badge.clock", color: theme.info)
            }
            TrainerSection(title: text("hades.combat"), icon: "shield.fill") {
                VStack(spacing: 0) {
                    ForEach(HadesFeature.allCases.filter(\.isToggle)) { feature in
                        TrainerFeatureToggleRow(title: text(feature.key), icon: feature.icon, state: state(feature),
                            shortcutText: HadesShortcutAction(rawValue: feature.rawValue).map(model.shortcutText)) {
                            model.setFeature(feature, value: !model.isEnabled(feature))
                        }
                    }
                }.trainerGroupedRows()
                VStack(spacing: 0) {
                    ForEach(HadesFeature.allCases.filter { !$0.isToggle }) { feature in
                        HadesFeatureValueRow(model: model, feature: feature)
                    }
                }.trainerGroupedRows()
            }.id(HadesWorkbenchSection.combat.id)

            TrainerSection(title: text("hades.values"), icon: "person.fill") {
                VStack(spacing: 0) {
                    HadesValueRow(model: model, title: text("hades.health"), icon: "heart.fill", value: model.health) {
                        model.setValue("health", value: $0, target: $1)
                    }
                    HadesValueRow(model: model, title: text("hades.maxHealth"), icon: "heart", value: model.maxHealth) {
                        model.setValue("maxHealth", value: $0, target: $1)
                    }
                    HadesValueRow(model: model, title: text("hades.money"), icon: "circle.fill", value: model.money) {
                        model.setValue("money", value: $0, target: $1)
                    }
                    HadesValueRow(model: model, title: text("hades.rerolls"), icon: "arrow.clockwise", value: model.rerolls) {
                        model.setValue("rerolls", value: $0, target: $1)
                    }
                    TrainerLabeledControlRow(title: text("hades.godGauge"), icon: "bolt.heart.fill", tint: theme.accent, emphasized: model.heroReady) {
                        Text("\(HadesNumberDraft.format(model.godGauge)) / \(HadesNumberDraft.format(model.maxGodGauge))")
                            .monospacedDigit().foregroundStyle(.secondary)
                    }
                }.trainerGroupedRows()
                HStack {
                    TrainerShortcutBadgeSlot(text: model.shortcutText(.heal))
                    TrainerSecondaryActionButton(title: text("hades.heal"), systemImage: "heart.fill", enabled: model.canMutate, action: model.heal)
                    Spacer()
                }
            }.id(HadesWorkbenchSection.values.id)

            TrainerSection(title: text("hades.resources"), icon: "shippingbox.fill") {
                VStack(spacing: 0) {
                    ForEach(model.resourceCatalog) { resource in
                        HadesValueRow(model: model, title: resource.name(language: localization.language.rawValue),
                            icon: "diamond.fill", value: model.resources[resource.id] ?? 0) {
                            model.setResource(resource.id, value: $0, target: $1)
                        }
                        .id(resource.id)
                    }
                }.trainerGroupedRows()
            }.id(HadesWorkbenchSection.resources.id)

            HadesCatalogView(model: model).id(HadesWorkbenchSection.catalog.id)

            TrainerSection(title: text("hades.currentTraits"), icon: "list.bullet.rectangle") {
                if model.traits.isEmpty { TrainerEmptyState(text: text("hades.emptyTraits")) }
                else {
                    LazyVStack(spacing: 10) {
                        ForEach(model.traits) { trait in
                            HadesCurrentTraitRow(model: model, trait: trait).id(trait.instanceId)
                        }
                    }
                }
            }.id(HadesWorkbenchSection.currentTraits.id)

            TrainerSection(title: text("hades.management"), icon: "gearshape.fill") {
                HStack {
                    if let open = managementActions.openSaveManagement {
                        TrainerSecondaryActionButton(title: localization.localized("host.saveManagement"), systemImage: "externaldrive",
                            enabled: model.hostActionsEnabled, action: open)
                    }
                    TrainerSecondaryActionButton(title: localization.localized("host.shortcutSettings"), systemImage: "keyboard") {
                        model.shortcutSettingsPresented = true
                    }
                    Spacer()
                    TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))
                    TrainerSecondaryActionButton(title: localization.localized("host.disableAll"), systemImage: "power",
                        enabled: model.hostActionsEnabled, action: model.disableAll)
                }
                if !model.shortcutError.isEmpty {
                    TrainerMessageBanner(text: text(model.shortcutError), icon: "keyboard", color: theme.warning)
                }
            }.id(HadesWorkbenchSection.management.id)
        }
        .sheet(isPresented: $model.shortcutSettingsPresented) { HadesShortcutSettingsView(model: model) }
        .onChange(of: pageVisible) { _, visible in
            if !visible { model.shortcutSettingsPresented = false }
        }
    }
}

private struct HadesValueRow: View {
    @ObservedObject var model: HadesTrainerModel
    let title: String
    let icon: String
    let value: Double
    let onCommit: (Double, HadesHeroTarget?) -> Void
    @Environment(\.trainerTheme) private var theme
    @State private var draft: HadesNumberDraft

    init(model: HadesTrainerModel, title: String, icon: String, value: Double,
         onCommit: @escaping (Double, HadesHeroTarget?) -> Void) {
        self.model = model; self.title = title; self.icon = icon; self.value = value; self.onCommit = onCommit
        _draft = State(initialValue: HadesNumberDraft(value: value))
    }
    var body: some View {
        TrainerLabeledControlRow(title: title, icon: icon, tint: theme.accent, emphasized: model.heroReady) {
            TrainerNumberField(text: Binding(get: { draft.text }, set: { draft.update($0) }), accessibilityLabel: title,
                enabled: model.canMutate, onEditingChanged: { active in
                    if active { draft.begin(target: model.target) } else { draft.end() }
                }, onCommit: { completed in
                    guard completed.changed else { return completed.text }
                    guard let number = Double(completed.text), number.isFinite, number.rounded() == number,
                          number >= 0, number <= 1_000_000_000 else {
                        model.rejectInvalidValue(); return completed.text
                    }
                    onCommit(number, draft.target)
                    return HadesNumberDraft.format(number)
                })
        }
        .onChange(of: value) { _, value in draft.observe(value) }
    }
}

private struct HadesFeatureValueRow: View {
    @ObservedObject var model: HadesTrainerModel
    let feature: HadesFeature
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var draft = HadesNumberDraft(value: 1)
    var body: some View {
        TrainerLabeledControlRow(title: HadesPresentation.text(feature.key, language: localization.language), icon: feature.icon, tint: theme.accent, emphasized: model.number(feature) != feature.neutralValue) {
            TrainerNumberField(text: Binding(get: { draft.text }, set: { draft.update($0) }),
                accessibilityLabel: HadesPresentation.text(feature.key, language: localization.language),
                enabled: model.canMutate, onEditingChanged: { active in
                    if active { draft.begin(target: nil) } else { draft.end() }
                }, onCommit: { completed in
                    completed.changed ? model.setNumber(feature, text: completed.text) : completed.text
                })
            if feature != .dashBonus { Text("×").foregroundStyle(.secondary) }
            TrainerResetButton(title: HadesPresentation.text("hades.reset", language: localization.language), enabled: model.canMutate) {
                model.setFeature(feature, value: feature.neutralValue)
            }
        }
        .onChange(of: model.number(feature), initial: true) { _, value in draft.observe(value) }
    }
}

private struct HadesCatalogView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var query = ""
    @State private var kind = "all"
    @State private var selection = ""
    @State private var rarity = "Heroic"
    @State private var level = "1"
    private let kinds = ["all", "boon", "hammer", "chaos", "keepsake", "companion"]
    private var matches: [HadesCatalogEntry] { model.catalog.filter { (kind == "all" || $0.kind == kind) && $0.matches(query) } }
    private var selected: HadesCatalogEntry? { matches.first { $0.id == selection } }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    var body: some View {
        TrainerSection(title: text("hades.catalog"), icon: "sparkles") {
            HStack {
                Picker(text("hades.catalog"), selection: $kind) {
                    ForEach(kinds, id: \.self) { Text(text("hades.kind.\($0)")).tag($0) }
                }.frame(maxWidth: 210)
                TrainerSearchField(text: $query, placeholder: text("hades.search"), clearLabel: localization.localized("host.search.clear"))
            }
            if matches.isEmpty { TrainerEmptyState(text: text("hades.emptyCatalog")) }
            else {
                Picker(text("hades.selectTrait"), selection: $selection) {
                    ForEach(matches) { entry in Text(entry.name(language: localization.language.rawValue)).tag(entry.id) }
                }.labelsHidden().frame(maxWidth: .infinity)
            }
            if let selected {
                TrainerListCard {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text(selected.name(language: localization.language.rawValue)).font(.headline)
                            Spacer()
                            Text(selected.source(language: localization.language.rawValue)).font(.caption).foregroundStyle(.secondary)
                        }
                        Text(selected.description(language: localization.language.rawValue)).font(.callout).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        if selected.kind == "keepsake" || selected.kind == "companion" {
                            Text(text("hades.equipmentAcquireHelp")).font(.caption).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        HStack(spacing: 12) {
                            Picker(text("hades.rarity"), selection: $rarity) {
                                ForEach(selected.rarities, id: \.self) { Text(text("hades.rarity.\($0)")).tag($0) }
                            }.frame(maxWidth: 220)
                            if selected.supportsLevel {
                                Text(text("hades.level"))
                                TrainerNumberField(text: $level, accessibilityLabel: text("hades.level"), width: 60)
                            }
                            Spacer()
                            TrainerPrimaryActionButton(title: text("hades.acquire"), enabled: model.canMutate && selected.acquirable != false) {
                                guard let amount = Int(level), (1...100).contains(amount) else { model.rejectInvalidValue(); return }
                                model.addTrait(selected, rarity: rarity, level: selected.supportsLevel ? amount : 1)
                            }
                        }
                    }
                }
            }
        }
        .onChange(of: matches.map(\.id), initial: true) { _, ids in
            if !ids.contains(selection) { selection = ids.first ?? "" }
        }
        .onChange(of: selection, initial: true) { _, _ in
            let rarities = selected?.rarities ?? []
            rarity = rarities.contains("Heroic") ? "Heroic" : rarities.first ?? "Common"
            level = "1"
        }
    }
}

private struct HadesCurrentTraitRow: View {
    @ObservedObject var model: HadesTrainerModel
    let trait: HadesCurrentTrait
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var rarity: String
    @State private var level: String
    @State private var owner: HadesHeroTarget?
    private var entry: HadesCatalogEntry? { model.catalog.first { $0.id == trait.name } }
    private var rarities: [String] { entry?.rarities ?? [trait.rarity] }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    init(model: HadesTrainerModel, trait: HadesCurrentTrait) {
        self.model = model; self.trait = trait
        _rarity = State(initialValue: trait.rarity); _level = State(initialValue: String(trait.level))
        _owner = State(initialValue: model.target)
    }
    var body: some View {
        TrainerListCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(model.traitName(trait, language: localization.language)).font(.headline)
                    Spacer()
                    if !trait.canEdit {
                        Text(text("hades.rarity.\(trait.rarity)")).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if trait.canEdit {
                    HStack {
                        Picker(text("hades.rarity"), selection: $rarity) {
                            ForEach(rarities, id: \.self) { Text(text("hades.rarity.\($0)")).tag($0) }
                        }.frame(maxWidth: 210)
                        if entry?.supportsLevel != false {
                            Text(text("hades.level"))
                            TrainerNumberField(text: $level, accessibilityLabel: text("hades.level"), width: 60)
                        }
                        Spacer()
                        TrainerSecondaryActionButton(title: text("hades.apply"), enabled: model.canMutate && (rarity != trait.rarity || level != String(trait.level))) {
                            guard let amount = Int(level), (1...100).contains(amount) else { model.rejectInvalidValue(); return }
                            model.updateTrait(trait, rarity: rarity, level: amount, target: owner)
                        }
                        TrainerSecondaryActionButton(title: text("hades.remove"), enabled: model.canMutate && trait.canRemove) { model.removeTrait(trait) }
                    }
                } else if !trait.limitation.isEmpty {
                    Text(text("hades.limitation.\(trait.limitation)")).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .onChange(of: trait) { old, updated in
            if rarity == old.rarity && level == String(old.level) {
                rarity = updated.rarity; level = String(updated.level); owner = model.target
            }
        }
        .onChange(of: model.target) { _, target in
            if rarity == trait.rarity && level == String(trait.level) { owner = target }
        }
    }
}

private struct HadesShortcutSettingsView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var capturing: HadesShortcutAction?
    @State private var keyMonitor: Any?
    private func text(_ key: String) -> String { localization.presentation(key) }
    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.shortcutSettings"), width: 560) {
            Button(text("hades.reset"), action: model.resetShortcuts)
        } content: {
            Text(localization.localized("host.hotkeys.help")).foregroundStyle(.secondary)
            ForEach(HadesShortcutAction.allCases) { action in
                HStack {
                    Text(text(action.key))
                    Spacer()
                    Button { begin(action) } label: {
                        Text(capturing == action ? localization.localized("host.hotkeys.pressNew") : model.shortcutText(action))
                            .font(.system(.body, design: .monospaced)).frame(width: theme.shortcutCaptureWidth)
                    }.buttonStyle(.bordered).disabled(action == .disableAll)
                }
            }
            if !model.shortcutError.isEmpty { Text(text(model.shortcutError)).foregroundStyle(theme.warning) }
        } footer: {
            HStack { Spacer(); Button(localization.localized("host.done")) { model.shortcutSettingsPresented = false } }
        }
        .onDisappear(perform: stop)
    }
    private func begin(_ action: HadesShortcutAction) {
        stop(); capturing = action
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 { DispatchQueue.main.async { stop() }; return nil }
            guard let chord = HotkeyChord.capture(event) else { return nil }
            DispatchQueue.main.async { model.setShortcut(action, chord: chord); stop() }
            return nil
        }
    }
    private func stop() {
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor); self.keyMonitor = nil }
        capturing = nil
    }
}

struct HadesManagementCommands: Commands {
    @ObservedObject var model: HadesTrainerModel
    @ObservedObject var localization: TrainerLocalizationStore
    var body: some Commands {
        CommandMenu(localization.localized("host.trainerMenu")) {
            Button(localization.localized("host.refreshStatus"), action: model.refreshFromHost).disabled(model.busy)
            Button(localization.localized("host.disableAll"), action: model.disableAll).disabled(!model.hostActionsEnabled)
            Divider()
            Button(localization.localized("host.shortcutSettings")) { model.shortcutSettingsPresented = true }
        }
    }
}
