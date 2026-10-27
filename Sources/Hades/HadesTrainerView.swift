import AppKit
import SwiftUI

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
    @State private var gameSpeedInput = "1.0"
    @State private var gameSpeedPreview: Double?
    @State private var gameSpeedEditing = false

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    private var error: String { model.localError.isEmpty ? model.backendStatus.error : model.localError }

    private func state(_ feature: HadesFeature) -> TrainerFeatureControlState {
        let enabled = model.isEnabled(feature)
        return TrainerFeatureControlState(
            isOn: enabled, isInteractive: model.canEditIntent, canEditValue: model.canEditIntent,
            opacity: model.heroReady ? 1 : 0.6,
            indicatorColor: model.isActive(feature) ? theme.accent : theme.inactive,
            helpText: text(feature.helpKey),
            isWarning: enabled && !model.isActive(feature)
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            if !error.isEmpty {
                TrainerMessageBanner(
                    text: localization.presentation(error, arguments: model.backendStatus.errorArguments),
                    icon: "exclamationmark.triangle.fill", color: theme.warning
                )
            }
            if !model.heroReady {
                TrainerMessageBanner(
                    text: text("hades.waitingForHero"),
                    icon: "person.crop.circle.badge.clock", color: theme.info
                )
            }

            runDataSection.id(HadesWorkbenchSection.values.id)
            commonSection.id(HadesWorkbenchSection.common.id)
            boonsSection.id(HadesWorkbenchSection.boons.id)
            resourcesSection.id(HadesWorkbenchSection.resources.id)
            managementSection.id(HadesWorkbenchSection.management.id)
        }
        .sheet(isPresented: $model.shortcutSettingsPresented) { HadesShortcutSettingsView(model: model) }
        .onChange(of: pageVisible) { _, visible in
            if !visible { model.shortcutSettingsPresented = false }
        }
    }

    private var runDataSection: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            TrainerSectionHeader(
                title: text(HadesWorkbenchSection.values.titleKey),
                icon: HadesWorkbenchSection.values.icon
            ) {
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        model.numericControlsExpanded.toggle()
                    }
                } label: {
                    HStack(spacing: 5) {
                        Text(text(model.numericControlsExpanded
                                  ? "hades.section.collapse" : "hades.section.expand"))
                        Image(systemName: model.numericControlsExpanded ? "chevron.up" : "chevron.down")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 4)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12), count: 4), spacing: 12) {
                HadesVitalMetricCard(model: model)
                HadesAmountMetricCard(model: model, title: text("hades.money"), icon: "circle.fill",
                                      value: model.money, field: "money")
                HadesAmountMetricCard(model: model, title: text("hades.rerolls"), icon: "arrow.clockwise",
                                      value: model.rerolls, field: "rerolls")
                HadesAmountMetricCard(model: model, title: text("hades.godGauge"), icon: "bolt.heart.fill",
                                      value: model.godGauge, field: "godGauge")
                if model.numericControlsExpanded {
                    ForEach(HadesFeature.allCases.filter { !$0.isToggle && $0 != .gameSpeed }) { feature in
                        HadesFeatureMetricCard(model: model, feature: feature)
                    }
                }
            }
            HStack(spacing: 8) {
                TrainerShortcutBadgeSlot(text: model.shortcutText(.heal))
                TrainerSecondaryActionButton(
                    title: text("hades.heal"), systemImage: "heart.fill",
                    enabled: model.canMutate, action: model.heal
                )
                Spacer()
            }
        }
    }

    private var commonSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.common.titleKey),
                       icon: HadesWorkbenchSection.common.icon) {
            VStack(spacing: 1) {
                ForEach(HadesFeature.allCases.filter { $0.isToggle && $0 != .boonRarityEnabled }) { feature in
                    TrainerFeatureToggleRow(
                        title: text(feature.key), icon: feature.icon, state: state(feature),
                        shortcutText: HadesShortcutAction(rawValue: feature.rawValue).map(model.shortcutText)
                    ) {
                        model.setFeature(feature, value: !model.isEnabled(feature))
                    }
                }
            }
            .trainerGroupedRows()
            gameSpeedPanel
        }
    }

    private var gameSpeedMapping: TrainerSliderMapping {
        .anchoredLogarithmic(
            values: [0.1, 0.5, 1.0, 2.0, 5.0],
            step: 0.1,
            detents: [0.5, 1.0, 2.0],
            magnetDistance: 0.10,
            settleDistance: 0.04
        )
    }

    private func speedNumber(_ value: Double) -> String { String(format: "%.1f", value) }

    private var gameSpeedInputBinding: Binding<String> {
        Binding(
            get: { gameSpeedPreview.map(speedNumber) ?? gameSpeedInput },
            set: { gameSpeedPreview = nil; gameSpeedInput = $0 }
        )
    }

    private var gameSpeedSliderValue: Binding<Double> {
        Binding(
            get: { Double(gameSpeedInput) ?? model.number(.gameSpeed) },
            set: { value in
                gameSpeedPreview = nil
                gameSpeedInput = speedNumber(value)
                model.setFeature(.gameSpeed, value: (value * 10).rounded() / 10)
            }
        )
    }

    private var gameSpeedPanel: some View {
        VStack(alignment: .leading, spacing: 4) {
            TrainerLabeledControlRow(
                title: localization.localized("host.timeWarp.title"),
                icon: "speedometer",
                tint: model.canMutate ? theme.accent : theme.inactive,
                emphasized: model.canMutate,
                helpText: localization.localized("host.timeWarp.hint")
            ) {
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: "1.0",
                    accessibilityLabel: localization.localized("host.timeWarp.title"),
                    width: 62,
                    enabled: model.canMutate,
                    onEditingChanged: { active in
                        gameSpeedEditing = active
                        if !active { gameSpeedPreview = nil }
                    },
                    onCommit: { completed in
                        guard completed.changed else { return completed.text }
                        guard let value = Double(completed.text), value.isFinite, (0...10).contains(value) else {
                            model.rejectInvalidValue()
                            return completed.text
                        }
                        let normalized = speedNumber((value * 10).rounded() / 10)
                        gameSpeedInput = normalized
                        model.setFeature(.gameSpeed, value: (value * 10).rounded() / 10)
                        return normalized
                    }
                )
                Text("×").foregroundStyle(.secondary)
                TrainerMappedSlider(
                    value: gameSpeedSliderValue,
                    mapping: gameSpeedMapping,
                    accessibilityLabel: localization.localized("host.timeWarp.title"),
                    accessibilityHint: localization.localized("host.timeWarp.hint"),
                    enabled: model.canMutate,
                    onPreviewValue: { gameSpeedPreview = $0 }
                )
                .frame(width: 200)
            }
            if let actual = model.features[HadesFeature.gameSpeed.rawValue]?.actualNumber {
                let key = abs(actual - model.number(.gameSpeed)) < 0.000001
                    ? "host.timeWarp.actual" : "host.timeWarp.pending"
                Text(localization.presentation(key, arguments: [speedNumber(actual)]))
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.features[HadesFeature.gameSpeed.rawValue]?.errorPresentation {
                Text(localization.presentation(
                    error, arguments: model.features[HadesFeature.gameSpeed.rawValue]?.errorArguments ?? []
                ))
                .font(.caption).foregroundStyle(theme.warning)
            }
        }
        .onChange(of: model.number(.gameSpeed), initial: true) { _, value in
            if !gameSpeedEditing && gameSpeedPreview == nil { gameSpeedInput = speedNumber(value) }
        }
        .trainerGroupedRows()
    }

    private var boonsSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.boons.titleKey),
                       icon: HadesWorkbenchSection.boons.icon) {
            TrainerFeatureToggleRow(
                title: text(HadesFeature.boonRarityEnabled.key),
                icon: HadesFeature.boonRarityEnabled.icon,
                state: state(.boonRarityEnabled),
                shortcutText: model.shortcutText(.boonRarityEnabled)
            ) {
                model.setFeature(.boonRarityEnabled, value: !model.isEnabled(.boonRarityEnabled))
            }
            .trainerGroupedRows()
            HadesCurrentTraitsPanel(model: model)
            HadesCatalogView(model: model)
        }
    }

    private var resourcesSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.resources.titleKey),
                       icon: HadesWorkbenchSection.resources.icon) {
            VStack(spacing: 0) {
                ForEach(model.resourceCatalog) { resource in
                    HadesValueRow(
                        model: model,
                        title: resource.name(language: localization.language.rawValue),
                        icon: "diamond.fill", value: model.resources[resource.id] ?? 0
                    ) {
                        model.setResource(resource.id, value: $0, target: $1)
                    }
                    .id(resource.id)
                }
            }
            .trainerGroupedRows()
        }
    }

    private var managementSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.management.titleKey),
                       icon: HadesWorkbenchSection.management.icon) {
            HStack(spacing: 8) {
                TrainerSecondaryActionButton(
                    title: localization.localized("host.refreshStatus"), systemImage: "arrow.clockwise",
                    enabled: model.backendAvailable && !model.busy, action: model.refreshFromHost
                )
                if let open = managementActions.openSaveManagement {
                    TrainerSecondaryActionButton(
                        title: localization.localized("host.saveManagement"), systemImage: "externaldrive",
                        enabled: model.hostActionsEnabled, action: open
                    )
                }
                TrainerSecondaryActionButton(
                    title: localization.localized("host.shortcutSettings"), systemImage: "keyboard"
                ) {
                    model.shortcutSettingsPresented = true
                }
                Spacer()
                TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))
                TrainerSecondaryActionButton(
                    title: localization.localized("host.disableAll"), systemImage: "power",
                    enabled: model.hostActionsEnabled, action: model.disableAll
                )
            }
            if !model.shortcutError.isEmpty {
                TrainerMessageBanner(text: text(model.shortcutError),
                                     icon: "keyboard", color: theme.warning)
            }
        }
    }
}

private struct HadesVitalMetricCard: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var currentDraft: HadesNumberDraft
    @State private var maximumDraft: HadesNumberDraft

    init(model: HadesTrainerModel) {
        self.model = model
        _currentDraft = State(initialValue: HadesNumberDraft(value: model.health))
        _maximumDraft = State(initialValue: HadesNumberDraft(value: model.maxHealth))
    }

    private var title: String { HadesPresentation.text("hades.health", language: localization.language) }

    private func commit(_ completion: TrainerTextField.Completion,
                        draft: HadesNumberDraft, field: String) -> String {
        guard completion.changed else { return completion.text }
        guard let number = Double(completion.text), number.isFinite,
              number.rounded() == number, number >= 1, number <= 1_000_000_000 else {
            model.rejectInvalidValue(); return completion.text
        }
        model.setValue(field, value: number, target: draft.target)
        return HadesNumberDraft.format(number)
    }

    var body: some View {
        TrainerMetricCard(title: title, icon: "heart.fill", tint: .pink) {
            Color.clear.frame(width: 26, height: 24)
        } content: {
            HStack(spacing: 2) {
                TrainerNumberField(
                    text: Binding(get: { currentDraft.text }, set: { currentDraft.update($0) }),
                    accessibilityLabel: localization.localized("host.input.currentValue", arguments: [title]),
                    width: 54, enabled: model.canMutate, alignment: .center,
                    onEditingChanged: { active in
                        if active { currentDraft.begin(target: model.target) } else { currentDraft.end() }
                    },
                    onCommit: { commit($0, draft: currentDraft, field: "health") }
                )
                Text("/").foregroundStyle(.secondary)
                TrainerNumberField(
                    text: Binding(get: { maximumDraft.text }, set: { maximumDraft.update($0) }),
                    accessibilityLabel: localization.localized("host.input.maximumValue", arguments: [title]),
                    width: 54, enabled: model.canMutate, alignment: .center,
                    onEditingChanged: { active in
                        if active { maximumDraft.begin(target: model.target) } else { maximumDraft.end() }
                    },
                    onCommit: { commit($0, draft: maximumDraft, field: "maxHealth") }
                )
            }
        }
        .onChange(of: model.health) { _, value in currentDraft.observe(value) }
        .onChange(of: model.maxHealth) { _, value in maximumDraft.observe(value) }
    }
}

private struct HadesAmountMetricCard: View {
    @ObservedObject var model: HadesTrainerModel
    let title: String
    let icon: String
    let value: Double
    let field: String
    @Environment(\.trainerTheme) private var theme
    @State private var draft: HadesNumberDraft

    init(model: HadesTrainerModel, title: String, icon: String, value: Double, field: String) {
        self.model = model; self.title = title; self.icon = icon; self.value = value; self.field = field
        _draft = State(initialValue: HadesNumberDraft(value: value))
    }

    var body: some View {
        TrainerMetricCard(title: title, icon: icon, tint: theme.accent) {
            Color.clear.frame(width: 26, height: 24)
        } content: {
            TrainerNumberField(
                text: Binding(get: { draft.text }, set: { draft.update($0) }),
                accessibilityLabel: title, width: 96, enabled: model.canMutate, alignment: .center,
                onEditingChanged: { active in
                    if active { draft.begin(target: model.target) } else { draft.end() }
                },
                onCommit: { completed in
                    guard completed.changed else { return completed.text }
                    guard let number = Double(completed.text), number.isFinite,
                          number.rounded() == number, number >= 0, number <= 1_000_000_000 else {
                        model.rejectInvalidValue(); return completed.text
                    }
                    model.setValue(field, value: number, target: draft.target)
                    return HadesNumberDraft.format(number)
                }
            )
        }
        .onChange(of: value) { _, value in draft.observe(value) }
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

private struct HadesFeatureMetricCard: View {
    @ObservedObject var model: HadesTrainerModel
    let feature: HadesFeature
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var draft: HadesNumberDraft

    init(model: HadesTrainerModel, feature: HadesFeature) {
        self.model = model; self.feature = feature
        _draft = State(initialValue: HadesNumberDraft(value: feature.neutralValue))
    }

    var body: some View {
        let title = HadesPresentation.text(feature.key, language: localization.language)
        return TrainerMetricCard(title: title, icon: feature.icon, tint: theme.accent) {
            TrainerResetButton(
                title: HadesPresentation.text("hades.reset", language: localization.language),
                enabled: model.canEditIntent
            ) {
                model.setFeature(feature, value: feature.neutralValue)
            }
        } content: {
            HStack(spacing: 3) {
                TrainerNumberField(
                    text: Binding(get: { draft.text }, set: { draft.update($0) }),
                    accessibilityLabel: title, width: 58, enabled: model.canEditIntent, alignment: .center,
                    onEditingChanged: { active in
                        if active { draft.begin(target: nil) } else { draft.end() }
                    },
                    onCommit: { completed in
                        completed.changed ? model.setNumber(feature, text: completed.text) : completed.text
                    }
                )
                if feature != .dashBonus { Text("×").foregroundStyle(.secondary) }
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
    @State private var source = ""
    @State private var selection = ""
    @State private var rarity = "Heroic"
    @State private var level = "1"

    private struct SourceGroup: Identifiable {
        let id: String
        let kind: String
        let entries: [HadesCatalogEntry]
    }

    private var matches: [HadesCatalogEntry] { model.catalog.filter { $0.kind != "curse" && $0.matches(query) } }
    private func sourceID(_ entry: HadesCatalogEntry) -> String {
        let nativeName = entry.sourceNames?["en"] ?? entry.kind
        if entry.kind == "boon" && nativeName.contains(" / ") { return "boon:duo" }
        return entry.kind + ":" + nativeName
    }
    private var sourceGroups: [SourceGroup] {
        let kinds = ["boon", "hammer", "chaos", "temporary", "special", "keepsake", "companion"]
        return Dictionary(grouping: matches, by: sourceID).map { id, entries in
            SourceGroup(id: id, kind: entries[0].kind, entries: entries)
        }.sorted { lhs, rhs in
            let lRank = kinds.firstIndex(of: lhs.kind) ?? kinds.count
            let rRank = kinds.firstIndex(of: rhs.kind) ?? kinds.count
            if lRank != rRank { return lRank < rRank }
            return lhs.id.localizedStandardCompare(rhs.id) == .orderedAscending
        }
    }
    private var selectedGroup: SourceGroup? { sourceGroups.first { $0.id == source } }
    private var selectedEntries: [HadesCatalogEntry] { selectedGroup?.entries ?? [] }
    private var selected: HadesCatalogEntry? { selectedEntries.first { $0.id == selection } }
    private func sourceTitle(_ group: SourceGroup) -> String {
        if group.id == "boon:duo" { return text("hades.kind.duo") }
        if group.kind == "keepsake" || group.kind == "companion" {
            return text("hades.kind." + group.kind)
        }
        return group.entries[0].source(language: localization.language.rawValue)
    }
    private func repairSelections() {
        if !sourceGroups.contains(where: { $0.id == source }) {
            source = sourceGroups.first?.id ?? ""
        }
        repairItemSelection()
    }
    private func repairItemSelection() {
        if !selectedEntries.contains(where: { $0.id == selection }) {
            selection = selectedEntries.first?.id ?? ""
        }
    }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(text("hades.catalog"), systemImage: "scope")
                .font(.subheadline.weight(.medium))
            TrainerSearchField(text: $query, placeholder: text("hades.search"),
                               clearLabel: localization.localized("host.search.clear"))
                .frame(maxWidth: 280)
            if matches.isEmpty { TrainerEmptyState(text: text("hades.emptyCatalog")) }
            else {
                HStack(alignment: .bottom, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades.exactSource")).font(.caption).foregroundStyle(.secondary)
                        Picker(text("hades.exactSource"), selection: $source) {
                            ForEach(sourceGroups) { group in
                                Text(sourceTitle(group)).tag(group.id)
                            }
                        }
                        .labelsHidden()
                    }
                    .frame(width: 240)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades.selectTrait")).font(.caption).foregroundStyle(.secondary)
                        Picker(text("hades.selectTrait"), selection: $selection) {
                            ForEach(selectedEntries) { entry in
                                Text(entry.name(language: localization.language.rawValue)).tag(entry.id)
                            }
                        }
                        .labelsHidden()
                    }
                    .frame(maxWidth: .infinity)
                }
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
                        if selected.kind == "chaos" {
                            HadesChaosPairControls(model: model, blessing: selected, rarity: rarity)
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
        .trainerPanel()
        .onChange(of: matches.map(\.id), initial: true) { _, _ in repairSelections() }
        .onChange(of: source) { _, _ in repairItemSelection() }
        .onChange(of: selection, initial: true) { _, _ in
            let rarities = selected?.rarities ?? []
            rarity = rarities.contains("Heroic") ? "Heroic" : rarities.first ?? "Common"
            level = "1"
        }
    }
}

private struct HadesCurrentTraitsPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var search = ""
    @State private var selection = ""

    private func text(_ key: String) -> String {
        HadesPresentation.text(key, language: localization.language)
    }
    private var matches: [HadesCurrentTrait] {
        let words = search.lowercased().split(whereSeparator: \.isWhitespace)
        guard !words.isEmpty else { return model.traits }
        return model.traits.filter { trait in
            let names = TrainerPresentationLanguage.allCases.map {
                model.traitName(trait, language: $0)
            }
            let searchable = (names + [trait.name]).joined(separator: " ").lowercased()
            return words.allSatisfy { searchable.contains($0) }
        }
    }
    private var selected: HadesCurrentTrait? { matches.first { $0.instanceId == selection } }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Label(text("hades.currentTraits"), systemImage: "slider.horizontal.3")
                    .font(.subheadline.weight(.medium))
                Spacer()
                TrainerSearchField(text: $search, placeholder: text("hades.search"),
                                   clearLabel: localization.localized("host.search.clear"))
                    .frame(maxWidth: 240)
            }
            if matches.isEmpty {
                TrainerEmptyState(text: text("hades.emptyTraits"))
            } else {
                Picker(text("hades.currentTraits"), selection: $selection) {
                    ForEach(matches) { trait in
                        Text(model.traitName(trait, language: localization.language)
                             + " · " + text("hades.rarity.\(trait.rarity)")).tag(trait.instanceId)
                    }
                }
                .labelsHidden()
                .frame(maxWidth: .infinity)
                if let selected {
                    HadesCurrentTraitRow(model: model, trait: selected).id(selected.instanceId)
                }
            }
        }
        .trainerPanel()
        .onChange(of: matches.map(\.instanceId), initial: true) { _, ids in
            if !ids.contains(selection) { selection = ids.first ?? "" }
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
                    }
                } else if !trait.limitation.isEmpty {
                    Text(text("hades.limitation.\(trait.limitation)")).font(.caption).foregroundStyle(.secondary)
                }
                HadesEffectLifecycleControls(model: model, trait: trait)
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
            ForEach(HadesWorkbenchCatalog.orderedShortcutActions) { action in
                HStack {
                    Text(text(action.key))
                    Spacer()
                    Button { begin(action) } label: {
                        Text(capturing == action ? localization.localized("host.hotkeys.pressNew") : model.shortcutText(action))
                            .font(.system(.body, design: .monospaced)).frame(width: theme.shortcutCaptureWidth)
                    }.buttonStyle(.bordered)
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
