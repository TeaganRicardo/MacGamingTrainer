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
    @State private var gameSpeedInput = "1.0"
    @State private var gameSpeedPreview: Double?
    @State private var gameSpeedEditing = false

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    private var error: String { model.localError.isEmpty ? model.backendStatus.error : model.localError }

    private func state(_ feature: HadesFeature) -> TrainerFeatureControlState {
        let enabled = model.isEnabled(feature)
        let active = model.isActive(feature)
        let detached = enabled && !model.connected
        return TrainerFeatureControlState(
            isOn: enabled,
            isInteractive: model.canEditIntent,
            canEditValue: model.canEditIntent,
            opacity: 1,
            indicatorColor: detached ? theme.warning : (active ? theme.accent : theme.inactive),
            helpText: detached ? text("hades.phase.detached") : text(feature.helpKey),
            isWarning: enabled && !active
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
                    HadesVitalMetricCard(model: model)
                    HadesAmountMetricCard(model: model, title: text("hades.money"), icon: TrainerSemanticIcon.Concept.currency,
                                          value: model.money, field: "money")
                    HadesAmountMetricCard(model: model, title: text("hades.rerolls"), icon: TrainerSemanticIcon.Concept.randomize,
                                          value: model.rerolls, field: "rerolls")
                    HadesAmountMetricCard(model: model, title: text("hades.godGauge"), icon: HadesWorkbenchIcon.godGauge,
                                          value: model.godGauge, field: "godGauge")
                }
                TrainerDisclosure(isExpanded: model.numericControlsExpanded) {
                    TrainerMetricGrid {
                        ForEach(HadesFeature.allCases.filter { !$0.isToggle && $0 != .gameSpeed }) { feature in
                            HadesFeatureMetricCard(model: model, feature: feature)
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
                icon: TrainerSemanticIcon.Concept.timeScale,
                tint: model.canEditIntent ? theme.accent : theme.inactive,
                emphasized: model.canEditIntent,
                helpText: localization.localized("host.timeWarp.hint")
            ) {
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: "1.0",
                    accessibilityLabel: localization.localized("host.timeWarp.title"),
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
                        accessibilityLabel: localization.localized("host.timeWarp.title"),
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

    private var boonRarityPanel: some View {
        let controlState = state(.boonRarityEnabled)
        return TrainerLabeledControlRow(
            title: text(HadesFeature.boonRarityEnabled.key),
            icon: HadesFeature.boonRarityEnabled.icon,
            tint: controlState.indicatorColor,
            emphasized: controlState.isOn,
            opacity: controlState.opacity
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
            VStack(spacing: 0) {
                ForEach(model.resourceCatalog) { resource in
                    HadesValueRow(
                        model: model,
                        title: resource.name(language: localization.language.rawValue),
                        glyph: HadesResourceIcon.glyph(for: resource.id), value: model.resources[resource.id] ?? 0
                    ) {
                        model.setResource(resource.id, value: $0, target: $1)
                    }
                    .id(resource.id)
                }
            }
            .trainerGroupedRows()
            HadesGatheringPanel(model: model)
        }
    }

    private var managementSection: some View {
        TrainerSection(title: text(HadesWorkbenchSection.management.titleKey),
                       icon: HadesWorkbenchSection.management.icon) {
            HadesManagementUtilities(model: model)
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
            model.rejectInvalidValue()
            return completion.rejected(message: HadesPresentation.text("hades.error.invalidValue", language: localization.language))
        }
        model.setValue(field, value: number, target: draft.target)
        return HadesNumberDraft.format(number)
    }

    var body: some View {
        TrainerMetricCard(title: title, icon: TrainerSemanticIcon.Concept.vitality, tint: .pink) {
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
    @EnvironmentObject private var localization: TrainerLocalizationStore
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
                        model.rejectInvalidValue()
                        return completed.rejected(message: HadesPresentation.text("hades.error.invalidValue", language: localization.language))
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
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let title: String
    let glyph: TrainerGlyph
    let value: Double
    let onCommit: (Double, HadesHeroTarget?) -> Void
    @Environment(\.trainerTheme) private var theme
    @State private var draft: HadesNumberDraft

    init(model: HadesTrainerModel, title: String, glyph: TrainerGlyph, value: Double,
         onCommit: @escaping (Double, HadesHeroTarget?) -> Void) {
        self.model = model; self.title = title; self.glyph = glyph; self.value = value; self.onCommit = onCommit
        _draft = State(initialValue: HadesNumberDraft(value: value))
    }
    var body: some View {
        TrainerLabeledControlRow(title: title, glyph: glyph, tint: theme.accent, emphasized: model.heroReady) {
            TrainerNumberField(text: Binding(get: { draft.text }, set: { draft.update($0) }), accessibilityLabel: title,
                enabled: model.canMutate, onEditingChanged: { active in
                    if active { draft.begin(target: model.target) } else { draft.end() }
                }, onCommit: { completed in
                    guard completed.changed else { return completed.text }
                    guard let number = Double(completed.text), number.isFinite, number.rounded() == number,
                          number >= 0, number <= 1_000_000_000 else {
                        model.rejectInvalidValue()
                        return completed.rejected(message: HadesPresentation.text("hades.error.invalidValue", language: localization.language))
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
                        guard completed.changed else { return completed.text }
                        return model.setNumber(feature, text: completed.text) { key in
                            _ = completed.rejected(message: HadesPresentation.text(key, language: localization.language))
                        }
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
