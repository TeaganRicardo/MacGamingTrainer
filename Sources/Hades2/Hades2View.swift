import Foundation
import SwiftUI
import AppKit

// Select the property-wrapper type explicitly: CLT does not ship SwiftUIMacros.
private typealias ViewState<Value> = SwiftUI.State<Value>

struct Hades2TrainerView: View {
    private enum EditField: Hashable {
        case healthCurrent, healthMax, manaCurrent, manaMax, armorCurrent, spellCharge
        case coins, material, rerolls, damageMultiplier, moneyMultiplier, resourceMultiplier, gameSpeed
        case grasp, dodge, crit, chargeSpeed, moveSpeed, sprintSpeed, dashSpeed, attackSpeed, manaRegen, enemyDamage, enemyHealth
        case traitRemainingUses
        case element(String)
    }

    private enum TraitManagerLayout {
        static let rowSpacing: CGFloat = 12
        static let removeControlWidth: CGFloat = 132
        static let searchWidth: CGFloat = 260

        static func levelControlsWidth(compactActionWidth: CGFloat) -> CGFloat {
            42 + 58 + compactActionWidth + 2 * 6
        }

        static func rarityControlsWidth(compactActionWidth: CGFloat, pickerWidth: CGFloat) -> CGFloat {
            48 + pickerWidth + compactActionWidth + 2 * 6
        }

        static func commonControlsWidth(compactActionWidth: CGFloat, pickerWidth: CGFloat) -> CGFloat {
            levelControlsWidth(compactActionWidth: compactActionWidth)
                + rarityControlsWidth(compactActionWidth: compactActionWidth, pickerWidth: pickerWidth)
                + removeControlWidth
                + 2 * rowSpacing
        }
    }

    private struct ExactBoonSourceGroup: Identifiable {
        let id: String
        let title: String
        let items: [BoonOption]
    }

    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerToolWindows) private var toolWindows
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @ViewState<EditField?> private var focusedField = nil

    private var accent: Color { theme.accent }
    @ViewState<String> private var healthCurrent = ""
    @ViewState<String> private var healthMaximum = ""
    @ViewState<String> private var manaCurrent = ""
    @ViewState<String> private var manaMaximum = ""
    @ViewState<String> private var armorCurrent = ""
    @ViewState<String> private var spellCharge = ""
    @ViewState<Bool> private var vitalsInitialized = false
    @ViewState<String> private var coins = ""
    @ViewState<Bool> private var coinsInitialized = false
    @ViewState<String> private var materialAmount = ""
    @ViewState<String> private var selectedMaterial = ""
    @ViewState<String> private var search = ""
    @ViewState<String> private var multiplier = String(format: "%g", Hades2MultiplierKey.damageMultiplier.defaultValue)
    @ViewState<String> private var moneyFactor = String(format: "%g", Hades2MultiplierKey.moneyMultiplier.defaultValue)
    @ViewState<String> private var materialFactor = String(format: "%g", Hades2MultiplierKey.resourceMultiplier.defaultValue)
    @ViewState<String> private var gameSpeedInput = String(Hades2MultiplierKey.gameSpeed.defaultValue)
    @ViewState<String?> private var gameSpeedPreview = nil
    @ViewState<String> private var rerollAmount = ""
    @ViewState<Bool> private var rerollsInitialized = false
    @ViewState<String> private var exactSearch = ""
    @ViewState<String> private var exactSourceSelection = ""
    @ViewState<String> private var traitSearch = ""
    @ViewState<String> private var managedTraitSelection = ""
    @ViewState<[String: String]> private var traitLevelInputs = [:]
    @ViewState<[String: String]> private var traitRarityInputs = [:]
    @ViewState<String> private var traitRemainingUsesInput = ""
    @ViewState<String> private var graspLimit = ""
    @ViewState<String> private var dodgeChance = ""
    @ViewState<String> private var critChance = ""
    @ViewState<String> private var chargeSpeed = ""
    @ViewState<String> private var moveSpeed = ""
    @ViewState<String> private var sprintSpeed = ""
    @ViewState<String> private var dashSpeed = ""
    @ViewState<String> private var attackSpeed = ""
    @ViewState<String> private var manaRegen = ""
    @ViewState<String> private var enemyDamage = "100"
    @ViewState<String> private var enemyHealth = "100"
    @ViewState<Bool> private var statsInitialized = false
    @ViewState<[String: String]> private var elementInputs = [:]
    @ViewState<Bool> private var elementsInitialized = false

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

    /// Resolve one Hades presentation key against the live Host language.
    private func text(_ key: String) -> String {
        // Some shell actions the module hosts (Disable All) keep their Host key
        // and Host resource, so a non-Hades prefix must resolve through the Host
        // table rather than being looked up as a Hades key.
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    /// Resolve a presentation token through the owner of its namespace.
    ///
    /// Hades tokens stay module-owned; Host tokens (including Core Time Warp
    /// failures) resolve through Host.strings with the same argument channel.
    private func resolved(_ token: TrainerTextToken) -> String {
        Hades2GameModule.resolveText(
            key: token.key,
            arguments: token.arguments,
            localization: localization
        )
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
        let localized = Hades2GameModule.presentationText(
            key: key,
            arguments: [],
            language: localization.language
        )
        return Hades2GameModule.presentationText(
            key: "hades2.element.generic",
            arguments: [localized == key ? element.name : localized],
            language: localization.language
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

    @ViewBuilder
    private var statusAndSessionSection: some View {
        TrainerSectionHeader(title: text("hades2.section.runData"), icon: Hades2WorkbenchSection.values.icon) {
            TrainerDisclosureButton(isExpanded: $model.numericControlsExpanded,
                expandTitle: text("hades2.section.expand"), collapseTitle: text("hades2.section.collapse"))
                .accessibilityIdentifier("hades2.numericDisclosure")
        }
        .trainerSectionTarget(Hades2WorkbenchSection.values.id)
        sessionStatsPanel
    }

    private var commonSection: some View {
        TrainerSection(title: text("hades2.section.common"), icon: Hades2WorkbenchSection.common.icon) {
            VStack(spacing: 1) {
                ForEach(Hades2WorkbenchCatalog.shortcutActions(in: .common).filter { $0.commonFeatureIcon != nil }) { action in
                    if let key = action.featureKey, let icon = action.commonFeatureIcon {
                        let enabled = model.isFeatureEnabled(key)
                        featureRow(text(action.presentationKey), key: key, icon: icon,
                                   enabled: enabled, shortcut: action) {
                            model.feature(key, value: !model.isFeatureEnabled(key))
                        }
                        .help(action.commonFeatureHelpKey.map { text($0) } ?? "")
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
        Hades2GameModule.presentationText(
            key: key,
            arguments: arguments,
            language: localization.language
        )
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
        guard force || focusedField != .traitRemainingUses else { return }
        guard let trait = managedCurrentRunTrait else {
            traitRemainingUsesInput = ""
            return
        }
        traitRemainingUsesInput = renderedTraitRemainingUses(trait)
    }

    private func canApplyTraitRemainingUses(_ trait: CurrentRunTrait) -> Bool {
        guard model.canMutateTraits, trait.canSetRemainingUses,
              let target = Int(traitRemainingUsesInput.trimmingCharacters(in: .whitespacesAndNewlines)),
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
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Label(text("hades2.traits.manager"), systemImage: TrainerSemanticIcon.Concept.controls)
                    .font(.subheadline.weight(.medium))
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
                .trainerPickerWidth(.expanding)
                .disabled(currentRunTraitPickerSections.allSatisfy({ $0.items.isEmpty }))

                TrainerSearchField(
                    text: $traitSearch,
                    placeholder: text("hades2.traits.search"),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(width: TraitManagerLayout.searchWidth)
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
                TrainerTextField(
                    title: text("hades2.traits.remainingUses"),
                    text: $traitRemainingUsesInput,
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
                .frame(width: 58)
                .disabled(!model.canMutateTraits || !trait.canSetRemainingUses)

                TrainerSecondaryActionButton(
                    title: text("hades2.traits.apply"),
                    enabled: canApplyTraitRemainingUses(trait)
                ) {
                    model.setTraitRemainingUses(
                        trait,
                        targetRemainingUses: traitRemainingUsesInput
                    )
                }

                TrainerSecondaryActionButton(
                    title: text("hades2.traits.expireNow"),
                    enabled: model.canMutateTraits && trait.canExpire
                ) {
                    model.expireTrait(trait)
                }
            }
        } else if trait.canAdvanceLifecycle {
            TrainerSecondaryActionButton(
                title: text("hades2.traits.chaos.advance"),
                enabled: model.canMutateTraits
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
        HStack(spacing: TraitManagerLayout.rowSpacing) {
            HStack(spacing: 6) {
                Text(text("hades2.traits.levelLabel"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(width: 42, alignment: .trailing)

                if let trait {
                    TrainerTextField(title: "—", text: traitLevelInput(trait), accessibilityLabel: text("hades2.traits.targetLevel"),
                        onCommit: { completion in
                            guard completion.changed else { return completion.text }
                            let raw = completion.text.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard let level = Int(raw), level > trait.level, level <= 999_999 else {
                                return completion.rejected(message: text("hades2.input.invalid"))
                            }
                            return String(level)
                        })
                        .id(trait.id)
                        .frame(width: 58)
                        .disabled(!model.canMutateTraits || !trait.canIncreaseLevel)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyLevel"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: canApplyTraitLevel(trait)
                    ) {
                        model.setTraitLevel(trait, targetLevel: traitLevelInput(trait).wrappedValue)
                    }
                } else {
                    TrainerTextField(title: "—", text: .constant(""), accessibilityLabel: text("hades2.traits.targetLevel"))
                        .frame(width: 58)
                        .disabled(true)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyLevel"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: false,
                        action: {}
                    )
                }
            }
            .frame(width: TraitManagerLayout.levelControlsWidth(compactActionWidth: theme.compactActionWidth), alignment: .trailing)

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
                    .trainerPickerWidth(.compactValue)
                    .disabled(!model.canMutateTraits || !trait.canSetRarity)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyRarity"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: canApplyTraitRarity(trait)
                    ) {
                        model.setTraitRarity(trait, rarity: traitRarityInput(trait).wrappedValue)
                    }
                } else {
                    Picker(text("hades2.traits.targetRarity"), selection: .constant("")) {
                        Text("—").tag("")
                    }
                    .labelsHidden()
                    .lineLimit(1)
                    .trainerPickerWidth(.compactValue)
                    .disabled(true)

                    TrainerSecondaryActionButton(
                        title: text("hades2.traits.applyRarity"),
                        systemImage: TrainerSemanticIcon.Action.apply,
                        enabled: false,
                        action: {}
                    )
                }
            }
            .frame(width: TraitManagerLayout.rarityControlsWidth(compactActionWidth: theme.compactActionWidth, pickerWidth: theme.pickerCompactWidth), alignment: .trailing)

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
            .frame(width: TraitManagerLayout.removeControlWidth)
            .disabled(trait == nil || !model.canMutateTraits || trait?.canRemove != true)
        }
        .frame(width: TraitManagerLayout.commonControlsWidth(compactActionWidth: theme.compactActionWidth, pickerWidth: theme.pickerCompactWidth), alignment: .trailing)
    }

    private var resourceSection: some View {
        TrainerSection(title: text("hades2.section.resourcesAndGathering"), icon: Hades2WorkbenchSection.resources.icon) {
            resourcePanel
            Hades2GatheringPanel(model: model)
            TrainerLabeledControlRow(
                title: text("hades2.garden.title"), icon: Hades2WorkbenchIcon.garden,
                tint: model.canMatureGarden ? theme.accent : theme.inactive,
                emphasized: model.canMatureGarden
            ) {
                TrainerShortcutBadgeSlot(text: model.shortcutText(.matureGarden))
                TrainerSecondaryActionButton(title: text("hades2.garden.matureNow"),
                    systemImage: ShortcutAction.matureGarden.icon,
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
            nextRoomRewardPanel
            nextOccurrencePanel
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

    @ViewBuilder
    private var gameSpeedPanel: some View {
        TrainerDisclosure(isExpanded: model.featureSupport["gameSpeed"] == true) {
            TrainerLabeledControlRow(
                title: text("hades2.gameSpeed.title"), icon: TrainerSemanticIcon.Concept.timeScale,
                tint: model.canEditDesired ? theme.accent : theme.inactive,
                emphasized: model.canEditDesired
            ) {
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: String(Hades2MultiplierKey.gameSpeed.defaultValue),
                    accessibilityLabel: text("hades2.gameSpeed.a11y"),
                    width: 62,
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
            .trainerGroupedRows()
        }
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
            spellCharge: model.spellCharge
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
            nextRoomReward: model.nextRoomReward,
            nextOccurrenceTarget: model.nextOccurrenceTarget,
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

        if !coinsInitialized, let value = snapshot.money {
            coins = number(value)
            coinsInitialized = true
        } else if focusedField != .coins, let value = snapshot.money {
            coins = number(value)
        }

        if !rerollsInitialized, let value = snapshot.rerolls {
            rerollAmount = number(value)
            rerollsInitialized = true
        } else if focusedField != .rerolls, let value = snapshot.rerolls {
            rerollAmount = number(value)
        }

        if !vitalsInitialized,
           let health = snapshot.health,
           let maxHealth = snapshot.maxHealth,
           let mana = snapshot.mana,
           let maxMana = snapshot.maxMana,
           let armor = snapshot.armor {
            healthCurrent = number(health)
            healthMaximum = number(maxHealth)
            manaCurrent = number(mana)
            manaMaximum = number(maxMana)
            armorCurrent = number(armor)
            spellCharge = number(snapshot.spellCharge)
            vitalsInitialized = true
        } else if vitalsInitialized {
            if focusedField != .healthCurrent, let value = snapshot.health { healthCurrent = number(value) }
            if focusedField != .healthMax, let value = snapshot.maxHealth { healthMaximum = number(value) }
            if focusedField != .manaCurrent, let value = snapshot.mana { manaCurrent = number(value) }
            if focusedField != .manaMax, let value = snapshot.maxMana { manaMaximum = number(value) }
            if focusedField != .armorCurrent, let value = snapshot.armor { armorCurrent = number(value) }
            if focusedField != .spellCharge, let value = snapshot.spellCharge { spellCharge = number(value) }
        }
    }

    private func syncStatSnapshot(_ snapshot: Hades2ViewStatSnapshot) {
        guard model.connected else { return }
        if !statsInitialized {
            if let value = snapshot.grasp { graspLimit = number(value) }
            if let value = snapshot.dodge { dodgeChance = compactNumber(value) }
            if let value = snapshot.crit { critChance = compactNumber(value) }
            if let value = snapshot.chargeSpeed { chargeSpeed = compactNumber(value) }
            if let value = snapshot.moveSpeed { moveSpeed = compactNumber(value) }
            if let value = snapshot.sprintSpeed { sprintSpeed = compactNumber(value) }
            if let value = snapshot.dashSpeed { dashSpeed = compactNumber(value) }
            if let value = snapshot.attackSpeed { attackSpeed = compactNumber(value) }
            if let value = snapshot.manaRegen { manaRegen = compactNumber(value) }
            if let value = snapshot.enemyDamage { enemyDamage = compactNumber(value) }
            if let value = snapshot.enemyHealth { enemyHealth = compactNumber(value) }
            statsInitialized = true
            return
        }

        if focusedField != .grasp, let value = snapshot.grasp { graspLimit = number(value) }
        if focusedField != .dodge, let value = snapshot.dodge { dodgeChance = compactNumber(value) }
        if focusedField != .crit, let value = snapshot.crit { critChance = compactNumber(value) }
        if focusedField != .chargeSpeed, let value = snapshot.chargeSpeed { chargeSpeed = compactNumber(value) }
        if focusedField != .moveSpeed, let value = snapshot.moveSpeed { moveSpeed = compactNumber(value) }
        if focusedField != .sprintSpeed, let value = snapshot.sprintSpeed { sprintSpeed = compactNumber(value) }
        if focusedField != .dashSpeed, let value = snapshot.dashSpeed { dashSpeed = compactNumber(value) }
        if focusedField != .attackSpeed, let value = snapshot.attackSpeed { attackSpeed = compactNumber(value) }
        if focusedField != .manaRegen, let value = snapshot.manaRegen { manaRegen = compactNumber(value) }
        if focusedField != .enemyDamage, let value = snapshot.enemyDamage { enemyDamage = compactNumber(value) }
        if focusedField != .enemyHealth, let value = snapshot.enemyHealth { enemyHealth = compactNumber(value) }
    }

    private func syncConfigSnapshot(_ snapshot: Hades2ViewConfigSnapshot) {
        model.selectedNextRoomReward = snapshot.nextRoomReward ?? ""
        model.selectedNextOccurrenceTarget = snapshot.nextOccurrenceTarget ?? ""
        syncElementInputs(snapshot.elements)
        if focusedField != .damageMultiplier { multiplier = compactNumber(snapshot.damageMultiplier) }
        if focusedField != .moneyMultiplier { moneyFactor = compactNumber(snapshot.moneyMultiplier) }
        if focusedField != .resourceMultiplier { materialFactor = compactNumber(snapshot.resourceMultiplier) }
        if focusedField != .gameSpeed, gameSpeedPreview == nil {
            gameSpeedInput = speedNumber(snapshot.gameSpeed)
        }
    }

    private func syncElementInputs(_ values: [ElementCount]) {
        if !elementsInitialized {
            elementInputs = Dictionary(uniqueKeysWithValues: values.map { ($0.id, number($0.count)) })
            elementsInitialized = true
            return
        }

        for item in values where focusedField != .element(item.id) {
            elementInputs[item.id] = number(item.count)
        }
    }

    private func applyCatalogChanges(from oldValue: Hades2ViewCatalogSnapshot, to newValue: Hades2ViewCatalogSnapshot) {
        if oldValue.materialID != newValue.materialID
            || (oldValue.materialCount != newValue.materialCount && focusedField != .material) {
            materialAmount = newValue.materialCount.map { number($0) } ?? ""
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
        materialAmount = material.map { number($0.count) } ?? ""
    }

    private func resetEditorInputs() {
        coinsInitialized = false
        rerollsInitialized = false
        vitalsInitialized = false
        statsInitialized = false
        coins = ""
        rerollAmount = ""
        materialAmount = ""
        healthCurrent = ""
        healthMaximum = ""
        manaCurrent = ""
        manaMaximum = ""
        armorCurrent = ""
        spellCharge = ""
        gameSpeedPreview = nil
        gameSpeedInput = String(Hades2MultiplierKey.gameSpeed.defaultValue)
        multiplier = String(format: "%g", Hades2MultiplierKey.damageMultiplier.defaultValue)
        moneyFactor = String(format: "%g", Hades2MultiplierKey.moneyMultiplier.defaultValue)
        materialFactor = String(format: "%g", Hades2MultiplierKey.resourceMultiplier.defaultValue)
        graspLimit = ""
        dodgeChance = ""
        critChance = ""
        chargeSpeed = ""
        moveSpeed = ""
        sprintSpeed = ""
        dashSpeed = ""
        attackSpeed = ""
        manaRegen = ""
        enemyDamage = "100"
        enemyHealth = "100"
        elementInputs = [:]
        elementsInitialized = false
        traitRemainingUsesInput = ""
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
            text("hades2.vital.health"), icon: TrainerSemanticIcon.Concept.vitality, current: $healthCurrent, maximum: $healthMaximum,
            currentField: .healthCurrent, maxField: .healthMax, color: .pink,
            vital: "health", locked: model.healthLocked
        )
        editableVitalMetric(
            text("hades2.vital.mana"), icon: TrainerSemanticIcon.Concept.energy, current: $manaCurrent, maximum: $manaMaximum,
            currentField: .manaCurrent, maxField: .manaMax, color: .cyan,
            vital: "mana", locked: model.manaLocked
        )
        editableAmountMetric(
            text("hades2.vital.runGold"), icon: TrainerSemanticIcon.Concept.currency, text: $coins, focus: .coins,
            color: .yellow, locked: model.moneyLocked, enabled: model.canSetResource,
            edit: .resource("Money"), lockEnabled: !model.infiniteMoney
        ) {
            model.lockResource("Money", locked: !model.moneyLocked)
        }
        editableAmountMetric(
            text("hades2.vital.armor"), icon: TrainerSemanticIcon.Concept.defense, text: $armorCurrent, focus: .armorCurrent,
            color: theme.warning, locked: model.armorLocked, enabled: model.canSetVital("armor"),
            edit: .vital("armor", field: "current")
        ) {
            model.lockVital("armor", locked: !model.armorLocked)
        }
    }

    @ViewBuilder
    private var expandedSessionMetrics: some View {
        damageMetric
        editableStatMetric(text("hades2.stat.grasp"), icon: Hades2WorkbenchIcon.grasp, stat: "grasp", text: $graspLimit, focus: .grasp, suffix: "", locked: model.graspLocked)
        editableAmountMetric(
            text("hades2.metric.rerolls"), icon: TrainerSemanticIcon.Concept.randomize, text: $rerollAmount, focus: .rerolls,
            color: accent, locked: model.rerollsLocked, enabled: model.canSetRerolls,
            edit: .rerolls, lockEnabled: !model.infiniteRerolls
        ) {
            model.lockRerolls(!model.rerollsLocked)
        }
        editableCounterMetric(
            text("hades2.metric.spellCharge"), icon: Hades2WorkbenchIcon.spellCharge, text: $spellCharge,
            focus: .spellCharge, color: .purple,
            detail: model.spellChargeCost.map { cost in
                    Hades2GameModule.presentationText(key: "hades2.metric.cost", arguments: [number(cost)], language: localization.language)
                } ?? nil,
            edit: .counter("spellCharge")
        )
        editableStatMetric(text("hades2.stat.dodge"), icon: TrainerSemanticIcon.Concept.defense, stat: "dodge", text: $dodgeChance, focus: .dodge, suffix: "%", locked: model.dodgeLocked)
        editableStatMetric(text("hades2.stat.crit"), icon: TrainerSemanticIcon.Concept.precision, stat: "crit", text: $critChance, focus: .crit, suffix: "%", locked: model.critLocked)
        editableStatMetric(text("hades2.stat.enemyDamage"), icon: TrainerSemanticIcon.Concept.impact, stat: "enemyDamage", text: $enemyDamage, focus: .enemyDamage, suffix: "%", locked: model.enemyDamageLocked)
        editableStatMetric(text("hades2.stat.enemyHealth"), icon: TrainerSemanticIcon.Concept.vitality, stat: "enemyHealth", text: $enemyHealth, focus: .enemyHealth, suffix: "%", locked: model.enemyHealthLocked)
        editableStatMetric(text("hades2.stat.chargeSpeed"), icon: TrainerSemanticIcon.Concept.timer, stat: "chargeSpeed", text: $chargeSpeed, focus: .chargeSpeed, suffix: "%", locked: model.chargeSpeedLocked)
        editableStatMetric(text("hades2.stat.moveSpeed"), icon: TrainerSemanticIcon.Concept.movement, stat: "moveSpeed", text: $moveSpeed, focus: .moveSpeed, suffix: "%", locked: model.moveSpeedLocked)
        editableStatMetric(text("hades2.stat.sprintSpeed"), icon: Hades2WorkbenchIcon.sprintSpeed, stat: "sprintSpeed", text: $sprintSpeed, focus: .sprintSpeed, suffix: "%", locked: model.sprintSpeedLocked)
        editableStatMetric(text("hades2.stat.dashSpeed"), icon: TrainerSemanticIcon.Concept.dash, stat: "dashSpeed", text: $dashSpeed, focus: .dashSpeed, suffix: "%", locked: model.dashSpeedLocked)
        editableStatMetric(text("hades2.stat.attackSpeed"), icon: TrainerSemanticIcon.Concept.actionSpeed, stat: "attackSpeed", text: $attackSpeed, focus: .attackSpeed, suffix: "%", locked: model.attackSpeedLocked)
        editableStatMetric(text("hades2.stat.manaRegen"), icon: TrainerSemanticIcon.Concept.energy, stat: "manaRegen", text: $manaRegen, focus: .manaRegen, suffix: "/s", locked: model.manaRegenLocked)
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
        TrainerMultiplierMetricCard(
            title: text("hades2.feature.damageMultiplier"), icon: TrainerSemanticIcon.Concept.impact,
            text: $multiplier, focus: $focusedField, focusValue: .damageMultiplier,
            suffix: "×", editable: model.canEditDesired,
            onCommit: completing(.multiplier("damageMultiplier"))
        )
    }

    private var boonRarityPanel: some View {
        Hades2BoonRarityPanel(model: model)
    }

    private var nextRoomRewardPanel: some View {
        TrainerLabeledControlRow(
            title: text("hades2.nextRoom.title"), icon: TrainerSemanticIcon.Context.doorway,
            tint: model.canEditDesired ? theme.accent : theme.inactive,
            emphasized: model.canEditDesired
        ) {
            Picker(text("hades2.nextRoom.title"), selection: $model.selectedNextRoomReward) {
                Text(text("hades2.nextRoom.noOverride")).tag("")
                Section(text("hades2.nextRoom.standard")) {
                    Text(rewardLabel("RoomMoneyDrop")).tag("RoomMoneyDrop")
                    Text(rewardLabel("MetaCardPointsCommonDrop")).tag("MetaCardPointsCommonDrop")
                    Text(rewardLabel("MemPointsCommonDrop")).tag("MemPointsCommonDrop")
                    Text(rewardLabel("MetaCurrencyDrop")).tag("MetaCurrencyDrop")
                    Text(rewardLabel("MaxHealthDrop")).tag("MaxHealthDrop")
                    Text(rewardLabel("MaxManaDrop")).tag("MaxManaDrop")
                    Text(rewardLabel("StackUpgrade")).tag("StackUpgrade")
                    Text(rewardLabel("WeaponUpgrade")).tag("WeaponUpgrade")
                    Text(rewardLabel("SpellDrop")).tag("SpellDrop")
                }
                Section(text("hades2.nextRoom.olympians")) {
                    ForEach(olympianBoons) { boon in Text(boon.englishName.isEmpty ? boon.name : "\(boon.name) · \(boon.englishName)").tag(boon.id) }
                }
            }
            .labelsHidden().trainerPickerWidth(.rowAction).disabled(!model.canEditDesired)
            TrainerShortcutBadge(text: model.shortcutText(.applyNextRoomReward))
            TrainerSecondaryActionButton(
                title: text("hades2.nextRoom.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: model.canEditDesired
            ) {
                model.setNextRoomReward(model.selectedNextRoomReward.isEmpty ? nil : model.selectedNextRoomReward)
            }
        }.trainerGroupedRows()
    }

    private var nextOccurrencePanel: some View {
        let characters = model.occurrenceTargets.filter { $0.kind == "character" }
        let shops = model.occurrenceTargets.filter { $0.kind == "shop" }
        return TrainerLabeledControlRow(
            title: text("hades2.occurrence.title"), icon: Hades2WorkbenchIcon.occurrence,
            tint: model.canEditDesired ? theme.accent : theme.inactive,
            emphasized: model.canEditDesired
        ) {
            if model.nextOccurrenceTarget != nil {
                Text(text("hades2.occurrence.pending"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Picker(text("hades2.occurrence.title"), selection: $model.selectedNextOccurrenceTarget) {
                Text(text("hades2.occurrence.noRequest")).tag("")
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
            .trainerPickerWidth(.rowAction)
            .disabled(!model.canEditDesired)
            TrainerShortcutBadgeSlot(text: model.shortcutText(.applyNextOccurrence))
            TrainerSecondaryActionButton(
                title: text("hades2.occurrence.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: model.canEditDesired
            ) {
                _ = model.setNextOccurrence(
                    model.selectedNextOccurrenceTarget.isEmpty
                        ? nil
                        : model.selectedNextOccurrenceTarget
                )
            }
        }
        .trainerGroupedRows()
    }

    private var resourcePanel: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            VStack(spacing: 1) {
                // The two gain multipliers are one family; keep them adjacent so the
                // shared "gain" meaning is visible instead of split around the editor.
                multiplierRow(text("hades2.feature.moneyMultiplier"), enabled: model.moneyMultiplierEnabled, actual: model.moneyMultiplier,
                    text: $moneyFactor, feature: "moneyMultiplier", toggle: .moneyMultiplierEnabled, shortcut: .moneyMultiplierEnabled)
                multiplierRow(text("hades2.feature.resourceMultiplier"), enabled: model.resourceMultiplierEnabled, actual: model.resourceMultiplier,
                    text: $materialFactor, feature: "resourceMultiplier", toggle: .resourceMultiplierEnabled, shortcut: .resourceMultiplierEnabled)
            }
            .trainerGroupedRows()
            TrainerResourceEditor(
                title: text("hades2.resource.materials"),
                icon: TrainerSemanticIcon.Concept.item,
                search: $search,
                selection: $selectedMaterial,
                amount: $materialAmount,
                sections: resourceGroups(filtered),
                enabled: model.canSetResource,
                locked: material?.locked ?? false,
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
                onLock: {
                    guard let material else { return }
                    model.lockResource(material.id, locked: !material.locked)
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

    private var boonAcquisitionPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                TrainerIconLabel(
                    title: text("hades2.spawn.exactBoons"),
                    icon: Hades2WorkbenchIcon.exactBoons,
                    tint: theme.accent,
                    emphasized: true
                )
                Spacer()
                TrainerSearchField(
                    text: $exactSearch,
                    placeholder: text("hades2.spawn.search"),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(maxWidth: 280)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(text("hades2.spawn.chaosPair"))
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                HStack(alignment: .bottom, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades2.spawn.chaosBlessing"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Picker(text("hades2.spawn.chaosBlessing"), selection: $model.selectedChaosBlessing) {
                            if chaosBlessingOptions.isEmpty {
                                Text(text("hades2.spawn.noItems")).tag("")
                            }
                            ForEach(chaosBlessingOptions) { option in
                                Text(exactItemLabel(option)).tag(option.id)
                            }
                        }
                        .labelsHidden()
                        .trainerPickerWidth(.expanding)
                        .disabled(!model.canAcquireChaosPair || chaosBlessingOptions.isEmpty)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades2.spawn.chaosCurse"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Picker(text("hades2.spawn.chaosCurse"), selection: $model.selectedChaosCurse) {
                            if chaosCurseOptions.isEmpty {
                                Text(text("hades2.spawn.noItems")).tag("")
                            }
                            ForEach(chaosCurseOptions) { option in
                                Text(exactItemLabel(option)).tag(option.id)
                            }
                        }
                        .labelsHidden()
                        .trainerPickerWidth(.expanding)
                        .disabled(!model.canAcquireChaosPair || chaosCurseOptions.isEmpty)
                    }

                    TrainerShortcutBadgeSlot(text: model.shortcutText(.acquireChaosPair))
                    TrainerSecondaryActionButton(
                        title: text("hades2.spawn.acquire"),
                        systemImage: TrainerSemanticIcon.Action.acquire,
                        enabled: model.canAcquireChaosPair
                            && chaosBlessingOptions.contains(where: { $0.id == model.selectedChaosBlessing })
                            && chaosCurseOptions.contains(where: { $0.id == model.selectedChaosCurse })
                    ) {
                        _ = model.acquireChaosPair(
                            blessingReward: model.selectedChaosBlessing,
                            curseReward: model.selectedChaosCurse
                        )
                    }
                }
            }
            .onAppear { repairChaosPairSelections() }
            .onChange(of: model.exactBoonOptions.map(\.id)) { _, _ in repairChaosPairSelections() }

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .bottom, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades2.spawn.exactSource"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                        .trainerPickerWidth(.expanding)
                        .disabled(!model.canAcquireExactReward || exactBoonSourceGroups.isEmpty)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text(text("hades2.spawn.exactTarget"))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Picker(text("hades2.spawn.exactTarget"), selection: exactItemSelection) {
                            if selectedExactItems.isEmpty || exactItemSelection.wrappedValue.isEmpty {
                                Text(text("hades2.spawn.noItems")).tag("")
                            }
                            ForEach(selectedExactItems) { option in
                                Text(exactItemLabel(option)).tag(option.id)
                            }
                        }
                        .labelsHidden()
                        .trainerPickerWidth(.expanding)
                        .disabled(!model.canAcquireExactReward || selectedExactItems.isEmpty)
                    }

                    TrainerShortcutBadgeSlot(text: model.shortcutText(.acquireExactBoon))
                    TrainerSecondaryActionButton(
                        title: text("hades2.spawn.acquire"),
                        systemImage: TrainerSemanticIcon.Action.acquire,
                        enabled: model.canAcquireExactReward
                            && selectedExactItems.contains(where: { $0.id == model.selectedExactBoon })
                    ) {
                        _ = model.acquireExactBoon(model.selectedExactBoon)
                    }
                }
            }
            .onAppear { repairExactSourceSelection() }
            .onChange(of: exactSearch) { _, _ in repairExactSourceSelection() }
            .onChange(of: model.exactBoonOptions.map(\.id)) { _, _ in repairExactSourceSelection() }
        }.trainerPanel()
    }

    private var currentRunEffectsPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                TrainerIconLabel(
                    title: text("hades2.spawn.purgingPool"),
                    icon: Hades2WorkbenchIcon.purge,
                    tint: model.canOpenSellTraits ? theme.accent : theme.inactive,
                    emphasized: model.canOpenSellTraits
                )
                Spacer()
                TrainerShortcutBadgeSlot(text: model.shortcutText(.openSellTraits))
                TrainerSecondaryActionButton(
                    title: text("hades2.spawn.open"),
                    systemImage: ShortcutAction.openSellTraits.icon,
                    enabled: model.canOpenSellTraits
                ) { _ = model.openSellTraits() }
            }
            if model.connected {
                Divider()
                currentRunTraitsPanel
            }
        }.trainerPanel()
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
            itemLabel: { option in
                option.englishName.isEmpty ? option.name : "\(option.name) · \(option.englishName)"
            },
            onAction: onAction
        )
    }

    private func multiplierRow(_ title: String, enabled: Bool, actual: Double, text: Binding<String>, feature: String, toggle: Hades2FeatureKey, shortcut: ShortcutAction? = nil) -> some View {
        TrainerFeatureMultiplierRow(
            title: title,
            icon: feature == "moneyMultiplier" ? TrainerSemanticIcon.Concept.currency : TrainerSemanticIcon.Section.inventory,
            state: model.featurePresentation(toggle, enabled: enabled).trainerControlState(using: theme, localization: localization),
            text: text,
            onCommit: completing(.multiplier(feature)),
            onEditingChanged: tracking(feature == "moneyMultiplier" ? .moneyMultiplier : .resourceMultiplier),
            shortcutText: shortcut.map { model.shortcutText($0) }
        ) {
            model.feature(toggle, value: !enabled)
        }
    }

    private var management: some View {
        TrainerSection(title: text("hades2.section.management"), icon: Hades2WorkbenchSection.management.icon) {
            Hades2ManagementUtilities(
                model: model,
                openSaveEditor: {
                    toolWindows.open("hades2-save-editor", text("hades2.saveEditor.title")) {
                        Hades2GameModule.makeSaveEditorWindow(model: model)
                    }
                }
            )
        }
    }

    private func featureRow(_ title: String, key: Hades2FeatureKey, icon: String, enabled: Bool, shortcut: ShortcutAction? = nil, action: @escaping () -> Void) -> some View {
        TrainerFeatureToggleRow(
            title: title,
            icon: icon,
            state: model.featurePresentation(key, enabled: enabled).trainerControlState(using: theme, localization: localization),
            shortcutText: shortcut.map { model.shortcutText($0) },
            action: action
        )
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

    private func editableStatMetric(_ title: String, icon: String, stat: String, text: Binding<String>, focus: EditField,
        suffix: String, locked: Bool) -> some View {
        TrainerStatMetricCard(
            title: title,
            icon: icon,
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
        let binding = Binding<String>(
            get: { elementInputs[element.id] ?? number(element.count) },
            set: {
                elementInputs[element.id] = $0
            }
        )
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
