import AppKit
import SwiftUI

struct HadesOperationFeedback: View {
    @ObservedObject var model: HadesTrainerModel

    var body: some View {
        TrainerOperationFeedback(
            notice: model.feedback,
            hasCurrentIssues: !model.currentIssues.isEmpty,
            detailsNoticeID: model.feedbackDetailsNoticeID,
            onDismiss: model.dismissFeedback,
            onShowDetails: { model.showFeedbackDetails(for: $0) }
        )
    }
}

struct HadesTrainerView: View {
    private enum EditField: Hashable {
        case value(HadesHeroValue)
        case feature(HadesFeature)
        case resource
    }

    /// The selected resource and its observation, so a new selection replaces
    /// the draft while an unfocused count refreshes it.
    private struct ResourceObservation: Equatable {
        let id: String
        let value: Double?
    }

    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var gameSpeedInput = "1.0"
    @State private var gameSpeedPreview: Double?
    @State private var gameSpeedEditing = false
    @State private var focusedField: EditField?
    @State private var drafts: [EditField: String] = [:]
    @State private var resourceSearch = ""
    @State private var selectedResource = ""

    private static let heroValues: [HadesHeroValue] = [.health, .maxHealth, .money, .rerolls, .godGauge]
    private static let multipliers = HadesFeature.allCases.filter { !$0.isToggle && $0 != .gameSpeed }

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    private func featureState(_ feature: HadesFeature) -> TrainerFeatureControlState {
        model.featurePresentation(feature).trainerControlState(using: theme, localization: localization)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            runDataSection.trainerSectionTarget(HadesWorkbenchSection.values.id)
            commonSection.trainerSectionTarget(HadesWorkbenchSection.common.id)
            boonsSection.trainerSectionTarget(HadesWorkbenchSection.boons.id)
            resourcesSection.trainerSectionTarget(HadesWorkbenchSection.resources.id)
            HadesRoomsPanel(model: model).trainerSectionTarget(HadesWorkbenchSection.rooms.id)
            managementSection.trainerSectionTarget(HadesWorkbenchSection.management.id)
        }
        .sheet(isPresented: $model.shortcutSettingsPresented) { HadesShortcutSettingsView(model: model) }
        .sheet(isPresented: $model.profilesPresented) { HadesProfileManagerView(model: model) }
        .sheet(isPresented: $model.diagnosticsPresented) { HadesDiagnosticsView(model: model) }
        .background {
            TrainerGamePageVisibilityObserver { visible in
                if !visible {
                    model.shortcutSettingsPresented = false
                    model.profilesPresented = false
                    model.diagnosticsPresented = false
                }
            }
        }
        // Drafts are owned through edit completion: an observation refreshes
        // every unfocused value and never replaces the focused draft.
        .onChange(of: observedDrafts, initial: true) { _, observed in
            for (field, text) in observed where field != focusedField { drafts[field] = text }
        }
        .onChange(of: filteredResources.map(\.id), initial: true) { _, ids in
            if !ids.contains(selectedResource) { selectedResource = ids.first ?? "" }
        }
        .onChange(of: resourceObservation, initial: true) { old, new in
            if old.id != new.id || focusedField != .resource {
                drafts[.resource] = new.value.map(HadesTrainerModel.displayText) ?? ""
            }
        }
    }

    private var observedDrafts: [EditField: String] {
        var observed: [EditField: String] = [:]
        for value in Self.heroValues {
            observed[.value(value)] = model.observed(value).map(HadesTrainerModel.displayText) ?? ""
        }
        for feature in Self.multipliers {
            observed[.feature(feature)] = HadesTrainerModel.displayText(model.number(feature))
        }
        return observed
    }

    private func draft(_ field: EditField) -> Binding<String> {
        Binding(get: { drafts[field] ?? "" }, set: { drafts[field] = $0 })
    }

    /// Commits route to the hero observed when this field's edit began: the
    /// edit captures the closure rendered for that hero.
    private func completing(_ edit: HadesTextEdit) -> (TrainerTextField.Completion) -> String {
        let target = model.target
        return { draft in
            model.completeTextEdit(edit, text: draft.text, changed: draft.changed, target: target) { key in
                _ = draft.rejected(message: text(key))
            }
        }
    }

    private var runDataSection: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            TrainerSectionHeader(
                title: text(HadesWorkbenchSection.values.titleKey),
                icon: HadesWorkbenchSection.values.icon
            ) {
                TrainerDisclosureButton(isExpanded: $model.numericControlsExpanded,
                    expandTitle: text("hades.section.expand"), collapseTitle: text("hades.section.collapse"))
                    .accessibilityIdentifier("hades.numericDisclosure")
            }
            VStack(spacing: 0) {
                TrainerMetricGrid {
                    TrainerVitalMetricCard(
                        title: text("hades.health"), icon: TrainerSemanticIcon.Concept.vitality, tint: .pink,
                        current: draft(.value(.health)), maximum: draft(.value(.maxHealth)),
                        focus: $focusedField, currentField: .value(.health),
                        onCurrentCommit: completing(.value(.health)),
                        onMaximumCommit: completing(.value(.maxHealth)),
                        maximumField: .value(.maxHealth),
                        locked: model.healthLocked, editable: model.canMutate,
                        onLock: { model.lockHealth(!model.healthLocked) }
                    )
                    TrainerAmountMetricCard(
                        title: text("hades.money"), icon: TrainerSemanticIcon.Concept.currency, tint: .yellow,
                        text: draft(.value(.money)), focus: $focusedField, focusValue: .value(.money),
                        locked: model.moneyLocked, editable: model.canMutate,
                        lockEnabled: !model.isEnabled(.moneyNoDecrease),
                        onLock: { model.lockMoney(!model.moneyLocked) },
                        onCommit: completing(.value(.money))
                    )
                    TrainerAmountMetricCard(
                        title: text("hades.rerolls"), icon: TrainerSemanticIcon.Concept.randomize, tint: theme.accent,
                        text: draft(.value(.rerolls)), focus: $focusedField, focusValue: .value(.rerolls),
                        locked: model.rerollsLocked, editable: model.canMutate,
                        lockEnabled: !model.isEnabled(.rerollsNoDecrease),
                        onLock: { model.lockRerolls(!model.rerollsLocked) },
                        onCommit: completing(.value(.rerolls))
                    )
                    // God Gauge has no fixed lock: Full God Gauge covers it.
                    TrainerCounterMetricCard(
                        title: text("hades.godGauge"), icon: HadesWorkbenchIcon.godGauge, tint: theme.accent,
                        text: draft(.value(.godGauge)), focus: $focusedField, focusValue: .value(.godGauge),
                        detail: nil, onCommit: completing(.value(.godGauge)), editable: model.canMutate
                    )
                }
                TrainerDisclosure(isExpanded: model.numericControlsExpanded) {
                    TrainerMetricGrid {
                        ForEach(Self.multipliers) { feature in
                            // Native units: multipliers are ×, additional dashes a count.
                            TrainerMultiplierMetricCard(
                                title: text(feature.key), icon: feature.icon,
                                text: draft(.feature(feature)), focus: $focusedField, focusValue: .feature(feature),
                                suffix: feature == .dashBonus ? "" : "×", editable: model.canEditIntent,
                                onCommit: completing(.feature(feature))
                            )
                        }
                    }.padding(.top, 12)
                }
            }
        }
    }

    private var commonSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.common.titleKey),
                       icon: HadesWorkbenchSection.common.icon) {
            VStack(spacing: 1) {
                ForEach(HadesFeature.allCases.filter { $0.isToggle && $0 != .boonRarityEnabled }) { feature in
                    TrainerFeatureToggleRow(
                        title: text(feature.key), icon: feature.icon, state: featureState(feature),
                        helpText: text(feature.helpKey),
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
                title: text(HadesFeature.gameSpeed.key),
                icon: TrainerSemanticIcon.Concept.timeScale,
                tint: model.canEditIntent ? theme.accent : theme.inactive,
                emphasized: model.canEditIntent,
                helpText: localization.localized("host.timeWarp.hint")
            ) {
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: "1.0",
                    accessibilityLabel: text(HadesFeature.gameSpeed.key),
                    width: 62,
                    enabled: model.canEditIntent,
                    onEditingChanged: { active in
                        gameSpeedEditing = active
                        if !active { gameSpeedPreview = nil }
                    },
                    onCommit: { completed in
                        guard completed.changed else { return completed.text }
                        guard let value = Double(completed.text), value.isFinite, (0...10).contains(value) else {
                            model.rejectInvalidValue()
                            return completed.rejected(message: text("hades.error.invalidValue"))
                        }
                        let normalized = speedNumber((value * 10).rounded() / 10)
                        gameSpeedInput = normalized
                        model.setFeature(.gameSpeed, value: (value * 10).rounded() / 10)
                        return normalized
                    }
                )
                Text("×").foregroundStyle(.secondary)
                TrainerShortcutBadge(text: model.shortcutText(.decreaseGameSpeed))
                TrainerGamePageVisibilityGate { pageVisible in
                    TrainerMappedSlider(
                        value: gameSpeedSliderValue,
                        mapping: gameSpeedMapping,
                        accessibilityLabel: text(HadesFeature.gameSpeed.key),
                        accessibilityHint: localization.localized("host.timeWarp.hint"),
                        enabled: model.canEditIntent && pageVisible,
                        onPreviewValue: { preview in
                            gameSpeedPreview = preview
                            if preview == nil && !gameSpeedEditing {
                                gameSpeedInput = speedNumber(model.number(.gameSpeed))
                            }
                        }
                    )
                    .frame(width: 200)
                }
                TrainerShortcutBadge(text: model.shortcutText(.increaseGameSpeed))
            }
            if let actual = model.features[HadesFeature.gameSpeed.rawValue]?.actualNumber {
                let key = abs(actual - model.number(.gameSpeed)) < 0.000001
                    ? "host.timeWarp.actual" : "host.timeWarp.pending"
                Text(localization.presentation(key, arguments: [speedNumber(actual)]))
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .onChange(of: model.number(.gameSpeed), initial: true) { _, value in
            if !gameSpeedEditing && gameSpeedPreview == nil { gameSpeedInput = speedNumber(value) }
        }
        .trainerGroupedRows()
    }

    private var boonRarityPanel: some View {
        let controlState = featureState(.boonRarityEnabled)
        return TrainerLabeledControlRow(
            title: text(HadesFeature.boonRarityEnabled.key),
            icon: HadesFeature.boonRarityEnabled.icon,
            tint: controlState.indicatorColor,
            emphasized: controlState.isOn,
            opacity: controlState.opacity,
            helpText: text(HadesFeature.boonRarityEnabled.helpKey)
        ) {
            Picker(text("hades.minimumRarity"), selection: Binding(
                get: { model.boonRarityTarget },
                set: model.setBoonRarityTarget
            )) {
                ForEach(["Common", "Rare", "Epic", "Heroic"], id: \.self) { rarity in
                    Text(text("hades.rarity.\(rarity)")).tag(rarity)
                }
            }
            .labelsHidden()
            .trainerPicker(.compactValue, state: model.canEditIntent ? .interactive : .unavailable)
            TrainerShortcutBadgeSlot(text: model.shortcutText(.boonRarityEnabled))
            TrainerToggleControl(
                title: text(HadesFeature.boonRarityEnabled.key),
                isOn: model.isEnabled(.boonRarityEnabled),
                enabled: controlState.isInteractive,
                helpText: controlState.helpText,
                tint: controlState.indicatorColor,
                onChange: { model.setFeature(.boonRarityEnabled, value: $0) }
            )
        }
        .trainerGroupedRows()
    }

    private var boonsSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.boons.titleKey),
                       icon: HadesWorkbenchSection.boons.icon) {
            boonRarityPanel
            HadesCurrentTraitsPanel(model: model)
            HadesCatalogView(model: model)
        }
    }

    private var resourcesSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.resources.titleKey),
                       icon: HadesWorkbenchSection.resources.icon) {
            TrainerResourceEditor(
                title: text("hades.resources"),
                icon: TrainerSemanticIcon.Concept.item,
                search: $resourceSearch,
                selection: $selectedResource,
                amount: draft(.resource),
                sections: resourceSections,
                enabled: model.canMutate,
                lock: nil,
                itemLabel: resourceLabel,
                onEditingChanged: TrainerTextField.editingTracker($focusedField, equals: .resource),
                onCommit: completing(.resource(selectedResource))
            )
            .trainerPanel()
            HadesGatheringPanel(model: model)
        }
    }

    private var filteredResources: [HadesResourceDefinition] {
        let query = resourceSearch.trimmingCharacters(in: .whitespaces)
        guard !query.isEmpty else { return model.resourceCatalog }
        return model.resourceCatalog.filter { resource in
            ([resource.id] + resource.names.values).contains { $0.localizedCaseInsensitiveContains(query) }
        }
    }

    /// The catalog owns the resources and their order. Hades I's native data
    /// gives them no categories, so they form one section.
    private var resourceSections: [TrainerPickerSection<HadesResourceDefinition>] {
        filteredResources.isEmpty ? [] : [
            TrainerPickerSection(id: 0, title: text("hades.resource.section"), items: filteredResources),
        ]
    }

    private var resourceObservation: ResourceObservation {
        ResourceObservation(id: selectedResource, value: model.resources[selectedResource])
    }

    /// Both official names, current language first, then the observed amount.
    private func resourceLabel(_ resource: HadesResourceDefinition) -> String {
        let primary = resource.name(language: localization.language.rawValue)
        let other: TrainerPresentationLanguage = localization.language == .en ? .zhCN : .en
        let secondary = resource.names[other.rawValue] ?? ""
        let name = secondary.isEmpty || secondary == primary ? primary : "\(primary) · \(secondary)"
        return name + " · " + (model.resources[resource.id].map(HadesTrainerModel.displayText) ?? "—")
    }

    private var managementSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.management.titleKey),
                       icon: HadesWorkbenchSection.management.icon) {
            HadesManagementUtilities(model: model)
        }
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
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                TrainerIconLabel(
                    title: text("hades.catalog"),
                    icon: HadesWorkbenchIcon.catalog,
                    tint: theme.accent,
                    emphasized: true
                )
                Spacer()
                TrainerSearchField(
                    text: $query,
                    placeholder: text("hades.search"),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(maxWidth: 280)
            }

            HadesChaosPairControls(model: model)

            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.exactSource")).font(.caption).foregroundStyle(.secondary)
                    Picker(text("hades.exactSource"), selection: $source) {
                        if sourceGroups.isEmpty { Text(text("hades.emptyCatalog")).tag("") }
                        ForEach(sourceGroups) { group in
                            Text(sourceTitle(group)).tag(group.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.expanding, state: model.canMutate && !sourceGroups.isEmpty ? .interactive : .unavailable)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.selectTrait")).font(.caption).foregroundStyle(.secondary)
                    Picker(text("hades.selectTrait"), selection: $selection) {
                        if selectedEntries.isEmpty { Text(text("hades.emptyCatalog")).tag("") }
                        ForEach(selectedEntries) { entry in
                            Text(entry.name(language: localization.language.rawValue)).tag(entry.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.expanding, state: model.canMutate && !selectedEntries.isEmpty ? .interactive : .unavailable)
                }
            }

            if let selected {
                VStack(alignment: .leading, spacing: 4) {
                    Text(selected.name(language: localization.language.rawValue))
                        .font(.subheadline.weight(.semibold))
                    if !selected.description(language: localization.language.rawValue).isEmpty {
                        Text(selected.description(language: localization.language.rawValue))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if selected.kind == "keepsake" || selected.kind == "companion" {
                        Text(text("hades.equipmentAcquireHelp"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.rarity")).font(.caption).foregroundStyle(.secondary)
                    Picker(text("hades.rarity"), selection: $rarity) {
                        if selected == nil { Text(text("hades.emptyCatalog")).tag(rarity) }
                        ForEach(selected?.rarities ?? [], id: \.self) {
                            Text(text("hades.rarity.\($0)")).tag($0)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.compactValue, state: selected != nil && model.canMutate ? .interactive : .unavailable)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.level")).font(.caption).foregroundStyle(.secondary)
                    TrainerNumberField(
                        text: $level,
                        accessibilityLabel: text("hades.level"),
                        accessibilityIdentifier: "hades.catalog.level",
                        width: 60,
                        enabled: selected?.supportsLevel == true && model.canMutate,
                        onCommit: { completion in
                            guard let amount = Int(completion.text), (1...100).contains(amount) else {
                                return completion.rejected(message: text("hades.error.invalidValue"))
                            }
                            return String(amount)
                        }
                    )
                    .id(selected?.id ?? "")
                }

                Spacer()
                TrainerSecondaryActionButton(
                    title: text("hades.acquire"),
                    systemImage: TrainerSemanticIcon.Action.acquire,
                    enabled: selected != nil && model.canMutate && selected?.acquirable != false,
                    widthRole: .compactRow
                ) {
                    guard let selected else { return }
                    guard let amount = Int(level), (1...100).contains(amount) else {
                        model.rejectInvalidValue()
                        return
                    }
                    model.addTrait(selected, rarity: rarity, level: selected.supportsLevel ? amount : 1)
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
    @State private var selectedTraitName = ""

    private func text(_ key: String) -> String {
        HadesPresentation.text(key, language: localization.language)
    }

    private func catalogEntry(_ trait: HadesCurrentTrait) -> HadesCatalogEntry? {
        model.catalog.first { $0.id == trait.name }
    }

    private func sourceLabel(_ trait: HadesCurrentTrait, language: TrainerPresentationLanguage) -> String {
        guard let entry = catalogEntry(trait) else {
            return HadesPresentation.text("hades.kind.special", language: language)
        }
        let source = entry.source(language: language.rawValue)
        if !source.isEmpty { return source }
        return HadesPresentation.text("hades.kind.\(entry.kind)", language: language)
    }

    private var matches: [HadesCurrentTrait] {
        let words = search.lowercased().split(whereSeparator: \.isWhitespace)
        let rows = words.isEmpty ? model.traits : model.traits.filter { trait in
            var searchable = [trait.name]
            for language in TrainerPresentationLanguage.allCases {
                searchable.append(model.traitName(trait, language: language))
                searchable.append(sourceLabel(trait, language: language))
            }
            let haystack = searchable.joined(separator: " ").lowercased()
            return words.allSatisfy { haystack.contains($0) }
        }
        return rows.sorted {
            let leftSource = sourceLabel($0, language: localization.language)
            let rightSource = sourceLabel($1, language: localization.language)
            if leftSource != rightSource {
                return leftSource.localizedStandardCompare(rightSource) == .orderedAscending
            }
            return model.traitName($0, language: localization.language)
                .localizedStandardCompare(model.traitName($1, language: localization.language))
                == .orderedAscending
        }
    }

    private var pickerSections: [TrainerPickerSection<HadesCurrentTrait>] {
        var titles: [String] = []
        var buckets: [String: [HadesCurrentTrait]] = [:]
        for trait in matches {
            let title = sourceLabel(trait, language: localization.language)
            if buckets[title] == nil {
                titles.append(title)
                buckets[title] = []
            }
            buckets[title, default: []].append(trait)
        }
        return titles.enumerated().map { index, title in
            TrainerPickerSection(id: index, title: title, items: buckets[title] ?? [])
        }
    }

    private var selected: HadesCurrentTrait? {
        matches.first { $0.instanceId == selection }
    }

    private func pickerLabel(_ trait: HadesCurrentTrait) -> String {
        [
            model.traitName(trait, language: localization.language),
            text("hades.level") + " " + String(trait.level),
            text("hades.rarity.\(trait.rarity)"),
        ].joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: TrainerTraitManagerLayout.rowSpacing) {
                Label(text("hades.currentTraits"), systemImage: TrainerSemanticIcon.Concept.controls)
                    .font(.subheadline.weight(.medium))
                    .fixedSize()

                Picker(text("hades.currentTraits"), selection: $selection) {
                    if pickerSections.allSatisfy({ $0.items.isEmpty }) {
                        Text(text("hades.emptyTraits")).tag("")
                    }
                    ForEach(pickerSections) { section in
                        Section(header: Text(section.title)) {
                            ForEach(section.items) { trait in
                                Text(pickerLabel(trait)).tag(trait.instanceId)
                            }
                        }
                    }
                }
                .labelsHidden()
                .trainerPicker(.expanding, state: pickerSections.allSatisfy({ $0.items.isEmpty }) ? .unavailable : .interactive)

                TrainerSearchField(
                    text: $search,
                    placeholder: text("hades.search"),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(width: TrainerTraitManagerLayout.searchWidth)
            }

            if let selected {
                HadesCurrentTraitRow(model: model, trait: selected)
                    .id(selected.instanceId)
            } else {
                HadesCurrentTraitPlaceholderRow()
            }
        }
        .trainerPanel()
        .onChange(of: matches.map(\.instanceId), initial: true) { _, ids in
            guard !ids.contains(selection) else { return }
            let replacement = matches.first { $0.name == selectedTraitName } ?? matches.first
            selection = replacement?.instanceId ?? ""
        }
        .onChange(of: selection, initial: true) { _, identifier in
            if let trait = matches.first(where: { $0.instanceId == identifier }) {
                selectedTraitName = trait.name
            }
        }
    }
}

private struct HadesCurrentTraitPlaceholderRow: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme

    private func text(_ key: String) -> String {
        HadesPresentation.text(key, language: localization.language)
    }

    var body: some View {
        HStack(spacing: TrainerTraitManagerLayout.rowSpacing) {
            HStack(spacing: 6) {
                Text(text("hades.level"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(width: 42, alignment: .trailing)
                TrainerNumberField(
                    text: .constant(""),
                    accessibilityLabel: text("hades.level"),
                    width: 58,
                    enabled: false,
                    onCommit: { $0.text }
                )
                TrainerSecondaryActionButton(
                    title: text("hades.setLevel"),
                    systemImage: TrainerSemanticIcon.Action.apply,
                    enabled: false,
                    widthRole: .compactRow,
                    action: {}
                )
            }
            .frame(
                width: TrainerTraitManagerLayout.levelControlsWidth(
                    compactActionWidth: theme.compactActionWidth
                ),
                alignment: .trailing
            )

            HStack(spacing: 6) {
                Text(text("hades.rarity"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(width: 48, alignment: .trailing)
                Picker(text("hades.rarity"), selection: .constant("")) {
                    Text("—").tag("")
                }
                .labelsHidden()
                .trainerPicker(.compactValue, state: .unavailable)
                TrainerSecondaryActionButton(
                    title: text("hades.setRarity"),
                    systemImage: TrainerSemanticIcon.Action.apply,
                    enabled: false,
                    widthRole: .compactRow,
                    action: {}
                )
            }
            .frame(
                width: TrainerTraitManagerLayout.rarityControlsWidth(
                    compactActionWidth: theme.compactActionWidth,
                    pickerWidth: theme.pickerCompactWidth
                ),
                alignment: .trailing
            )

            Button(role: .destructive) {
            } label: {
                Label(text("hades.remove"), systemImage: TrainerSemanticIcon.Action.remove)
            }
            .buttonStyle(.bordered)
            .frame(width: TrainerTraitManagerLayout.removeControlWidth)
            .disabled(true)
        }
        .frame(
            width: TrainerTraitManagerLayout.commonControlsWidth(
                compactActionWidth: theme.compactActionWidth,
                pickerWidth: theme.pickerCompactWidth
            ),
            alignment: .trailing
        )
        .frame(maxWidth: .infinity, alignment: .trailing)
    }
}

private struct HadesCurrentTraitRow: View {
    @ObservedObject var model: HadesTrainerModel
    let trait: HadesCurrentTrait
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var rarity: String
    @State private var level: String
    @State private var owner: HadesHeroTarget?

    private var entry: HadesCatalogEntry? { model.catalog.first { $0.id == trait.name } }
    private var rarities: [String] { entry?.rarities ?? [trait.rarity] }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    init(model: HadesTrainerModel, trait: HadesCurrentTrait) {
        self.model = model
        self.trait = trait
        _rarity = State(initialValue: trait.rarity)
        _level = State(initialValue: String(trait.level))
        _owner = State(initialValue: model.target)
    }

    private var canApplyLevel: Bool {
        guard model.canMutate, trait.canEdit, entry?.supportsLevel != false,
              let amount = Int(level), (1...100).contains(amount) else { return false }
        return amount != trait.level
    }

    private var canApplyRarity: Bool {
        model.canMutate && trait.canEdit && rarities.contains(rarity) && rarity != trait.rarity
    }

    private var removalLabel: String {
        if trait.canExpire == true && trait.blessing != nil {
            return text("hades.cancelCurse")
        }
        if entry?.kind == "temporary" {
            return text("hades.cancelTemporaryEffect")
        }
        if trait.level > 1 {
            let prefix = text("hades.removeAllMatching")
            let name = model.traitName(trait, language: localization.language)
            return localization.language == .zhCN ? prefix + name : prefix + " " + name
        }
        return text("hades.remove")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: TrainerTraitManagerLayout.rowSpacing) {
                HStack(spacing: 6) {
                    Text(text("hades.level"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .frame(width: 42, alignment: .trailing)
                    TrainerNumberField(
                        text: $level,
                        accessibilityLabel: text("hades.level"),
                        accessibilityIdentifier: "hades.currentTrait.level",
                        width: 58,
                        enabled: model.canMutate && trait.canEdit && entry?.supportsLevel != false,
                        onEditingChanged: { active in if active { owner = model.target } },
                        onCommit: { completion in
                            guard let amount = Int(completion.text), (1...100).contains(amount) else {
                                return completion.rejected(message: text("hades.error.invalidValue"))
                            }
                            return String(amount)
                        }
                    )
                    TrainerSecondaryActionButton(
                        title: text("hades.setLevel"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: canApplyLevel,
                        widthRole: .compactRow
                    ) {
                        guard let amount = Int(level), (1...100).contains(amount) else {
                            model.rejectInvalidValue()
                            return
                        }
                        model.updateTrait(trait, rarity: trait.rarity, level: amount, target: owner)
                    }
                }
                .frame(
                    width: TrainerTraitManagerLayout.levelControlsWidth(
                        compactActionWidth: theme.compactActionWidth
                    ),
                    alignment: .trailing
                )

                HStack(spacing: 6) {
                    Text(text("hades.rarity"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .frame(width: 48, alignment: .trailing)
                    Picker(text("hades.rarity"), selection: $rarity) {
                        ForEach(rarities, id: \.self) {
                            Text(text("hades.rarity.\($0)")).tag($0)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.compactValue,
                        state: model.canMutate && trait.canEdit ? .interactive : .unavailable)

                    TrainerSecondaryActionButton(
                        title: text("hades.setRarity"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: canApplyRarity,
                        widthRole: .compactRow
                    ) {
                        model.updateTrait(trait, rarity: rarity, level: trait.level, target: owner)
                    }
                }
                .frame(
                    width: TrainerTraitManagerLayout.rarityControlsWidth(
                        compactActionWidth: theme.compactActionWidth,
                        pickerWidth: theme.pickerCompactWidth
                    ),
                    alignment: .trailing
                )

                Button(role: .destructive) {
                    model.removeTrait(trait)
                } label: {
                    Label {
                        Text(removalLabel)
                            .lineLimit(2)
                            .minimumScaleFactor(0.85)
                            .frame(maxWidth: .infinity)
                    } icon: {
                        Image(systemName: TrainerSemanticIcon.Action.remove)
                    }
                }
                .buttonStyle(.bordered)
                .frame(width: TrainerTraitManagerLayout.removeControlWidth)
                .disabled(!model.canMutate || !trait.canRemove)
            }
            .frame(
                width: TrainerTraitManagerLayout.commonControlsWidth(
                    compactActionWidth: theme.compactActionWidth,
                    pickerWidth: theme.pickerCompactWidth
                ),
                alignment: .trailing
            )
            .frame(maxWidth: .infinity, alignment: .trailing)

            if !trait.canEdit && !trait.limitation.isEmpty {
                Text(text("hades.limitation.\(trait.limitation)"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if trait.hasContextualControls {
                HadesEffectLifecycleControls(model: model, trait: trait)
            }
        }
        .onChange(of: trait) { old, updated in
            if rarity == old.rarity { rarity = updated.rarity }
            if level == String(old.level) { level = String(updated.level) }
            owner = model.target
        }
        .onChange(of: model.target) { _, target in
            if rarity == trait.rarity && level == String(trait.level) { owner = target }
        }
    }
}

private struct HadesShortcutSettingsView: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        TrainerShortcutSettingsView(
            isPresented: $model.shortcutSettingsPresented,
            entries: HadesWorkbenchCatalog.orderedShortcutActions.map { action in
                TrainerShortcutSettingsEntry(
                    id: action.rawValue,
                    title: localization.string(action.key),
                    icon: action.icon,
                    chordText: model.shortcutText(action),
                    isEditable: action != .disableAll
                )
            },
            registrationFailure: model.shortcutRegistrationFailure,
            resetTitle: localization.string("hades.reset"),
            onReset: model.resetShortcuts,
            onAssign: { actionID, chord in
                guard let action = HadesShortcutAction(rawValue: actionID) else {
                    return .rejected(messageKey: "host.hotkeys.unrecognized")
                }
                return model.setShortcut(action, chord: chord)
            }
        )
    }
}

struct HadesManagementCommands: Commands {
    @ObservedObject var model: HadesTrainerModel
    @ObservedObject var localization: TrainerLocalizationStore
    var body: some Commands {
        TrainerManagementCommandMenu(title: localization.localized("host.trainerMenu"),
            groups: HadesManagementCatalog.make(model: model, localization: localization).groups)
    }
}
