import Foundation
import SwiftUI
import AppKit
import TrainerCore

struct Hades2TrainerView: View {
    private enum EditField: Hashable {
        case healthCurrent, healthMax, manaCurrent, manaMax, armorCurrent, spellCharge, biomeTime
        case coins, material, rerolls, damageMultiplier, moneyMultiplier, resourceMultiplier, gameSpeed
        case grasp, dodge, crit, chargeSpeed, moveSpeed, sprintSpeed, dashSpeed, attackSpeed, manaRegen, enemyDamage, enemyHealth
        case traitRemainingUses
        case element(String)
    }

    private struct ExactBoonSourceGroup: Identifiable {
        let id: String
        let title: String
        let items: [BoonOption]
    }

    private static let defaultDrafts: [EditField: String] = [
        .damageMultiplier: String(format: "%g", Hades2MultiplierKey.damageMultiplier.defaultValue),
        .moneyMultiplier: String(format: "%g", Hades2MultiplierKey.moneyMultiplier.defaultValue),
        .resourceMultiplier: String(format: "%g", Hades2MultiplierKey.resourceMultiplier.defaultValue),
        .gameSpeed: String(Hades2MultiplierKey.gameSpeed.defaultValue),
        .enemyDamage: "100",
        .enemyHealth: "100",
    ]

    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerToolWindows) private var toolWindows
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var focusedField: EditField?
    @State private var drafts = TrainerObservedDrafts<EditField>(Self.defaultDrafts)

    private var accent: Color { theme.accent }
    @State private var vitalsInitialized = false
    @State private var coinsInitialized = false
    @State private var selectedMaterial = ""
    @State private var search = ""
    @State private var gameSpeedPreview: String?
    @State private var rerollsInitialized = false
    @State private var exactSearch = ""
    @State private var exactSourceSelection = ""
    @State private var traitSearch = ""
    @State private var managedTraitSelection = ""
    @State private var traitLevelInputs: [String: String] = [:]
    @State private var traitRarityInputs: [String: String] = [:]
    @State private var statsInitialized = false
    @State private var elementsInitialized = false

    private func draft(_ field: EditField) -> Binding<String> {
        $drafts.binding(field)
    }

    private var gameSpeedInput: String {
        get { drafts[.gameSpeed] }
        nonmutating set { drafts[.gameSpeed] = newValue }
    }

    private var filtered: [MaterialResource] {
        model.resources.filter { $0.id != "Money" && (search.isEmpty || $0.name.localizedCaseInsensitiveContains(search) || $0.englishName.localizedCaseInsensitiveContains(search) || $0.id.localizedCaseInsensitiveContains(search)) }
    }

    private func sortedBoons(_ options: [BoonOption]) -> [BoonOption] {
        options.sorted {
            if $0.sortSection != $1.sortSection { return $0.sortSection < $1.sortSection }
            if $0.sortGroup != $1.sortGroup { return $0.sortGroup < $1.sortGroup }
            if $0.sortOrder != $1.sortOrder { return $0.sortOrder < $1.sortOrder }
            return $0.id < $1.id
        }
    }

    private var olympianBoons: [BoonOption] { sortedBoons(model.boons.filter { $0.group == "olympian" }) }
    private var pickupRewards: [BoonOption] { sortedBoons(model.boons.filter { $0.group == "pickup" }) }
    private var specialBoons: [BoonOption] { sortedBoons(model.specialRewardOptions) }
    private var chaosBlessingOptions: [BoonOption] {
        sortedBoons(model.exactBoonOptions.filter { $0.acquisitionMode == "chaosBlessing" })
    }

    private var chaosCurseOptions: [BoonOption] {
        sortedBoons(model.exactBoonOptions.filter { $0.acquisitionMode == "chaosCurse" })
    }

    private var genericExactCatalog: [BoonOption] {
        sortedBoons(model.exactBoonOptions.filter { option in
            option.acquisitionMode != "chaosBlessing"
                && option.acquisitionMode != "chaosCurse"
        })
    }

    private var genericExactBoons: [BoonOption] {
        genericExactCatalog.filter { option in
            exactSearch.isEmpty
                || option.name.localizedCaseInsensitiveContains(exactSearch)
                || option.englishName.localizedCaseInsensitiveContains(exactSearch)
                || option.targetID.localizedCaseInsensitiveContains(exactSearch)
                || option.id.localizedCaseInsensitiveContains(exactSearch)
                || option.sourceId.localizedCaseInsensitiveContains(exactSearch)
                || option.sourceName.localizedCaseInsensitiveContains(exactSearch)
                || option.sourceEnglishName.localizedCaseInsensitiveContains(exactSearch)
                || option.sectionTitle.localizedCaseInsensitiveContains(exactSearch)
                || option.englishSectionTitle.localizedCaseInsensitiveContains(exactSearch)
                || option.category.localizedCaseInsensitiveContains(exactSearch)
                || option.englishCategory.localizedCaseInsensitiveContains(exactSearch)
        }
    }
    private var material: MaterialResource? { filtered.first { $0.id == selectedMaterial } }

    private func resourceGroups(_ options: [MaterialResource]) -> [TrainerPickerSection<MaterialResource>] {
        var titles: [String] = []
        var buckets: [String: [MaterialResource]] = [:]
        for item in options.sorted(by: { $0.sortOrder < $1.sortOrder }) {
            let localizedSection = localization.language == .en ? item.englishSectionTitle : item.sectionTitle
            let title = localizedSection.isEmpty ? text("hades2.resource.sectionDefault") : localizedSection
            if buckets[title] == nil { titles.append(title); buckets[title] = [] }
            buckets[title, default: []].append(item)
        }
        return titles.enumerated().map { index, title in
            TrainerPickerSection(id: index, title: title, items: buckets[title] ?? [])
        }
    }

    private func boonGroups(_ options: [BoonOption]) -> [TrainerPickerSection<BoonOption>] {
        var titles: [String] = []
        var buckets: [String: [BoonOption]] = [:]
        for item in options {
            // An empty sectionTitle means the backend did not label this group,
            // so fall back to the module's table rather than showing a blank
            // heading; the raw category is the last resort.
            let title: String
            let localizedSection = localization.language == .en ? item.englishSectionTitle : item.sectionTitle
            let localizedCategory = localization.language == .en ? item.englishCategory : item.category
            if !localizedSection.isEmpty {
                title = localizedSection
            } else if !localizedCategory.isEmpty {
                title = localizedCategory
            } else {
                title = text("hades2.spawn.characterRewards")
            }
            if buckets[title] == nil { titles.append(title); buckets[title] = [] }
            buckets[title, default: []].append(item)
        }
        return titles.enumerated().map { index, title in
            TrainerPickerSection(id: index, title: title, items: buckets[title] ?? [])
        }
    }

    private func exactSourceGroupID(_ option: BoonOption) -> String {
        // Stable machine identity only: localized titles and item names never
        // participate in source selection, so language changes and same-name
        // effects cannot move the user's selection.
        "\(option.sourceId)|\(option.acquisitionMode)|\(option.sortGroup)"
    }

    private func exactSourceTitle(_ option: BoonOption) -> String {
        let section = localization.language == .en ? option.englishSectionTitle : option.sectionTitle
        if !section.isEmpty { return section }
        let source = localization.language == .en ? option.sourceEnglishName : option.sourceName
        if !source.isEmpty { return source }
        let category = localization.language == .en ? option.englishCategory : option.category
        return category.isEmpty ? text("hades2.spawn.exactBoons") : category
    }

    private var exactBoonSourceGroups: [ExactBoonSourceGroup] {
        var order: [String] = []
        var titles: [String: String] = [:]
        var buckets: [String: [BoonOption]] = [:]
        for option in genericExactBoons {
            let sourceID = exactSourceGroupID(option)
            if buckets[sourceID] == nil {
                order.append(sourceID)
                titles[sourceID] = exactSourceTitle(option)
                buckets[sourceID] = []
            }
            buckets[sourceID, default: []].append(option)
        }
        return order.map { sourceID in
            ExactBoonSourceGroup(
                id: sourceID,
                title: titles[sourceID] ?? text("hades2.spawn.exactBoons"),
                items: buckets[sourceID] ?? []
            )
        }
    }

    private var selectedExactSourceGroup: ExactBoonSourceGroup? {
        exactBoonSourceGroups.first { $0.id == exactSourceSelection }
    }

    private var selectedExactItems: [BoonOption] {
        selectedExactSourceGroup?.items ?? []
    }

    private var exactItemSelection: Binding<String> {
        Binding(
            get: {
                guard selectedExactItems.contains(where: { $0.id == model.selectedExactBoon }) else {
                    return ""
                }
                return model.selectedExactBoon
            },
            set: { itemID in
                guard !itemID.isEmpty,
                      selectedExactItems.contains(where: { $0.id == itemID }) else { return }
                model.selectedExactBoon = itemID
            }
        )
    }

    private func selectExactSource(_ sourceID: String) {
        guard let source = exactBoonSourceGroups.first(where: { $0.id == sourceID }) else { return }
        exactSourceSelection = sourceID
        if !source.items.contains(where: { $0.id == model.selectedExactBoon }) {
            model.selectedExactBoon = ""
        }
    }

    private func repairExactSourceSelection() {
        let groups = exactBoonSourceGroups
        guard !groups.isEmpty else { return }

        let selectedGroup = groups.first(where: { group in
            group.items.contains(where: { $0.id == model.selectedExactBoon })
        })
        if exactSearch.isEmpty, let selectedGroup {
            exactSourceSelection = selectedGroup.id
            return
        }
        if groups.contains(where: { $0.id == exactSourceSelection }) { return }
        exactSourceSelection = selectedGroup?.id ?? groups[0].id
    }

    private func repairChaosPairSelections() {
        if !chaosBlessingOptions.contains(where: { $0.id == model.selectedChaosBlessing }) {
            model.selectedChaosBlessing = chaosBlessingOptions.first?.id ?? ""
        }
        if !chaosCurseOptions.contains(where: { $0.id == model.selectedChaosCurse }) {
            model.selectedChaosCurse = chaosCurseOptions.first?.id ?? ""
        }
    }

    /// Resolve one presentation key against the live Host language.
    private func text(_ key: String) -> String {
        localization.string(key)
    }

    /// Resolve a presentation token through the Host localization store.
    private func resolved(_ token: TrainerTextToken) -> String {
        localization.string(token)
    }

    /// Next-room reward label in the active language. Each key resolves both
    /// languages from the same shipped table, so no name is invented here.
    private func rewardLabel(_ rewardID: String) -> String {
        text("hades2.reward.\(rewardID)")
    }

    /// Element metric title. Prefer the registry's localized element name; fall
    /// back to the backend-supplied official name when an id is unknown.
    private func elementLabel(_ element: ElementCount) -> String {
        let key = "hades2.element.\(element.id)"
        // Prefer the registry's localized element name; an id the table does not
        // know falls back to the official name the backend supplied. The argument
        // is text, not a key, so it is passed as-is.
        let localized = localization.string(key)
        return localization.string(
            "hades2.element.generic",
            arguments: [localized == key ? element.name : localized]
        )
    }

    var body: some View {
        editorGenerationObservedContent
    }

    private var rootContent: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            statusAndSessionSection
            commonSection.trainerSectionTarget(Hades2WorkbenchSection.common.id)
            boonsSection.trainerSectionTarget(Hades2WorkbenchSection.boons.id)
            resourceSection.trainerSectionTarget(Hades2WorkbenchSection.resources.id)
            roomsSection.trainerSectionTarget(Hades2WorkbenchSection.rooms.id)
            management.trainerSectionTarget(Hades2WorkbenchSection.management.id)
        }
    }

    private var statusAndSessionSection: some View {
        TrainerSection(
            title: text("hades2.section.runData"),
            icon: Hades2WorkbenchSection.values.icon
        ) {
            TrainerDisclosureButton(isExpanded: $model.numericControlsExpanded,
                expandTitle: text("hades2.section.expand"), collapseTitle: text("hades2.section.collapse"))
                .accessibilityIdentifier("hades2.numericDisclosure")
        } content: {
            sessionStatsPanel
        }
        .trainerSectionTarget(Hades2WorkbenchSection.values.id)
    }

    private var commonSection: some View {
        TrainerSection(title: text("hades2.section.common"), icon: Hades2WorkbenchSection.common.icon) {
            VStack(spacing: 1) {
                ForEach(Hades2CheatCatalog.commonToggleDefinitions) { definition in
                    if let key = Hades2FeatureKey(rawValue: definition.id) {
                        let enabled = model.isFeatureEnabled(key)
                        let shortcut = ShortcutAction(rawValue: definition.shortcutID ?? definition.id)
                        TrainerCheatToggleRow(
                            definition: definition,
                            state: model.featurePresentation(key, enabled: enabled)
                                .trainerControlState(using: theme, localization: localization),
                            shortcutText: shortcut.map { model.shortcutText($0) }
                        ) {
                            model.feature(key, value: !model.isFeatureEnabled(key))
                        }
                    }
                }
            }
            .trainerGroupedRows()
            gameSpeedPanel
        }
    }

    private var boonsSection: some View {
        TrainerSection(title: text("hades2.section.boonsAndEffects"), icon: Hades2WorkbenchSection.boons.icon) {
            boonRarityPanel
            currentRunEffectsPanel
            boonAcquisitionPanel
            elementPanel
        }
    }

    /// Resolve a Hades key with runtime arguments against the live Host
    /// language. An argument is runtime text unless it is another owned key.
    private func text(_ key: String, arguments: [String]) -> String {
        localization.string(key, arguments: arguments)
    }

    private func currentRunTraitName(_ trait: CurrentRunTrait) -> String {
        localization.language == .en ? trait.englishName : trait.displayName
    }

    private var filteredCurrentRunTraits: [CurrentRunTrait] {
        let rows = traitSearch.isEmpty ? model.currentRunTraits : model.currentRunTraits.filter { trait in
            [
                trait.displayName, trait.englishName,
                trait.linkedDisplayName, trait.linkedEnglishName,
                trait.sourceName, trait.sourceEnglishName,
            ].contains { $0.localizedCaseInsensitiveContains(traitSearch) }
        }
        return rows.sorted {
            let leftSource = traitSourceLabel($0)
            let rightSource = traitSourceLabel($1)
            if leftSource != rightSource {
                return leftSource.localizedStandardCompare(rightSource) == .orderedAscending
            }
            return currentRunTraitName($0).localizedStandardCompare(currentRunTraitName($1)) == .orderedAscending
        }
    }

    private func traitRarityLabel(_ rarity: String) -> String {
        let key = "hades2.rarity." + rarity
        let localized = text(key)
        return localized == key ? rarity : localized
    }

    private func traitSourceLabel(_ trait: CurrentRunTrait) -> String {
        let presentationKey = "hades2.traits.family.\(trait.family)"
        let localizedFamily = text(presentationKey)

        // Arcana cards are one player-facing system. The exact card owner is
        // carried by the item label; using each card name as a section heading
        // fragments one deck into dozens of one-item groups.
        if trait.family == "arcana" {
            return localizedFamily == presentationKey ? trait.family : localizedFamily
        }

        if !trait.sourceID.isEmpty {
            let label = localization.language == .en ? trait.sourceEnglishName : trait.sourceName
            if !label.isEmpty { return label }
        }
        return localizedFamily == presentationKey ? trait.family : localizedFamily
    }

    private var currentRunTraitPickerSections: [TrainerPickerSection<CurrentRunTrait>] {
        var titles: [String] = []
        var buckets: [String: [CurrentRunTrait]] = [:]
        for trait in filteredCurrentRunTraits {
            let title = traitSourceLabel(trait)
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

    private var managedCurrentRunTrait: CurrentRunTrait? {
        model.currentRunTraits.first { $0.id == managedTraitSelection }
    }

    private func currentRunTraitPickerLabel(_ trait: CurrentRunTrait) -> String {
        var parts = [currentRunTraitName(trait), text("hades2.traits.level", arguments: [String(trait.level)])]
        if !trait.rarity.isEmpty {
            parts.append(traitRarityLabel(trait.rarity))
        }
        if trait.sameNameCount > 1 {
            parts.append(text("hades2.traits.instances", arguments: [String(trait.sameNameCount)]))
        }
        return parts.joined(separator: " · ")
    }

    private func repairManagedTraitSelection() {
        let available = filteredCurrentRunTraits
        guard !available.contains(where: { $0.id == managedTraitSelection }) else { return }
        managedTraitSelection = available.first?.id ?? ""
    }

    private func traitLevelInput(_ trait: CurrentRunTrait) -> Binding<String> {
        Binding(
            get: {
                traitLevelInputs[trait.id]
                    ?? String(trait.canIncreaseLevel ? trait.level + 1 : trait.level)
            },
            set: { traitLevelInputs[trait.id] = $0 }
        )
    }

    private func defaultTraitRarityInput(_ trait: CurrentRunTrait) -> String {
        guard !trait.availableRarities.isEmpty else { return "" }
        guard !trait.rarity.isEmpty else { return trait.availableRarities[0] }
        guard let index = trait.availableRarities.firstIndex(of: trait.rarity) else {
            return trait.availableRarities[0]
        }
        guard trait.availableRarities.indices.contains(index + 1) else {
            return trait.rarity
        }
        return trait.availableRarities[index + 1]
    }

    private func traitRarityInput(_ trait: CurrentRunTrait) -> Binding<String> {
        Binding(
            get: {
                if let draft = traitRarityInputs[trait.id], trait.availableRarities.contains(draft) {
                    return draft
                }
                return defaultTraitRarityInput(trait)
            },
            set: { traitRarityInputs[trait.id] = $0 }
        )
    }

    private func renderedTraitRemainingUses(_ trait: CurrentRunTrait) -> String {
        guard let uses = trait.remainingUses else { return "" }
        return uses.rounded() == uses ? String(Int(uses)) : String(format: "%.1f", uses)
    }

    private func syncManagedTraitRemainingUsesInput(force: Bool = false) {
        let next = managedCurrentRunTrait.map(renderedTraitRemainingUses) ?? ""
        drafts.observe(.traitRemainingUses, value: next, focused: focusedField, force: force)
    }

    private func canApplyTraitRemainingUses(_ trait: CurrentRunTrait) -> Bool {
        guard model.canMutateTraits, trait.canSetRemainingUses,
              let target = Int(drafts[.traitRemainingUses].trimmingCharacters(in: .whitespacesAndNewlines)),
              (1...999_999).contains(target) else { return false }
        return trait.remainingUses != Double(target)
    }

    private func canApplyTraitLevel(_ trait: CurrentRunTrait) -> Bool {
        guard model.canMutateTraits, trait.canIncreaseLevel,
              let target = Int(traitLevelInput(trait).wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines))
        else { return false }
        return target > trait.level && target <= 999_999
    }

    private func canApplyTraitRarity(_ trait: CurrentRunTrait) -> Bool {
        let target = traitRarityInput(trait).wrappedValue
        return model.canMutateTraits
            && trait.canSetRarity
            && trait.availableRarities.contains(target)
            && target != trait.rarity
    }

    private var currentRunTraitsPanel: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            HStack(spacing: TrainerManagedRowLayout.rowSpacing) {
                TrainerIconLabel(
                    title: text("hades2.traits.manager"),
                    icon: TrainerSemanticIcon.Concept.controls,
                    tint: model.canMutateTraits ? theme.accent : theme.inactive,
                    emphasized: model.canMutateTraits
                )
                .fixedSize()

                Picker(text("hades2.traits.manager"), selection: $managedTraitSelection) {
                    if currentRunTraitPickerSections.allSatisfy({ $0.items.isEmpty }) {
                        Text(text("hades2.traits.empty")).tag("")
                    }
                    ForEach(currentRunTraitPickerSections) { section in
                        Section(header: Text(section.title)) {
                            ForEach(section.items) { trait in
                                Text(currentRunTraitPickerLabel(trait)).tag(trait.id)
                            }
                        }
                    }
                }
                .labelsHidden()
                .trainerPicker(.expanding, state: currentRunTraitPickerSections.allSatisfy({ $0.items.isEmpty }) ? .unavailable : .interactive)

                TrainerSearchField(
                    text: $traitSearch,
                    placeholder: text("hades2.traits.search"),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(width: TrainerManagedRowLayout.searchWidth)
            }

            VStack(alignment: .leading, spacing: 8) {
                currentRunTraitCommonControls(managedCurrentRunTrait)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                if let trait = managedCurrentRunTrait, trait.hasContextualControls {
                    currentRunTraitContextualControls(trait)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
        .onAppear {
            repairManagedTraitSelection()
            syncManagedTraitRemainingUsesInput(force: true)
        }
        .onChange(of: model.currentRunTraits) { _, _ in
            repairManagedTraitSelection()
            syncManagedTraitRemainingUsesInput()
        }
        .onChange(of: traitSearch) { _, _ in
            repairManagedTraitSelection()
            syncManagedTraitRemainingUsesInput(force: true)
        }
        .onChange(of: managedTraitSelection) { _, _ in
            syncManagedTraitRemainingUsesInput(force: true)
        }
    }

    @ViewBuilder
    private func currentRunTraitContextualControls(_ trait: CurrentRunTrait) -> some View {
        if trait.hasTemporaryContextualControls {
            HStack(spacing: 6) {
                Text(text("hades2.traits.remainingUses"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                TrainerNumberField(
                    text: draft(.traitRemainingUses),
                    placeholder: "—",
                    accessibilityLabel: text("hades2.traits.remainingUses"),
                    width: theme.inlineFieldWidth,
                    enabled: model.canMutateTraits && trait.canSetRemainingUses,
                    onEditingChanged: tracking(.traitRemainingUses),
                    onCommit: { completion in
                        guard completion.changed else { return completion.text }
                        let raw = completion.text.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard let uses = Int(raw), (1...999_999).contains(uses) else {
                            return completion.rejected(message: text("hades2.input.invalid"))
                        }
                        return String(uses)
                    }
                )
                .id(trait.id)

                TrainerSecondaryActionButton(
                    title: text("hades2.traits.apply"),
                    enabled: canApplyTraitRemainingUses(trait),
                    widthRole: .compactRow
                ) {
                    model.setTraitRemainingUses(
                        trait,
                        targetRemainingUses: drafts[.traitRemainingUses]
                    )
                }

                TrainerSecondaryActionButton(
                    title: text("hades2.traits.expireNow"),
                    enabled: model.canMutateTraits && trait.canExpire,
                    widthRole: .compactRow
                ) {
                    model.expireTrait(trait)
                }
            }
        } else if trait.canAdvanceLifecycle {
            TrainerSecondaryActionButton(
                title: text("hades2.traits.chaos.advance"),
                enabled: model.canMutateTraits,
                widthRole: .compactRow
            ) {
                model.advanceTraitLifecycle(trait)
            }
        }
    }

    private func currentRunTraitRemovalLabel(_ trait: CurrentRunTrait?) -> String {
        guard let trait else { return text("hades2.traits.remove") }
        if trait.lifecycleState == "curse" {
            return text("hades2.traits.chaos.cancelPair")
        }
        if trait.family == "temporary" {
            return text("hades2.traits.temporary.cancel")
        }
        if trait.removalScopeAllMatching {
            return text("hades2.traits.removeAllMatching", arguments: [currentRunTraitName(trait)])
        }
        return text("hades2.traits.remove")
    }

    private func currentRunTraitCommonControls(_ trait: CurrentRunTrait?) -> some View {
        HStack(spacing: TrainerManagedRowLayout.rowSpacing) {
            HStack(spacing: 6) {
                Text(text("hades2.traits.levelLabel"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(width: 42, alignment: .trailing)

                if let trait {
                    TrainerNumberField(
                        text: traitLevelInput(trait),
                        placeholder: "—",
                        accessibilityLabel: text("hades2.traits.targetLevel"),
                        width: theme.compactFieldWidth,
                        enabled: model.canMutateTraits && trait.canIncreaseLevel,
                        onCommit: { completion in
                            guard completion.changed else { return completion.text }
                            let raw = completion.text.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard let level = Int(raw), level > trait.level, level <= 999_999 else {
                                return completion.rejected(message: text("hades2.input.invalid"))
                            }
                            return String(level)
                        }
                    )
                    .id(trait.id)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyLevel"),
                        enabled: canApplyTraitLevel(trait),
                        widthRole: .compactRow
                    ) {
                        model.setTraitLevel(trait, targetLevel: traitLevelInput(trait).wrappedValue)
                    }
                } else {
                    TrainerNumberField(
                        text: .constant(""),
                        placeholder: "—",
                        accessibilityLabel: text("hades2.traits.targetLevel"),
                        width: theme.compactFieldWidth,
                        enabled: false
                    )

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyLevel"),
                        enabled: false,
                        widthRole: .compactRow,
                        action: {}
                    )
                }
            }
            .frame(width: TrainerManagedRowLayout.numericAdjustmentWidth(compactActionWidth: theme.compactActionWidth), alignment: .trailing)

            HStack(spacing: 6) {
                Text(text("hades2.traits.targetRarity"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(width: 48, alignment: .trailing)

                if let trait {
                    Picker(text("hades2.traits.targetRarity"), selection: traitRarityInput(trait)) {
                        if trait.availableRarities.isEmpty {
                            Text("—").tag("")
                        } else {
                            ForEach(trait.availableRarities, id: \.self) { rarity in
                                Text(traitRarityLabel(rarity)).tag(rarity)
                            }
                        }
                    }
                    .labelsHidden()
                    .lineLimit(1)
                    .trainerPicker(.compactValue, state: model.canMutateTraits && trait.canSetRarity ? .interactive : .unavailable)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyRarity"),
                        enabled: canApplyTraitRarity(trait),
                        widthRole: .compactRow
                    ) {
                        model.setTraitRarity(trait, rarity: traitRarityInput(trait).wrappedValue)
                    }
                } else {
                    Picker(text("hades2.traits.targetRarity"), selection: .constant("")) {
                        Text("—").tag("")
                    }
                    .labelsHidden()
                    .lineLimit(1)
                    .trainerPicker(.compactValue, state: .unavailable)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyRarity"),
                        enabled: false,
                        widthRole: .compactRow,
                        action: {}
                    )
                }
            }
            .frame(width: TrainerManagedRowLayout.pickerAdjustmentWidth(compactActionWidth: theme.compactActionWidth, pickerWidth: theme.pickerCompactWidth), alignment: .trailing)

            Button(role: .destructive) {
                guard let trait else { return }
                model.removeTrait(trait)
            } label: {
                Label {
                    Text(currentRunTraitRemovalLabel(trait))
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                        .frame(maxWidth: .infinity)
                } icon: {
                    Image(systemName: TrainerSemanticIcon.Action.remove)
                }
            }
            .buttonStyle(.bordered)
            .frame(width: TrainerManagedRowLayout.trailingActionWidth)
            .disabled(trait == nil || !model.canMutateTraits || trait?.canRemove != true)
        }
        .frame(width: TrainerManagedRowLayout.trailingControlsWidth(compactActionWidth: theme.compactActionWidth, pickerWidth: theme.pickerCompactWidth), alignment: .trailing)
    }

    private var resourceSection: some View {
        TrainerSection(title: text("hades2.section.resourcesAndGathering"), icon: Hades2WorkbenchSection.resources.icon) {
            resourcePanel
            Hades2GatheringPanel(model: model)
            TrainerCheatOneShotRow(
                definition: Hades2CheatCatalog.definition(id: "matureGarden")!,
                tint: model.canMatureGarden ? theme.accent : theme.inactive,
                emphasized: model.canMatureGarden
            ) {
                TrainerShortcutBadgeSlot(text: model.shortcutText(.matureGarden))
            } actionButton: {
                TrainerSecondaryActionButton(title: text("hades2.garden.matureNow"),
                    enabled: model.canMatureGarden) {
                    _ = model.matureGarden()
                }
                .help(text(model.canMatureGarden ? "hades2.garden.help" : "hades2.garden.unavailable"))
            }
            .trainerGroupedRows()
        }
    }

    private var roomsSection: some View {
        TrainerSection(title: text("hades2.section.roomsAndRewards"), icon: Hades2WorkbenchSection.rooms.icon) {
            worldExitPanel
            nextOccurrencePanel
            Hades2ChamberFacilityPanel(model: model)
            Hades2ChaosGatePanel(model: model)
            rewardSpawningPanel
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

    private var gameSpeedInputBinding: Binding<String> {
        Binding(
            get: { gameSpeedPreview ?? gameSpeedInput },
            set: {
                gameSpeedPreview = nil
                gameSpeedInput = $0
            }
        )
    }

    private var gameSpeedSliderValue: Binding<Double> {
        Binding(
            get: { Double(gameSpeedInput) ?? model.gameSpeed },
            set: {
                gameSpeedPreview = nil
                gameSpeedInput = speedNumber($0)
                model.setGameSpeed(gameSpeedInput)
            }
        )
    }

    private func speedNumber(_ value: Double) -> String {
        String(format: "%.1f", value)
    }

    private var gameSpeedPanel: some View {
        let definition = Hades2CheatCatalog.definition(id: "gameSpeed")!
        return VStack(alignment: .leading, spacing: 4) {
            TrainerLabeledControlRow(
                title: definition.label.resolve(using: localization),
                icon: definition.icon,
                tint: model.canEditDesired ? theme.accent : theme.inactive,
                emphasized: model.canEditDesired,
                helpText: definition.help?.resolve(using: localization) ?? ""
            ) {
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: String(Hades2MultiplierKey.gameSpeed.defaultValue),
                    accessibilityLabel: text("hades2.gameSpeed.a11y"),
                    width: theme.inlineFieldWidth,
                    enabled: model.canEditDesired && model.featureSupport["gameSpeed"] == true,
                    onEditingChanged: tracking(.gameSpeed),
                    onCommit: completing(.gameSpeed)
                )
                Text("×").foregroundStyle(.secondary)
                TrainerShortcutBadge(text: model.shortcutText(.decreaseGameSpeed))
                TrainerGamePageVisibilityGate { pageVisible in
                    TrainerMappedSlider(
                        value: gameSpeedSliderValue,
                        mapping: gameSpeedMapping,
                        accessibilityLabel: text("hades2.gameSpeed.a11y"),
                        accessibilityHint: text("hades2.gameSpeed.hint"),
                        enabled: model.canEditDesired && pageVisible && model.featureSupport["gameSpeed"] == true,
                        onPreviewValue: { preview in
                            gameSpeedPreview = preview.map(speedNumber)
                            if preview == nil && focusedField != .gameSpeed {
                                gameSpeedInput = speedNumber(model.gameSpeed)
                            }
                        }
                    )
                    .frame(width: 200)
                }
                TrainerShortcutBadge(text: model.shortcutText(.increaseGameSpeed))
            }
            if let actual = model.appliedGameSpeed {
                let key = abs(actual - model.gameSpeed) < 0.000001
                    ? "host.timeWarp.actual" : "host.timeWarp.pending"
                Text(localization.presentation(key, arguments: [speedNumber(actual)]))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.bottom, theme.inlineRowVerticalPadding)
            }
        }
        .trainerGroupedRows()
    }

    private var presentedContent: some View {
        rootContent
            .sheet(isPresented: $model.shortcutSettingsPresented) { Hades2ShortcutSettingsView(model: model) }
            .sheet(isPresented: $model.profilesPresented) { Hades2ProfileManagerView(model: model, isPresented: $model.profilesPresented) }
            .sheet(isPresented: $model.diagnosticsPresented) { Hades2DiagnosticsView(model: model, isPresented: $model.diagnosticsPresented) }
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

    private var connectionSnapshot: Hades2ViewConnectionSnapshot {
        Hades2ViewConnectionSnapshot(
            connected: model.connected,
            money: model.money,
            rerolls: model.rerolls,
            health: model.health,
            maxHealth: model.maxHealth,
            mana: model.mana,
            maxMana: model.maxMana,
            armor: model.armor,
            spellCharge: model.spellCharge,
            biomeTime: model.biomeTime
        )
    }

    private var statSnapshot: Hades2ViewStatSnapshot {
        Hades2ViewStatSnapshot(
            grasp: model.graspValue,
            dodge: model.dodgeValue,
            crit: model.critValue,
            chargeSpeed: model.chargeSpeedValue,
            moveSpeed: model.moveSpeedValue,
            sprintSpeed: model.sprintSpeedValue,
            dashSpeed: model.dashSpeedValue,
            attackSpeed: model.attackSpeedValue,
            manaRegen: model.manaRegenValue,
            enemyDamage: model.enemyDamageValue,
            enemyHealth: model.enemyHealthValue
        )
    }

    private var configSnapshot: Hades2ViewConfigSnapshot {
        Hades2ViewConfigSnapshot(
            elements: model.elements,
            damageMultiplier: model.damageMultiplier,
            moneyMultiplier: model.moneyMultiplier,
            resourceMultiplier: model.resourceMultiplier,
            gameSpeed: model.gameSpeed
        )
    }

    private var catalogSnapshot: Hades2ViewCatalogSnapshot {
        Hades2ViewCatalogSnapshot(
            materialID: material?.id,
            materialCount: material?.count,
            occurrenceTargetIDs: model.occurrenceTargets.map(\.id),
            olympianIDs: olympianBoons.map(\.id),
            pickupIDs: pickupRewards.map(\.id),
            specialIDs: specialBoons.map(\.id),
            exactIDs: genericExactCatalog.map(\.id),
            filteredResourceIDs: filtered.map(\.id)
        )
    }

    private var connectionObservedContent: some View {
        presentedContent
            .onChange(of: connectionSnapshot, initial: true) { _, snapshot in
                syncConnectionSnapshot(snapshot)
            }
    }

    private var statObservedContent: some View {
        connectionObservedContent
            .onChange(of: statSnapshot, initial: true) { _, snapshot in
                syncStatSnapshot(snapshot)
            }
    }

    private var gameConfigObservedContent: some View {
        statObservedContent
            .onChange(of: configSnapshot, initial: true) { _, snapshot in
                syncConfigSnapshot(snapshot)
            }
    }

    private var catalogObservedContent: some View {
        gameConfigObservedContent
            .onChange(of: catalogSnapshot, initial: true) { oldValue, newValue in
                applyCatalogChanges(from: oldValue, to: newValue)
            }
    }

    private var editorGenerationObservedContent: some View {
        catalogObservedContent
            .id(model.editGeneration)
            .onChange(of: model.editGeneration) { _, _ in
                rebuildEditorDraftsFromModel()
            }
    }

    private func syncConnectionSnapshot(_ snapshot: Hades2ViewConnectionSnapshot) {
        guard snapshot.connected else {
            resetEditorInputs()
            return
        }

        if let value = snapshot.money {
            drafts.observe(.coins, value: number(value), focused: focusedField, force: !coinsInitialized)
            coinsInitialized = true
        }

        if let value = snapshot.rerolls {
            drafts.observe(.rerolls, value: number(value), focused: focusedField, force: !rerollsInitialized)
            rerollsInitialized = true
        }

        if !vitalsInitialized,
           let health = snapshot.health,
           let maxHealth = snapshot.maxHealth,
           let mana = snapshot.mana,
           let maxMana = snapshot.maxMana,
           let armor = snapshot.armor {
            drafts.observe([
                .healthCurrent: number(health),
                .healthMax: number(maxHealth),
                .manaCurrent: number(mana),
                .manaMax: number(maxMana),
                .armorCurrent: number(armor),
                .spellCharge: number(snapshot.spellCharge),
                .biomeTime: Hades2TrainerModel.displayBiomeTime(snapshot.biomeTime),
            ], focused: focusedField, force: true)
            vitalsInitialized = true
        } else if vitalsInitialized {
            var observed: [EditField: String] = [
                .biomeTime: Hades2TrainerModel.displayBiomeTime(snapshot.biomeTime),
            ]
            if let value = snapshot.health { observed[.healthCurrent] = number(value) }
            if let value = snapshot.maxHealth { observed[.healthMax] = number(value) }
            if let value = snapshot.mana { observed[.manaCurrent] = number(value) }
            if let value = snapshot.maxMana { observed[.manaMax] = number(value) }
            if let value = snapshot.armor { observed[.armorCurrent] = number(value) }
            if let value = snapshot.spellCharge { observed[.spellCharge] = number(value) }
            drafts.observe(observed, focused: focusedField)
        }
    }

    private func syncStatSnapshot(_ snapshot: Hades2ViewStatSnapshot) {
        guard model.connected else { return }
        var observed: [EditField: String] = [:]
        if let value = snapshot.grasp { observed[.grasp] = number(value) }
        if let value = snapshot.dodge { observed[.dodge] = compactNumber(value) }
        if let value = snapshot.crit { observed[.crit] = compactNumber(value) }
        if let value = snapshot.chargeSpeed { observed[.chargeSpeed] = compactNumber(value) }
        if let value = snapshot.moveSpeed { observed[.moveSpeed] = compactNumber(value) }
        if let value = snapshot.sprintSpeed { observed[.sprintSpeed] = compactNumber(value) }
        if let value = snapshot.dashSpeed { observed[.dashSpeed] = compactNumber(value) }
        if let value = snapshot.attackSpeed { observed[.attackSpeed] = compactNumber(value) }
        if let value = snapshot.manaRegen { observed[.manaRegen] = compactNumber(value) }
        if let value = snapshot.enemyDamage { observed[.enemyDamage] = compactNumber(value) }
        if let value = snapshot.enemyHealth { observed[.enemyHealth] = compactNumber(value) }
        drafts.observe(observed, focused: focusedField, force: !statsInitialized)
        statsInitialized = true
    }

    private func syncConfigSnapshot(_ snapshot: Hades2ViewConfigSnapshot) {
        syncElementInputs(snapshot.elements)
        var observed: [EditField: String] = [
            .damageMultiplier: compactNumber(snapshot.damageMultiplier),
            .moneyMultiplier: compactNumber(snapshot.moneyMultiplier),
            .resourceMultiplier: compactNumber(snapshot.resourceMultiplier),
        ]
        if gameSpeedPreview == nil {
            observed[.gameSpeed] = speedNumber(snapshot.gameSpeed)
        }
        drafts.observe(observed, focused: focusedField)
    }

    private func syncElementInputs(_ values: [ElementCount]) {
        let observed = Dictionary(uniqueKeysWithValues: values.map { (EditField.element($0.id), number($0.count)) })
        drafts.observe(observed, focused: focusedField, force: !elementsInitialized)
        elementsInitialized = true
    }

    private func applyCatalogChanges(from oldValue: Hades2ViewCatalogSnapshot, to newValue: Hades2ViewCatalogSnapshot) {
        if oldValue.materialID != newValue.materialID {
            drafts[.material] = newValue.materialCount.map { number($0) } ?? ""
        } else if oldValue.materialCount != newValue.materialCount {
            drafts.observe(.material, value: newValue.materialCount.map { number($0) } ?? "", focused: focusedField)
        }
        if !model.selectedNextOccurrenceTarget.isEmpty
            && !newValue.occurrenceTargetIDs.contains(model.selectedNextOccurrenceTarget) {
            model.selectedNextOccurrenceTarget = ""
        }
        if !newValue.olympianIDs.contains(model.selectedOlympianReward) { model.selectedOlympianReward = newValue.olympianIDs.first ?? "" }
        if !newValue.pickupIDs.contains(model.selectedPickupReward) { model.selectedPickupReward = newValue.pickupIDs.first ?? "" }
        if !newValue.specialIDs.contains(model.selectedSpecialReward) { model.selectedSpecialReward = newValue.specialIDs.first ?? "" }
        if !newValue.exactIDs.contains(model.selectedExactBoon) { model.selectedExactBoon = newValue.exactIDs.first ?? "" }
        if !newValue.filteredResourceIDs.contains(selectedMaterial) {
            selectedMaterial = search.isEmpty && newValue.filteredResourceIDs.contains("MetaCurrency")
                ? "MetaCurrency"
                : (newValue.filteredResourceIDs.first ?? "")
        }
    }

    private func rebuildEditorDraftsFromModel() {
        focusedField = nil
        resetEditorInputs()
        guard model.connected else { return }
        syncConnectionSnapshot(connectionSnapshot)
        syncStatSnapshot(statSnapshot)
        syncConfigSnapshot(configSnapshot)
        drafts[.material] = material.map { number($0.count) } ?? ""
    }

    private func resetEditorInputs() {
        coinsInitialized = false
        rerollsInitialized = false
        vitalsInitialized = false
        statsInitialized = false
        elementsInitialized = false
        gameSpeedPreview = nil
        drafts.reset(to: Self.defaultDrafts)
    }

    private var sessionStatsPanel: some View {
        VStack(spacing: 0) {
            TrainerMetricGrid { primarySessionMetrics }
            TrainerDisclosure(isExpanded: model.numericControlsExpanded) {
                TrainerMetricGrid { expandedSessionMetrics }.padding(.top, 12)
            }
        }
    }

    @ViewBuilder
    private var primarySessionMetrics: some View {
        editableVitalMetric(
            text("hades2.vital.health"), icon: TrainerSemanticIcon.Concept.vitality, current: draft(.healthCurrent), maximum: draft(.healthMax),
            currentField: .healthCurrent, maxField: .healthMax, color: .pink,
            vital: "health", locked: model.healthLocked
        )
        editableVitalMetric(
            text("hades2.vital.mana"), icon: TrainerSemanticIcon.Concept.energy, current: draft(.manaCurrent), maximum: draft(.manaMax),
            currentField: .manaCurrent, maxField: .manaMax, color: .cyan,
            vital: "mana", locked: model.manaLocked
        )
        editableAmountMetric(
            text("hades2.vital.runGold"), icon: TrainerSemanticIcon.Concept.currency, text: draft(.coins), focus: .coins,
            color: .yellow, locked: model.moneyLocked, enabled: model.canSetResource,
            edit: .resource("Money"), lockEnabled: !model.infiniteMoney
        ) {
            model.lockResource("Money", locked: !model.moneyLocked)
        }
        editableAmountMetric(
            text("hades2.vital.armor"), icon: TrainerSemanticIcon.Concept.defense, text: draft(.armorCurrent), focus: .armorCurrent,
            color: theme.warning, locked: model.armorLocked, enabled: model.canSetVital("armor"),
            edit: .vital("armor", field: "current")
        ) {
            model.lockVital("armor", locked: !model.armorLocked)
        }
    }

    @ViewBuilder
    private var expandedSessionMetrics: some View {
        damageMetric
        editableStatMetric(stat: "grasp", text: draft(.grasp), focus: .grasp, suffix: "", locked: model.graspLocked)
        editableAmountMetric(
            text("hades2.metric.rerolls"), icon: TrainerSemanticIcon.Concept.randomize, text: draft(.rerolls), focus: .rerolls,
            color: accent, locked: model.rerollsLocked, enabled: model.canSetRerolls,
            edit: .rerolls, lockEnabled: !model.infiniteRerolls
        ) {
            model.lockRerolls(!model.rerollsLocked)
        }
        editableCounterMetric(
            text("hades2.metric.spellCharge"), icon: Hades2WorkbenchIcon.spellCharge, text: draft(.spellCharge),
            focus: .spellCharge, color: .purple,
            detail: model.spellChargeCost.map { cost in
                    localization.string("hades2.metric.cost", arguments: [number(cost)])
                } ?? nil,
            edit: .counter("spellCharge")
        )
        editableAmountMetric(
            text("hades2.metric.biomeTime"), icon: TrainerSemanticIcon.Concept.timer,
            text: draft(.biomeTime), focus: .biomeTime,
            color: .orange, locked: model.biomeTimeLocked,
            enabled: model.canSetBiomeTime, edit: .biomeTime,
            lockEnabled: (model.biomeTime ?? 0) > 0 || model.biomeTimeLocked
        ) {
            model.lockBiomeTime(!model.biomeTimeLocked)
        }
        editableStatMetric(stat: "dodge", text: draft(.dodge), focus: .dodge, suffix: "%", locked: model.dodgeLocked)
        editableStatMetric(stat: "crit", text: draft(.crit), focus: .crit, suffix: "%", locked: model.critLocked)
        editableStatMetric(stat: "enemyDamage", text: draft(.enemyDamage), focus: .enemyDamage, suffix: "%", locked: model.enemyDamageLocked)
        editableStatMetric(stat: "enemyHealth", text: draft(.enemyHealth), focus: .enemyHealth, suffix: "%", locked: model.enemyHealthLocked)
        editableStatMetric(stat: "chargeSpeed", text: draft(.chargeSpeed), focus: .chargeSpeed, suffix: "%", locked: model.chargeSpeedLocked)
        editableStatMetric(stat: "moveSpeed", text: draft(.moveSpeed), focus: .moveSpeed, suffix: "%", locked: model.moveSpeedLocked)
        editableStatMetric(stat: "sprintSpeed", text: draft(.sprintSpeed), focus: .sprintSpeed, suffix: "%", locked: model.sprintSpeedLocked)
        editableStatMetric(stat: "dashSpeed", text: draft(.dashSpeed), focus: .dashSpeed, suffix: "%", locked: model.dashSpeedLocked)
        editableStatMetric(stat: "attackSpeed", text: draft(.attackSpeed), focus: .attackSpeed, suffix: "%", locked: model.attackSpeedLocked)
        editableStatMetric(stat: "manaRegen", text: draft(.manaRegen), focus: .manaRegen, suffix: "/s", locked: model.manaRegenLocked)
    }

    private var elementPanel: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 12), count: max(model.elements.count, 1))
        return LazyVGrid(columns: columns, spacing: 12) {
            ForEach(model.elements) { element in
                elementMetric(element)
            }
        }
    }

    private var damageMetric: some View {
        TrainerCheatMultiplierCard(
            definition: Hades2CheatCatalog.definition(id: "damageMultiplier")!,
            text: draft(.damageMultiplier), focus: $focusedField, focusValue: .damageMultiplier,
            suffix: "×", editable: model.canEditDesired,
            onCommit: completing(.multiplier("damageMultiplier"))
        )
    }

    private var boonRarityPanel: some View {
        Hades2BoonRarityPanel(model: model)
    }

    private static let worldActionGodIDs: Set<String> = [
        "AphroditeUpgrade",
        "ApolloUpgrade",
        "AresUpgrade",
        "DemeterUpgrade",
        "HephaestusUpgrade",
        "HeraUpgrade",
        "HermesUpgrade",
        "HestiaUpgrade",
        "PoseidonUpgrade",
        "ZeusUpgrade",
    ]

    private static let worldActionRoomIDs: Set<String> = [
        "P_MiniBoss01",
        "P_MiniBoss02",
    ]

    /// Every reason the resident reports on a Modify Exit item (#832): the
    /// game's own selection rules, shown as warnings, and the few refusals
    /// (a native probe that threw, no buildable room).
    private static let worldActionReasonIDs: Set<String> = [
        "biome_depth_too_high",
        "biome_depth_too_low",
        "door_forced_destination",
        "door_forced_room_set",
        "door_has_predetermined_destination",
        "game_state_requirements",
        "global_forced_destination",
        "god_eligibility_requires_rng",
        "god_eligibility_unavailable",
        "god_limit",
        "god_not_eligible",
        "max_appearances_this_biome",
        "max_creations_this_run",
        "native_forced_room_present",
        "native_ineligible",
        "no_room_route",
        "reward_eligibility_probe_error",
        "reward_eligibility_requires_rng",
        "reward_eligibility_unavailable",
        "reward_not_available",
        "reward_not_in_current_store",
        "reward_store_name_missing",
        "reward_store_unavailable",
        "room_eligibility_probe_error",
        "room_eligibility_requires_rng",
        "room_eligibility_unavailable",
        "room_excluded_by_exit_rules",
        "room_has_fixed_reward_category",
        "room_has_forced_reward",
        "room_linked_route_required",
        "room_max_appearances_this_run",
        "room_max_creations_per_room",
        "room_miniboss_wing_required",
        "room_no_reward",
        "room_requires_indoor",
        "room_required_tags_missing",
        "room_reward_deferred",
        "room_same_as_source",
        "room_wrong_wing_end",
        "source_anomaly_replacement",
        "source_forced_room_set",
        "source_linked_destination",
        "source_next_room_set",
        "source_persistent_door_rooms",
        "source_uses_previous_room_set",
    ]

    private func worldActionReason(_ id: String?) -> String? {
        guard let id else { return nil }
        let known = Self.worldActionReasonIDs.contains(id) ? id : "native_ineligible"
        let key = "hades2.worldActions.unavailable.\(known)"
        let localized = text(key)
        return localized == key ? text("hades2.worldActions.unavailable.native_ineligible") : localized
    }

    private func worldActionRoomLabel(_ id: String) -> String {
        if id == "current" { return text("hades2.worldActions.currentRoom") }
        if id.contains("_MiniBoss") {
            if Self.worldActionRoomIDs.contains(id) {
                let key = "hades2.worldActions.room.\(id)"
                let localized = text(key)
                if localized != key { return localized }
            }
            return "\(text("hades2.worldActions.route.miniboss")) · \(id)"
        }
        switch id {
        case "H_Bridge01":
            return text("hades2.worldActions.room.H_Bridge01")
        case "combat", "miniboss", "story", "shop", "reprieve":
            return text("hades2.worldActions.route.\(id)")
        default:
            return id
        }
    }

    private func worldActionRewardLabel(_ id: String) -> String {
        if Self.worldActionGodIDs.contains(id) {
            let key = "hades2.worldActions.god.\(id)"
            let localized = text(key)
            if localized != key { return localized }
        }
        let localized: String?
        switch id {
        case "Story": localized = text("hades2.worldActions.route.story")
        case "Shop": localized = text("hades2.worldActions.route.shop")
        case "RoomMoneyDrop": localized = rewardLabel("RoomMoneyDrop")
        case "MetaCardPointsCommonDrop": localized = rewardLabel("MetaCardPointsCommonDrop")
        case "MemPointsCommonDrop": localized = rewardLabel("MemPointsCommonDrop")
        case "MetaCurrencyDrop": localized = rewardLabel("MetaCurrencyDrop")
        case "MaxHealthDrop": localized = rewardLabel("MaxHealthDrop")
        case "MaxManaDrop": localized = rewardLabel("MaxManaDrop")
        case "StackUpgrade": localized = rewardLabel("StackUpgrade")
        case "WeaponUpgrade": localized = rewardLabel("WeaponUpgrade")
        case "SpellDrop": localized = rewardLabel("SpellDrop")
        default: localized = nil
        }
        if let localized { return localized }
        if let option = model.boons.first(where: { $0.id == id }) {
            if localization.language == .en {
                return option.englishName.isEmpty ? option.name : option.englishName
            }
            return option.englishName.isEmpty ? option.name : "\(option.name) · \(option.englishName)"
        }
        return id
    }

    /// A refused item names why; an allowed item names the game rule it breaks.
    private func worldActionItemLabel(_ label: String, enabled: Bool = true,
                                      reason: String? = nil, warning: String? = nil) -> String {
        if !enabled { return "\(label) · \(worldActionReason(reason ?? "native_ineligible") ?? "")" }
        guard let warning = worldActionReason(warning) else { return label }
        return "\(label) · ⚠︎ \(warning)"
    }

    /// `Exit 1 · Combat · Zeus`: what the door holds now, as the game reports it.
    private func worldExitLabel(_ exit: Hades2WorldExit) -> String {
        if exit.exitKind == "shipWheel" {
            let wheelTitle: String
            switch exit.wheelSide {
            case "left": wheelTitle = text("hades2.worldActions.shipWheel.left")
            case "right": wheelTitle = text("hades2.worldActions.shipWheel.right")
            case "forward": wheelTitle = text("hades2.worldActions.shipWheel.forward")
            default: wheelTitle = text("hades2.worldActions.shipWheel")
            }
            let rewardText = exit.reward.isEmpty
                ? text("hades2.worldActions.noReward")
                : worldActionRewardLabel(exit.reward)
            return "\(wheelTitle) · \(rewardText)"
        }
        let prefix: String
        if exit.exitKind == "cageReward", let slot = exit.slotIndex {
            prefix = text(
                "hades2.worldActions.exitRewardSlot",
                arguments: [String(exit.doorOrdinal ?? exit.ordinal), String(slot)]
            )
        } else {
            prefix = text("hades2.worldActions.exitNumber", arguments: [String(exit.ordinal)])
        }
        var parts = [prefix]
        if !exit.roomKind.isEmpty {
            parts.append(worldActionRoomLabel(exit.roomKind))
        } else {
            parts.append(exit.roomName.isEmpty ? text("hades2.worldActions.unknownTarget") : worldActionRoomLabel(exit.roomName))
        }
        if exit.reward.isEmpty {
            parts.append(text("hades2.worldActions.noReward"))
        } else if exit.reward != "Empty",
                  !(exit.reward == "Story" && exit.roomKind == "story"),
                  !(exit.reward == "Shop" && exit.roomKind == "shop") {
            parts.append(worldActionRewardLabel(exit.reward))
        }
        return parts.joined(separator: " · ")
    }

    private func worldExitChoiceLabel(_ choice: Hades2WorldExitChoice, in exit: Hades2WorldExit) -> String {
        let room = worldActionRoomLabel(choice.room)
        let label: String
        if let reward = choice.reward {
            label = "\(room) · \(worldActionRewardLabel(reward))"
        } else {
            let acceptsReward = exit.roomTargets.first { $0.id == choice.room }?.acceptsReward ?? false
            label = acceptsReward ? "\(room) · \(text("hades2.worldActions.anyReward"))" : room
        }
        return worldExitChoiceItemLabel(label, choice: choice, in: exit)
    }

    private func worldExitChoiceItemLabel(_ label: String, choice: Hades2WorldExitChoice,
                                          in exit: Hades2WorldExit, enabled: Bool = true,
                                          reason: String? = nil) -> String {
        guard enabled else { return worldActionItemLabel(label, enabled: false, reason: reason) }
        let room = exit.roomTargets.first { $0.id == choice.room }
        let reward = exit.rewardTargets.first { $0.id == choice.reward }
        let warnings = [choice.reward != nil && exit.isCurrentRoom(choice.room)
            ? exit.rewardWarning : room?.warning, reward?.warning]
        var seen = Set<String>()
        return warnings.compactMap { $0 }.filter { seen.insert($0).inserted }.reduce(label) {
            worldActionItemLabel($0, warning: $1)
        }
    }

    private func worldExitChoiceItem(_ choice: Hades2WorldExitChoice, title: String, enabled: Bool) -> some View {
        Toggle(isOn: Binding(
            get: { model.selectedWorldExitTarget == choice.id },
            set: { if $0 { model.selectedWorldExitTarget = choice.id } }
        )) {
            Text(title)
        }
        .disabled(!enabled)
    }

    /// One room type's submenu: "Any reward" (a reservation; the game picks),
    /// then Olympians, then other rewards. A reward under the door's own room
    /// type edits that room in place.
    @ViewBuilder
    private func worldExitRewardItems(_ exit: Hades2WorldExit, room: Hades2WorldActionTarget) -> some View {
        let gods = exit.rewardTargets.filter { Self.worldActionGodIDs.contains($0.id) }
        let others = exit.rewardTargets.filter { !Self.worldActionGodIDs.contains($0.id) }
        if exit.offersAnyReward(room) {
            let choice = Hades2WorldExitChoice(room: room.id)
            worldExitChoiceItem(
                choice,
                title: worldExitChoiceItemLabel(text("hades2.worldActions.anyReward"), choice: choice, in: exit),
                enabled: true
            )
        }
        if !gods.isEmpty {
            Section(text("hades2.worldActions.gods")) {
                ForEach(gods) { reward in
                    let choice = Hades2WorldExitChoice(room: room.id, reward: reward.id)
                    worldExitChoiceItem(
                        choice,
                        title: worldExitChoiceItemLabel(worldActionRewardLabel(reward.id), choice: choice, in: exit,
                            enabled: reward.enabled, reason: reward.reason),
                        enabled: reward.enabled
                    )
                }
            }
        }
        if !others.isEmpty {
            Section(text("hades2.worldActions.rewards")) {
                ForEach(others) { reward in
                    let choice = Hades2WorldExitChoice(room: room.id, reward: reward.id)
                    worldExitChoiceItem(
                        choice,
                        title: worldExitChoiceItemLabel(worldActionRewardLabel(reward.id), choice: choice, in: exit,
                            enabled: reward.enabled, reason: reward.reason),
                        enabled: reward.enabled
                    )
                }
            }
        }
    }

    /// Target: a nested menu by room type (`Combat > Zeus`, `Story`, ...).
    /// One choice sets the room type and the reward together (#832).
    private func worldExitTargetMenu(_ exit: Hades2WorldExit?) -> some View {
        let title: String
        if let exit, let lease = exit.activeLease {
            title = worldExitChoiceLabel(lease.choice, in: exit)
        } else if let exit, let choice = model.selectedWorldExitChoice, exit.isEnabled(choice) {
            title = worldExitChoiceLabel(choice, in: exit)
        } else {
            title = text("hades2.worldActions.noTarget")
        }
        return Menu {
            if let exit {
                ForEach(exit.roomTargets) { room in
                    if room.acceptsReward {
                        Menu {
                            worldExitRewardItems(exit, room: room)
                        } label: {
                            Text(worldActionItemLabel(worldActionRoomLabel(room.id), enabled: room.enabled,
                                reason: room.reason))
                        }
                        .disabled(!room.enabled)
                    } else {
                        let choice = Hades2WorldExitChoice(room: room.id)
                        worldExitChoiceItem(
                            choice,
                            title: worldExitChoiceItemLabel(worldActionRoomLabel(room.id), choice: choice, in: exit,
                                enabled: room.enabled, reason: room.reason),
                            enabled: room.enabled
                        )
                    }
                }
            }
        } label: {
            Text(title)
        }
        .accessibilityLabel(text("hades2.worldActions.target"))
        .accessibilityValue(title)
    }

    private var worldExitPanel: some View {
        let exit = model.selectedWorldExit
        return TrainerDualPickerActionRow(
            title: text("hades2.worldActions.modifyExit"),
            icon: Hades2WorkbenchIcon.doorway,
            tint: model.canSelectWorldExit ? theme.accent : theme.inactive,
            emphasized: model.selectedWorldExitLease != nil
        ) {
            Picker(
                text("hades2.worldActions.exit"),
                selection: Binding(
                    get: { model.selectedWorldExitToken },
                    set: {
                        model.selectedWorldExitToken = $0
                        model.repairWorldActionSelection()
                    }
                )
            ) {
                if model.worldActionExits.isEmpty {
                    Text(text("hades2.worldActions.noExit")).tag("")
                }
                ForEach(model.worldActionExits) { row in
                    Text(worldExitLabel(row)).tag(row.doorToken)
                }
            }
            .labelsHidden()
            .trainerPicker(.layoutAllocated, state: model.canSelectWorldExit ? .interactive : .unavailable)
            .accessibilityIdentifier("hades2.worldActions.currentExit")
        } secondPicker: {
            worldExitTargetMenu(exit)
                .trainerPicker(.layoutAllocated, state: model.canSelectWorldExitTarget ? .interactive : .unavailable)
                .accessibilityIdentifier("hades2.worldActions.target")
        } shortcut: {
            TrainerShortcutBadgeSlot(text: model.shortcutText(.applyWorldExit))
        } action: {
            TrainerSecondaryActionButton(
                title: text(model.selectedWorldExitLease != nil ? "hades2.worldActions.cancel" : "hades2.worldActions.apply"),
                enabled: model.selectedWorldExitActionAvailable,
                latched: model.selectedWorldExitLease != nil,
                subduedLatched: true,
                widthRole: .compactRow,
                helpText: text(model.selectedWorldExitLease != nil ? "hades2.worldActions.cancel" : "hades2.worldActions.apply")
            ) {
                _ = model.toggleSelectedWorldExit()
            }
            .accessibilityIdentifier("hades2.worldActions.apply")
        }
        .trainerGroupedRows()
    }

    private var nextOccurrencePanel: some View {
        let characters = model.occurrenceTargets.filter { $0.kind == "character" }
        let shops = model.occurrenceTargets.filter { $0.kind == "shop" }
        let pending = model.activeWorldOccurrenceTarget != nil
        return TrainerLabeledControlRow(
            title: text("hades2.occurrence.title"),
            icon: Hades2WorkbenchIcon.occurrence,
            tint: model.canSelectWorldOccurrence ? theme.accent : theme.inactive,
            emphasized: pending,
            layout: .pickerAction
        ) {
            Picker(text("hades2.occurrence.title"), selection: $model.selectedNextOccurrenceTarget) {
                if model.occurrenceTargets.isEmpty {
                    Text(text("hades2.occurrence.noRequest")).tag("")
                }
                if !characters.isEmpty {
                    Section(text("hades2.occurrence.characters")) {
                        ForEach(characters) { target in
                            Text(text(target.titleKey)).tag(target.id)
                        }
                    }
                }
                if !shops.isEmpty {
                    Section(text("hades2.occurrence.shop")) {
                        ForEach(shops) { target in
                            Text(text(target.titleKey)).tag(target.id)
                        }
                    }
                }
            }
            .labelsHidden()
            .trainerPicker(
                .rowAction,
                state: model.canSelectWorldOccurrenceTarget
                    ? .interactive : .unavailable
            )
            TrainerShortcutBadgeSlot(text: model.shortcutText(.applyNextOccurrence))
            TrainerSecondaryActionButton(
                title: text(pending ? "hades2.worldActions.cancel" : "hades2.worldActions.apply"),
                enabled: model.occurrenceActionAvailable,
                latched: pending,
                subduedLatched: true,
                helpText: text(pending ? "hades2.worldActions.cancel" : "hades2.worldActions.apply")
            ) {
                _ = model.toggleNextOccurrence()
            }
        }
        .trainerGroupedRows()
    }

    private var resourcePanel: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            VStack(spacing: 1) {
                // The two gain multipliers are one family; keep them adjacent so the
                // shared "gain" meaning is visible instead of split around the editor.
                ForEach(Hades2CheatCatalog.multiplierToggleDefinitions) { definition in
                    let isMoney = definition.id == "moneyMultiplierEnabled"
                    let feature = isMoney ? "moneyMultiplier" : "resourceMultiplier"
                    let enabled = isMoney ? model.moneyMultiplierEnabled : model.resourceMultiplierEnabled
                    let field: EditField = isMoney ? .moneyMultiplier : .resourceMultiplier
                    if let toggle = Hades2FeatureKey(rawValue: definition.id) {
                        let shortcut = ShortcutAction(rawValue: definition.shortcutID ?? definition.id)
                        TrainerCheatMultiplierRow(
                            definition: definition,
                            state: model.featurePresentation(toggle, enabled: enabled)
                                .trainerControlState(using: theme, localization: localization),
                            text: draft(field),
                            onCommit: completing(.multiplier(feature)),
                            onEditingChanged: tracking(field),
                            shortcutText: shortcut.map { model.shortcutText($0) }
                        ) {
                            model.feature(toggle, value: !enabled)
                        }
                    }
                }
            }
            .trainerGroupedRows()
            TrainerResourceEditor(
                title: text("hades2.resource.materials"),
                icon: TrainerSemanticIcon.Concept.item,
                search: $search,
                selection: $selectedMaterial,
                amount: draft(.material),
                sections: resourceGroups(filtered),
                enabled: model.canSetResource,
                lock: TrainerResourceLock(locked: material?.locked ?? false) {
                    guard let material else { return }
                    model.lockResource(material.id, locked: !material.locked)
                },
                itemLabel: { resource in
                    let primaryName = localization.language == .en && !resource.englishName.isEmpty
                        ? resource.englishName : resource.name
                    let secondaryName = localization.language == .en ? resource.name : resource.englishName
                    let displayName = secondaryName.isEmpty || secondaryName == primaryName
                        ? primaryName : "\(primaryName) · \(secondaryName)"
                    return displayName
                        + " · \(number(resource.count))"
                        + (resource.locked ? " · " + text("hades2.vital.lockedSuffix") : "")
                },
                onEditingChanged: tracking(.material),
                onCommit: completing(.resource(selectedMaterial))
            )
            .trainerPanel()
        }
    }

    private var rewardSpawningPanel: some View {
        VStack(spacing: 1) {
            spawnRow(title: text("hades2.spawn.olympianBoons"), icon: TrainerSemanticIcon.Section.effects, options: olympianBoons, selection: $model.selectedOlympianReward, shortcut: .spawnOlympian, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            spawnRow(title: text("hades2.spawn.pickupRewards"), icon: TrainerSemanticIcon.Section.inventory, options: pickupRewards, selection: $model.selectedPickupReward, shortcut: .spawnPickup, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            spawnRow(
                title: text("hades2.spawn.characterRewards"),
                icon: Hades2WorkbenchIcon.specialReward,
                options: specialBoons,
                selection: $model.selectedSpecialReward,
                shortcut: .spawnSpecial,
                // The row stays interactive while either character-reward action
                // family is available; the button reflects the selected option.
                enabled: model.canSpawnReward || model.canOpenSpecialChoice,
                actionEnabled: model.canPerformSelectedSpecialReward,
                onAction: model.performSpecialReward
            )
        }.trainerGroupedRows()
    }

    /// Session-only settings for the currently active acquisition target.
    /// Neither the source nor the displayed rarity is the natural-offer policy.
    private var acquisitionSettingsRow: some View {
        HStack(spacing: 6) {
            Text(text("hades2.acquisition.level"))
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
            TrainerNumberField(
                text: $model.acquisitionLevel,
                accessibilityLabel: text("hades2.acquisition.level"),
                accessibilityIdentifier: "hades2.acquisition.level",
                width: theme.inlineFieldWidth,
                enabled: model.acquisitionSupportsLevel,
                onCommit: { value in
                    guard let level = Int(value.text), (1...999_999).contains(level) else {
                        return value.rejected(message: text("hades2.acquisition.invalidLevel"))
                    }
                    return String(level)
                }
            )
            .id(model.acquisitionTarget.rawValue + "|" + model.acquisitionTargetDescription)

            Text(text("hades2.acquisition.rarity"))
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
            Picker(text("hades2.acquisition.rarity"), selection: Binding(
                get: { model.acquisitionAllowsCallerRarity ? model.acquisitionRarity : "" },
                set: { model.selectAcquisitionRarity($0) }
            )) {
                if !model.acquisitionAllowsCallerRarity {
                    Text(text("hades2.acquisition.gameControlled")).tag("")
                }
                ForEach(model.acquisitionRarityOptions, id: \.self) { rarity in
                    Text(traitRarityLabel(rarity)).tag(rarity)
                }
            }
            .labelsHidden()
            .trainerPicker(.compactValue, state: model.acquisitionAllowsCallerRarity ? .interactive : .unavailable)

            if model.acquisitionRarityAdjustment != .none {
                let key = model.acquisitionAllowsCallerRarity
                    ? "hades2.acquisition.adjustedRarity" : "hades2.acquisition.gameControlledHint"
                Text(model.acquisitionAllowsCallerRarity
                     ? text("hades2.acquisition.adjustedRarityCompact") + " " + traitRarityLabel(model.acquisitionRarity)
                     : text("hades2.acquisition.gameControlledCompact"))
                    .font(.caption2).foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 88, alignment: .leading)
                    .help(model.acquisitionAllowsCallerRarity
                        ? text(key) + " " + traitRarityLabel(model.acquisitionRarity)
                        : text(key))
                    .accessibilityIdentifier("hades2.acquisition.adjustment")
            }
        }
    }

    private static let exactBoonCaptionKeys = [
        "hades2.spawn.chaosBlessing", "hades2.spawn.chaosCurse",
        "hades2.spawn.exactSource", "hades2.spawn.exactTarget",
    ]

    /// Each dual-picker row splits what its two captions leave between its
    /// pickers. Sizing every caption to the widest of the four, in the current
    /// language, keeps all four pickers the same width and aligned.
    private func exactBoonCaption(_ key: String) -> some View {
        ZStack(alignment: .leading) {
            ForEach(Self.exactBoonCaptionKeys, id: \.self) { Text(text($0)).hidden() }
            Text(text(key))
        }
        .font(.caption).foregroundStyle(.secondary)
        .fixedSize(horizontal: true, vertical: false)
    }

    private func exactBoonShortcut(_ action: ShortcutAction) -> some View {
        ZStack(alignment: .leading) {
            TrainerShortcutBadgeSlot(text: model.shortcutText(.acquireChaosPair)).hidden()
            TrainerShortcutBadgeSlot(text: model.shortcutText(.acquireExactBoon)).hidden()
            TrainerShortcutBadgeSlot(text: model.shortcutText(action))
        }
    }

    private var boonAcquisitionPanel: some View {
        TrainerAcquisitionPanel(
            title: text("hades2.spawn.exactBoons"),
            icon: Hades2WorkbenchIcon.exactBoons,
            search: $exactSearch,
            searchPlaceholder: text("hades2.spawn.search"),
            clearLabel: localization.localized("host.search.clear")
        ) {
            acquisitionSettingsRow
        } rows: {
            VStack(alignment: .leading, spacing: 16) {
                TrainerDualInlinePickerLayout(
                    minimumPickerWidth: 144,
                    maximumPickerWidth: theme.pickerActionMaxWidth,
                    minimumShortcutWidth: theme.shortcutBadgeMinimumWidth,
                    minimumActionWidth: theme.compactActionWidth
                ) {
                    exactBoonCaption("hades2.spawn.chaosBlessing")
                    Picker(text("hades2.spawn.chaosBlessing"), selection: $model.selectedChaosBlessing) {
                        if chaosBlessingOptions.isEmpty {
                            Text(text("hades2.spawn.noItems")).tag("")
                        }
                        ForEach(chaosBlessingOptions) { option in
                            Text(exactItemLabel(option)).tag(option.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.layoutAllocated, state: model.canAcquireChaosPair && !chaosBlessingOptions.isEmpty ? .interactive : .unavailable)

                    exactBoonCaption("hades2.spawn.chaosCurse")
                    Picker(text("hades2.spawn.chaosCurse"), selection: $model.selectedChaosCurse) {
                        if chaosCurseOptions.isEmpty {
                            Text(text("hades2.spawn.noItems")).tag("")
                        }
                        ForEach(chaosCurseOptions) { option in
                            Text(exactItemLabel(option)).tag(option.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.layoutAllocated, state: model.canAcquireChaosPair && !chaosCurseOptions.isEmpty ? .interactive : .unavailable)

                    exactBoonShortcut(.acquireChaosPair)
                    TrainerSecondaryActionButton(
                        title: text("hades2.spawn.acquire"),
                        enabled: model.canAcquireChaosPair
                            && chaosBlessingOptions.contains(where: { $0.id == model.selectedChaosBlessing })
                            && chaosCurseOptions.contains(where: { $0.id == model.selectedChaosCurse }),
                        widthRole: .compactRow
                    ) {
                        _ = model.acquireChaosPair(
                            blessingReward: model.selectedChaosBlessing,
                            curseReward: model.selectedChaosCurse
                        )
                    }
                }
                .onAppear { repairChaosPairSelections() }
                .onChange(of: model.exactBoonOptions.map(\.id)) { _, _ in repairChaosPairSelections() }

                TrainerDualInlinePickerLayout(
                    minimumPickerWidth: 144,
                    maximumPickerWidth: theme.pickerActionMaxWidth,
                    minimumShortcutWidth: theme.shortcutBadgeMinimumWidth,
                    minimumActionWidth: theme.compactActionWidth
                ) {
                    exactBoonCaption("hades2.spawn.exactSource")
                    Picker(
                        text("hades2.spawn.exactSource"),
                        selection: Binding(
                            get: { exactSourceSelection },
                            set: { selectExactSource($0) }
                        )
                    ) {
                        if exactBoonSourceGroups.isEmpty {
                            Text(text("hades2.spawn.noItems")).tag("")
                        }
                        ForEach(exactBoonSourceGroups) { group in
                            Text(group.title).tag(group.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.layoutAllocated, state: model.canAcquireExactReward && !exactBoonSourceGroups.isEmpty ? .interactive : .unavailable)

                    exactBoonCaption("hades2.spawn.exactTarget")
                    Picker(text("hades2.spawn.exactTarget"), selection: exactItemSelection) {
                        if selectedExactItems.isEmpty || exactItemSelection.wrappedValue.isEmpty {
                            Text(text("hades2.spawn.noItems")).tag("")
                        }
                        ForEach(selectedExactItems) { option in
                            Text(exactItemLabel(option)).tag(option.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.layoutAllocated, state: model.canAcquireExactReward && !selectedExactItems.isEmpty ? .interactive : .unavailable)

                    exactBoonShortcut(.acquireExactBoon)
                    TrainerSecondaryActionButton(
                        title: text("hades2.spawn.acquire"),
                        enabled: model.canAcquireExactReward
                            && selectedExactItems.contains(where: { $0.id == model.selectedExactBoon }),
                        widthRole: .compactRow
                    ) {
                        _ = model.acquireExactBoon(model.selectedExactBoon)
                    }
                }
                .onAppear { repairExactSourceSelection() }
                .onChange(of: exactSearch) { _, _ in repairExactSourceSelection() }
                .onChange(of: model.exactBoonOptions.map(\.id)) { _, _ in repairExactSourceSelection() }
            }
        }
        .onChange(of: model.selectedChaosBlessing) { _, _ in model.activateAcquisition(.chaos) }
        .onChange(of: model.selectedChaosCurse) { _, _ in model.activateAcquisition(.chaos) }
        .onChange(of: model.selectedExactBoon) { _, _ in model.activateAcquisition(.exact) }
        .onChange(of: model.acquisitionRarity) { _, _ in model.activateAcquisition(model.acquisitionTarget) }
        .onChange(of: model.acquisitionLevel) { _, _ in model.activateAcquisition(model.acquisitionTarget) }
        .onChange(of: model.nativeRarityOrder) { _, _ in model.activateAcquisition(model.acquisitionTarget) }
        .onChange(of: model.exactBoonOptions.map { $0.id + ":" + $0.rarities.joined(separator: ",") }) { _, _ in
            model.activateAcquisition(model.acquisitionTarget)
        }
    }

    private var currentRunEffectsPanel: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            // Runtime trait management is a multi-control form. Keep it as a
            // panel, while the Purging Pool is one functional row and must use
            // the same Core geometry as every other single-action feature.
            currentRunTraitsPanel.trainerPanel()
            TrainerLabeledControlRow(
                title: text("hades2.spawn.purgingPool"),
                icon: Hades2WorkbenchIcon.purge,
                tint: model.canOpenSellTraits ? theme.accent : theme.inactive,
                emphasized: model.canOpenSellTraits
            ) {
                TrainerShortcutBadgeSlot(text: model.shortcutText(.openSellTraits))
                TrainerSecondaryActionButton(
                    title: text("hades2.spawn.open"),
                    enabled: model.canOpenSellTraits,
                    widthRole: .compactRow
                ) { _ = model.openSellTraits() }
            }
            .trainerGroupedRows()
        }
    }

    private func exactItemLabel(_ option: BoonOption) -> String {
        if localization.language == .en {
            if !option.englishName.isEmpty { return option.englishName }
            if !option.name.isEmpty { return option.name }
            return text("hades2.spawn.unnamedEffect")
        }
        if !option.name.isEmpty {
            if !option.englishName.isEmpty && option.englishName != option.name {
                return "\(option.name) · \(option.englishName)"
            }
            return option.name
        }
        if !option.englishName.isEmpty { return option.englishName }
        return text("hades2.spawn.unnamedEffect")
    }

    private func spawnRow(
        title: String?,
        icon: String?,
        options: [BoonOption],
        selection: Binding<String>,
        shortcut: ShortcutAction,
        enabled: Bool,
        actionEnabled: Bool? = nil,
        onAction: @escaping (String) -> Void
    ) -> some View {
        TrainerGroupedOptionPicker(
            title: title,
            icon: icon,
            pickerLabel: title ?? text("hades2.spawn.characterRewards"),
            selection: selection,
            sections: boonGroups(options),
            enabled: enabled,
            actionEnabled: actionEnabled,
            inline: true,
            emptyLabel: text("hades2.spawn.noItems"),
            actionTitle: text("hades2.spawn.generate"),
            shortcutText: model.shortcutText(shortcut),
            itemLabel: exactItemLabel,
            onAction: onAction
        )
    }

    private var management: some View {
        TrainerSection(title: text("hades2.section.management"), icon: Hades2WorkbenchSection.management.icon) {
            Hades2ManagementUtilities()
        }
    }

    private func editableVitalMetric(_ title: String, icon: String, current: Binding<String>, maximum: Binding<String>,
        currentField: EditField, maxField: EditField, color: Color, vital: String, locked: Bool) -> some View {
        TrainerVitalMetricCard(
            title: title,
            icon: icon,
            tint: color,
            current: current,
            maximum: maximum,
            focus: $focusedField,
            currentField: currentField,
            onCurrentCommit: completing(.vital(vital, field: "current")),
            onMaximumCommit: completing(.vital(vital, field: "max")),
            maximumField: maxField,
            locked: locked,
            editable: model.canSetVital(vital),
            onLock: { model.lockVital(vital, locked: !locked) }
        )
    }

    private func editableAmountMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField, color: Color,
        locked: Bool, enabled: Bool, edit: Hades2RuntimeTextEdit, lockEnabled: Bool = true,
        onLock: @escaping () -> Void) -> some View {
        TrainerAmountMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: text,
            focus: $focusedField,
            focusValue: focus,
            locked: locked,
            editable: enabled,
            lockEnabled: lockEnabled,
            onLock: onLock,
            onCommit: completing(edit)
        )
    }

    private func editableCounterMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField,
        color: Color, detail: String?, edit: Hades2RuntimeTextEdit) -> some View {
        TrainerCounterMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: text,
            focus: $focusedField,
            focusValue: focus,
            detail: detail,
            onCommit: completing(edit),
            editable: model.canSetSpellCharge
        )
    }

    private func editableStatMetric(stat: String, text: Binding<String>, focus: EditField,
        suffix: String, locked: Bool) -> some View {
        let definition = Hades2CheatCatalog.definition(id: stat)!
        return TrainerStatMetricCard(
            title: definition.label.resolve(using: localization),
            icon: definition.icon,
            text: text,
            focus: $focusedField,
            focusValue: focus,
            suffix: suffix,
            locked: locked,
            supported: model.statSupport[stat] != false,
            available: model.statAvailable[stat] != false,
            editable: model.canSetStats,
            onLock: { model.setStat(stat, text: text.wrappedValue, locked: !locked) },
            onCommit: completing(.stat(stat))
        )
    }

    private func elementMetric(_ element: ElementCount) -> some View {
        let binding = $drafts.binding(.element(element.id), default: number(element.count))
        let style = elementStyle(element.id)
        return TrainerAmountMetricCard(
            title: elementLabel(element),
            icon: style.icon,
            tint: style.tint,
            text: binding,
            focus: $focusedField,
            focusValue: .element(element.id),
            locked: element.locked,
            editable: model.canSetElements,
            placeholder: "0",
            onLock: { model.lockElement(element.id, locked: !element.locked) },
            onCommit: completing(.element(element.id))
        )
    }

    private func elementStyle(_ id: String) -> (icon: String, tint: Color) {
        switch id {
        case "Fire": return ("flame.fill", .orange)
        case "Water": return ("drop.fill", .blue)
        case "Earth": return ("mountain.2.fill", .brown)
        case "Air": return ("wind", .cyan)
        case "Aether": return ("sparkles", .purple)
        default: return ("circle.hexagongrid.fill", accent)
        }
    }

    private func tracking(_ field: EditField) -> (Bool) -> Void {
        TrainerTextField.editingTracker($focusedField, equals: field)
    }

    private func completing(_ edit: Hades2RuntimeTextEdit) -> (TrainerTextField.Completion) -> String {
        let generation = model.editGeneration
        return { draft in
            model.completeTextEdit(edit, text: draft.text, changed: draft.changed, generation: generation)
            { key in _ = draft.rejected(message: text(key)) }
        }
    }

    private func compactNumber(_ value: Double) -> String { String(format: "%.3g", value) }
    private func speedLabel(_ value: Double) -> String { String(format: "%g×", value) }
    private func number(_ value: Double?) -> String { value.map { String(format: "%.0f", $0) } ?? "—" }
    private func pair(_ value: Double?, _ maximum: Double?) -> String { "\(number(value)) / \(number(maximum))" }
}
