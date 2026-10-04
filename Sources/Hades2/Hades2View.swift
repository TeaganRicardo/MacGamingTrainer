import Foundation
import SwiftUI
import AppKit

// Select the property-wrapper type explicitly: CLT does not ship SwiftUIMacros.
private typealias ViewState<Value> = SwiftUI.State<Value>

struct Hades2TrainerView: View {
    private enum EditField: Hashable {
        case healthCurrent, healthMax, manaCurrent, manaMax, armorCurrent, spellCharge
        case coins, material, rerolls, damageMultiplier, moneyMultiplier, resourceMultiplier, boonRarity, gameSpeed
        case grasp, dodge, crit, chargeSpeed, moveSpeed, sprintSpeed, dashSpeed, attackSpeed, manaRegen, enemyDamage, enemyHealth
        case traitRemainingUses
        case element(String)
    }

    private enum TraitManagerLayout {
        static let levelControlsWidth: CGFloat = 174
        static let rarityControlsWidth: CGFloat = 224
        static let removeControlWidth: CGFloat = 106
        static let commonControlsWidth: CGFloat = 528
        static let searchWidth: CGFloat = 260
    }

    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @FocusState private var focusedField: EditField?

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
    @ViewState<String> private var multiplier = "2"
    @ViewState<Bool> private var statsExpanded = false
    @ViewState<Bool> private var profileManager = false
    @ViewState<Bool> private var diagnosticSheet = false
    @ViewState<String> private var moneyFactor = "2"
    @ViewState<String> private var materialFactor = "2"
    @ViewState<String> private var gameSpeedInput = "1.0"
    @ViewState<String?> private var gameSpeedPreview = nil
    @ViewState<String> private var rerollAmount = ""
    @ViewState<Bool> private var rerollsInitialized = false
    @ViewState<String> private var specialSearch = ""
    @ViewState<String> private var exactSearch = ""
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
    @ViewState<String> private var boonRarityFactor = "100"
    @ViewState<Bool> private var boonConfigInitialized = false
    @ViewState<Set<String>> private var editedConfigDrafts = []
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
    private var specialBoons: [BoonOption] {
        sortedBoons(model.specialRewardOptions.filter { specialSearch.isEmpty || $0.name.localizedCaseInsensitiveContains(specialSearch) || $0.englishName.localizedCaseInsensitiveContains(specialSearch) || $0.id.localizedCaseInsensitiveContains(specialSearch) || $0.category.localizedCaseInsensitiveContains(specialSearch) || $0.englishCategory.localizedCaseInsensitiveContains(specialSearch) || $0.englishSectionTitle.localizedCaseInsensitiveContains(specialSearch) })
    }
    private var exactBoons: [BoonOption] {
        sortedBoons(model.exactBoonOptions.filter {
            exactSearch.isEmpty
                || $0.name.localizedCaseInsensitiveContains(exactSearch)
                || $0.englishName.localizedCaseInsensitiveContains(exactSearch)
                || $0.targetID.localizedCaseInsensitiveContains(exactSearch)
                || $0.id.localizedCaseInsensitiveContains(exactSearch)
                || $0.sourceId.localizedCaseInsensitiveContains(exactSearch)
                || $0.sourceName.localizedCaseInsensitiveContains(exactSearch)
                || $0.sourceEnglishName.localizedCaseInsensitiveContains(exactSearch)
                || $0.category.localizedCaseInsensitiveContains(exactSearch)
                || $0.englishCategory.localizedCaseInsensitiveContains(exactSearch)
        })
    }
    private var material: MaterialResource? { filtered.first { $0.id == selectedMaterial } }

    private func resourceGroups(_ options: [MaterialResource]) -> [TrainerPickerSection<MaterialResource>] {
        var titles: [String] = []
        var buckets: [String: [MaterialResource]] = [:]
        for item in options.sorted(by: { $0.sortOrder < $1.sortOrder }) {
            let title = item.sectionTitle.isEmpty ? text("hades2.resource.sectionDefault") : item.sectionTitle
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
            combatSection
            buildSection
            resourceSection
            spawnSection
            management
        }
    }

    @ViewBuilder
    private var statusAndSessionSection: some View {
        messageSlot
        TrainerSectionHeader(title: text("hades2.section.runData"), icon: "gauge.with.dots.needle.67percent") {
            Button { withAnimation(.easeInOut(duration: 0.18)) { statsExpanded.toggle() } } label: {
                HStack(spacing: 5) {
                    Text(statsExpanded ? text("hades2.section.collapse") : text("hades2.section.expand"))
                    Image(systemName: statsExpanded ? "chevron.up" : "chevron.down")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
        sessionStatsPanel
    }

    private var combatSection: some View {
        TrainerSection(title: text("hades2.section.combat"), icon: "shield.checkered") {
            VStack(spacing: 1) {
                featureRow(text("hades2.feature.invincibility"), key: .invincibility, icon: "shield.fill", enabled: model.invincibility, shortcut: .invincibility) { model.feature(.invincibility, value: !model.invincibility) }
                featureRow(text("hades2.feature.infiniteHealth"), key: .infiniteHealth, icon: "heart.fill", enabled: model.infiniteHealth, shortcut: .infiniteHealth) { model.feature(.infiniteHealth, value: !model.infiniteHealth) }
                featureRow(text("hades2.feature.infiniteMana"), key: .infiniteMana, icon: "sparkles", enabled: model.infiniteMana, shortcut: .infiniteMana) { model.feature(.infiniteMana, value: !model.infiniteMana) }
                featureRow(text("hades2.feature.instantCastCooldown"), key: .instantCastCooldown, icon: "circle.dotted.circle", enabled: model.instantCastCooldown, shortcut: .instantCastCooldown) { model.feature(.instantCastCooldown, value: !model.instantCastCooldown) }
                featureRow(text("hades2.feature.hexAlwaysReady"), key: .hexAlwaysReady, icon: "moon.stars.fill", enabled: model.hexAlwaysReady, shortcut: .hexAlwaysReady) { model.feature(.hexAlwaysReady, value: !model.hexAlwaysReady) }
                featureRow(text("hades2.feature.infiniteAmmo"), key: .infiniteAmmo, icon: "scope", enabled: model.infiniteAmmo, shortcut: .infiniteAmmo) { model.feature(.infiniteAmmo, value: !model.infiniteAmmo) }
                featureMultiplierRow(
                    text("hades2.feature.damageMultiplier"),
                    key: .damageEnabled,
                    icon: "bolt.fill",
                    enabled: model.damageEnabled,
                    text: configIntentBinding($multiplier, key: "damageMultiplier") { model.setMultiplier("damageMultiplier", text: $0) },
                    shortcut: .damageEnabled
                ) {
                    model.feature(.damageEnabled, value: !model.damageEnabled)
                }
            }
            .trainerGroupedRows()

            gameSpeedPanel

            VStack(spacing: 1) {
                featureRow(text("hades2.feature.autoMiniGames"), key: .autoMiniGames, icon: "gamecontroller.fill", enabled: model.autoMiniGames, shortcut: .autoMiniGames) { model.feature(.autoMiniGames, value: !model.autoMiniGames) }
                featureRow(text("hades2.feature.gardenQoL"), key: .gardenQoL, icon: "leaf.fill", enabled: model.gardenQoL, shortcut: .gardenQoL) { model.feature(.gardenQoL, value: !model.gardenQoL) }
            }
            .trainerGroupedRows()
        }
    }

    private var buildSection: some View {
        TrainerSection(title: text("hades2.section.build"), icon: "chart.bar.xaxis") {
            metaStatPanel
            boonRarityPanel
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
            return localizedFamily == presentationKey ? "Arcana" : localizedFamily
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
        guard model.canOpenNativeBoonScreen, trait.canSetRemainingUses,
              let target = Int(traitRemainingUsesInput.trimmingCharacters(in: .whitespacesAndNewlines)),
              (1...999_999).contains(target) else { return false }
        return trait.remainingUses != Double(target)
    }

    private func canApplyTraitLevel(_ trait: CurrentRunTrait) -> Bool {
        guard model.canOpenNativeBoonScreen, trait.canIncreaseLevel,
              let target = Int(traitLevelInput(trait).wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines))
        else { return false }
        return target > trait.level && target <= 999_999
    }

    private func canApplyTraitRarity(_ trait: CurrentRunTrait) -> Bool {
        let target = traitRarityInput(trait).wrappedValue
        return model.canOpenNativeBoonScreen
            && trait.canSetRarity
            && trait.availableRarities.contains(target)
            && target != trait.rarity
    }

    private var currentRunTraitsPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Label(text("hades2.traits.manager"), systemImage: "slider.horizontal.3")
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
                .frame(maxWidth: .infinity)
                .disabled(currentRunTraitPickerSections.allSatisfy({ $0.items.isEmpty }))

                TextField(text("hades2.traits.search"), text: $traitSearch)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: TraitManagerLayout.searchWidth)
            }

            HStack(spacing: 12) {
                if let trait = managedCurrentRunTrait {
                    currentRunTraitContextualControls(trait)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    currentRunTraitCommonControls(trait)
                } else {
                    Spacer(minLength: 0)
                    currentRunTraitCommonControls(nil)
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
        .onChange(of: focusedField) { oldValue, newValue in
            if oldValue == .traitRemainingUses && newValue != .traitRemainingUses {
                syncManagedTraitRemainingUsesInput(force: true)
            }
        }
    }

    @ViewBuilder
    private func currentRunTraitContextualControls(_ trait: CurrentRunTrait) -> some View {
        if trait.family == "temporary"
            && (trait.remainingUses != nil || trait.canSetRemainingUses || trait.canExpire) {
            HStack(spacing: 6) {
                Text(text("hades2.traits.remainingUses"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField(
                    text("hades2.traits.remainingUses"),
                    text: $traitRemainingUsesInput
                )
                .textFieldStyle(.roundedBorder)
                .focused($focusedField, equals: .traitRemainingUses)
                .frame(width: 58)
                .disabled(!model.canOpenNativeBoonScreen || !trait.canSetRemainingUses)

                Button(text("hades2.traits.apply")) {
                    model.setTraitRemainingUses(
                        trait,
                        targetRemainingUses: traitRemainingUsesInput
                    )
                }
                .buttonStyle(.bordered)
                .disabled(!canApplyTraitRemainingUses(trait))

                Button(text("hades2.traits.expireNow")) {
                    model.expireTrait(trait)
                }
                .buttonStyle(.bordered)
                .disabled(!model.canOpenNativeBoonScreen || !trait.canExpire)
            }
            .fixedSize(horizontal: true, vertical: false)
        } else if trait.canAdvanceLifecycle {
            Button(text("hades2.traits.chaos.advance")) {
                model.advanceTraitLifecycle(trait)
            }
            .buttonStyle(.bordered)
            .disabled(!model.canOpenNativeBoonScreen)
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
        HStack(spacing: 12) {
            HStack(spacing: 6) {
                Text(text("hades2.traits.targetLevel"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 42, alignment: .trailing)

                if let trait {
                    TextField(text("hades2.traits.targetLevel"), text: traitLevelInput(trait))
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 58)
                        .disabled(!model.canOpenNativeBoonScreen || !trait.canIncreaseLevel)

                    Button(text("hades2.traits.apply")) {
                        model.setTraitLevel(trait, targetLevel: traitLevelInput(trait).wrappedValue)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 62)
                    .disabled(!canApplyTraitLevel(trait))
                } else {
                    TextField(text("hades2.traits.targetLevel"), text: .constant(""))
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 58)
                        .disabled(true)

                    Button(text("hades2.traits.apply")) {}
                        .buttonStyle(.bordered)
                        .frame(width: 62)
                        .disabled(true)
                }
            }
            .frame(width: TraitManagerLayout.levelControlsWidth, alignment: .trailing)

            HStack(spacing: 6) {
                Text(text("hades2.traits.targetRarity"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
                    .frame(width: 108)
                    .disabled(!model.canOpenNativeBoonScreen || !trait.canSetRarity)

                    Button(text("hades2.traits.apply")) {
                        model.setTraitRarity(trait, rarity: traitRarityInput(trait).wrappedValue)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 62)
                    .disabled(!canApplyTraitRarity(trait))
                } else {
                    Picker(text("hades2.traits.targetRarity"), selection: .constant("")) {
                        Text("—").tag("")
                    }
                    .labelsHidden()
                    .frame(width: 108)
                    .disabled(true)

                    Button(text("hades2.traits.apply")) {}
                        .buttonStyle(.bordered)
                        .frame(width: 62)
                        .disabled(true)
                }
            }
            .frame(width: TraitManagerLayout.rarityControlsWidth, alignment: .trailing)

            Button(role: .destructive) {
                guard let trait else { return }
                model.removeTrait(trait)
            } label: {
                Text(currentRunTraitRemovalLabel(trait))
                    .lineLimit(1)
                    .minimumScaleFactor(0.65)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .frame(width: TraitManagerLayout.removeControlWidth)
            .disabled(trait == nil || !model.canOpenNativeBoonScreen || trait?.canRemove != true)
        }
        .frame(width: TraitManagerLayout.commonControlsWidth, alignment: .trailing)
    }

    private var resourceSection: some View {
        TrainerSection(title: text("hades2.section.resources"), icon: "shippingbox.fill") {
            resourcePanel
        }
    }

    private var spawnSection: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            TrainerSection(title: text("hades2.section.spawn"), icon: "sparkles") {
                boonPanel
                nextRoomRewardPanel
            }
            TrainerSection(title: text("hades2.section.elements"), icon: "circle.hexagongrid.fill") {
                elementPanel
            }
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
                model.setGameSpeed($0)
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

    private func normalizeGameSpeedInput() {
        guard let raw = Double(gameSpeedInput), raw.isFinite else {
            gameSpeedInput = speedNumber(model.gameSpeed)
            return
        }
        let value = (raw * 10).rounded() / 10
        guard Hades2TrainerModel.gameSpeedInputRange.contains(value) else {
            gameSpeedInput = speedNumber(model.gameSpeed)
            return
        }
        gameSpeedInput = speedNumber(value)
    }

    @ViewBuilder
    private var gameSpeedPanel: some View {
        if model.featureSupport["gameSpeed"] == true {
            HStack(spacing: 10) {
                Text(text("hades2.gameSpeed.title")).font(.headline)
                Spacer(minLength: 12)
                TrainerNumberField(
                    text: gameSpeedInputBinding,
                    placeholder: "1.0",
                    width: 62,
                    enabled: model.canEditDesired
                )
                .focused($focusedField, equals: .gameSpeed)
                .onSubmit { normalizeGameSpeedInput() }
                Text("×").foregroundStyle(.secondary)
                TrainerMappedSlider(
                    value: gameSpeedSliderValue,
                    mapping: gameSpeedMapping,
                    accessibilityLabel: text("hades2.gameSpeed.a11y"),
                    accessibilityHint: text("hades2.gameSpeed.hint"),
                    enabled: model.canEditDesired,
                    onPreviewValue: { gameSpeedPreview = speedNumber($0) }
                )
                .frame(width: 200)
            }
            .trainerPanel()
        }
    }

    private var presentedContent: some View {
        rootContent
            .sheet(isPresented: $model.shortcutSettingsPresented) { Hades2ShortcutSettingsView(model: model) }
            .sheet(isPresented: $profileManager) { Hades2ProfileManagerView(model: model, isPresented: $profileManager) }
            .sheet(isPresented: $diagnosticSheet) { Hades2DiagnosticsView(model: model, isPresented: $diagnosticSheet) }
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
            boonRarityMultiplier: model.boonRarityMultiplier,
            nextRoomReward: model.nextRoomReward,
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
            olympianIDs: olympianBoons.map(\.id),
            pickupIDs: pickupRewards.map(\.id),
            specialIDs: specialBoons.map(\.id),
            exactIDs: exactBoons.map(\.id),
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
        if !boonConfigInitialized {
            boonRarityFactor = compactNumber(snapshot.boonRarityMultiplier)
            boonConfigInitialized = true
        } else if focusedField != .boonRarity {
            boonRarityFactor = compactNumber(snapshot.boonRarityMultiplier)
        }
        model.selectedNextRoomReward = snapshot.nextRoomReward ?? ""
        syncElementInputs(snapshot.elements)
        if !editedConfigDrafts.contains("damageMultiplier") { multiplier = compactNumber(snapshot.damageMultiplier) }
        if !editedConfigDrafts.contains("moneyMultiplier") { moneyFactor = compactNumber(snapshot.moneyMultiplier) }
        if !editedConfigDrafts.contains("resourceMultiplier") { materialFactor = compactNumber(snapshot.resourceMultiplier) }
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
        if oldValue.materialID != newValue.materialID {
            materialAmount = material.map { number($0.count) } ?? ""
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
        gameSpeedInput = "1.0"
        multiplier = "2"
        moneyFactor = "2"
        materialFactor = "2"
        boonRarityFactor = "100"
        boonConfigInitialized = false
        editedConfigDrafts.removeAll()
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
        let columns = Array(repeating: GridItem(.flexible(), spacing: 12), count: 4)
        return LazyVGrid(columns: columns, spacing: 12) {
            primarySessionMetrics
            if statsExpanded {
                expandedSessionMetrics
            }
        }
    }

    @ViewBuilder
    private var primarySessionMetrics: some View {
        editableVitalMetric(
            text("hades2.vital.health"), icon: "heart.fill", current: $healthCurrent, maximum: $healthMaximum,
            currentField: .healthCurrent, maxField: .healthMax, color: .pink,
            vital: "health", locked: model.healthLocked
        )
        editableVitalMetric(
            text("hades2.vital.mana"), icon: "sparkles", current: $manaCurrent, maximum: $manaMaximum,
            currentField: .manaCurrent, maxField: .manaMax, color: .cyan,
            vital: "mana", locked: model.manaLocked
        )
        editableAmountMetric(
            text("hades2.vital.runGold"), icon: "circle.hexagongrid.fill", text: $coins, focus: .coins,
            color: .yellow, locked: model.moneyLocked, enabled: model.canSetResource,
            onEdit: { model.setResource("Money", amount: $0) }
        ) {
            model.lockResource("Money", locked: !model.moneyLocked)
        }
        editableAmountMetric(
            text("hades2.vital.armor"), icon: "shield.lefthalf.filled", text: $armorCurrent, focus: .armorCurrent,
            color: theme.warning, locked: model.armorLocked, enabled: model.canSetVitals,
            onEdit: { model.setVital("armor", field: "current", text: $0) }
        ) {
            model.lockVital("armor", locked: !model.armorLocked)
        }
    }

    @ViewBuilder
    private var expandedSessionMetrics: some View {
        editableAmountMetric(
            text("hades2.metric.rerolls"), icon: "dice.fill", text: $rerollAmount, focus: .rerolls,
            color: accent, locked: model.rerollsLocked, enabled: model.canSetResource,
            onEdit: { model.setRerolls($0) }
        ) {
            model.lockRerolls(!model.rerollsLocked)
        }
        editableCounterMetric(
            text("hades2.metric.spellCharge"), icon: "moonphase.waxing.crescent", text: $spellCharge,
            focus: .spellCharge, color: .purple,
            detail: model.spellChargeCost.map { cost in
                    Hades2GameModule.presentationText(key: "hades2.metric.cost", arguments: [number(cost)], language: localization.language)
                } ?? nil,
            onEdit: { model.setCounter("spellCharge", text: $0) }
        )
        editableStatMetric(text("hades2.stat.dodge"), icon: "figure.run", stat: "dodge", text: $dodgeChance, focus: .dodge, suffix: "%", locked: model.dodgeLocked)
        editableStatMetric(text("hades2.stat.crit"), icon: "scope", stat: "crit", text: $critChance, focus: .crit, suffix: "%", locked: model.critLocked)
        editableStatMetric(text("hades2.stat.enemyDamage"), icon: "burst.fill", stat: "enemyDamage", text: $enemyDamage, focus: .enemyDamage, suffix: "%", locked: model.enemyDamageLocked)
        editableStatMetric(text("hades2.stat.enemyHealth"), icon: "heart.text.square.fill", stat: "enemyHealth", text: $enemyHealth, focus: .enemyHealth, suffix: "%", locked: model.enemyHealthLocked)
        editableStatMetric(text("hades2.stat.chargeSpeed"), icon: "timer", stat: "chargeSpeed", text: $chargeSpeed, focus: .chargeSpeed, suffix: "%", locked: model.chargeSpeedLocked)
        editableStatMetric(text("hades2.stat.moveSpeed"), icon: "figure.walk", stat: "moveSpeed", text: $moveSpeed, focus: .moveSpeed, suffix: "%", locked: model.moveSpeedLocked)
        editableStatMetric(text("hades2.stat.sprintSpeed"), icon: "hare.fill", stat: "sprintSpeed", text: $sprintSpeed, focus: .sprintSpeed, suffix: "%", locked: model.sprintSpeedLocked)
        editableStatMetric(text("hades2.stat.dashSpeed"), icon: "forward.end.fill", stat: "dashSpeed", text: $dashSpeed, focus: .dashSpeed, suffix: "%", locked: model.dashSpeedLocked)
        editableStatMetric(text("hades2.stat.attackSpeed"), icon: "bolt.fill", stat: "attackSpeed", text: $attackSpeed, focus: .attackSpeed, suffix: "%", locked: model.attackSpeedLocked)
        editableStatMetric(text("hades2.stat.manaRegen"), icon: "drop.circle.fill", stat: "manaRegen", text: $manaRegen, focus: .manaRegen, suffix: "/s", locked: model.manaRegenLocked)
    }

    private var elementPanel: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 12), count: max(model.elements.count, 1))
        return LazyVGrid(columns: columns, spacing: 12) {
            ForEach(model.elements) { element in
                elementMetric(element)
            }
        }
    }

    private var metaStatPanel: some View {
        VStack(spacing: 1) {
            statRow(text("hades2.stat.grasp"), stat: "grasp", text: $graspLimit, locked: model.graspLocked, suffix: "", focus: .grasp)
        }.trainerGroupedRows()
    }

    private func statRow(_ title: String, stat: String, text: Binding<String>, locked: Bool, suffix: String, focus: EditField) -> some View {
        TrainerInlineStatEditor(
            title: title,
            text: intentBinding(text) {
                if locked { model.setStat(stat, text: $0, locked: true) }
            },
            focus: $focusedField,
            focusValue: focus,
            suffix: suffix,
            locked: locked,
            supported: model.statSupport[stat] != false,
            available: model.statAvailable[stat] != false,
            editable: model.canSetStats,
            onLockChange: { model.setStat(stat, text: text.wrappedValue, locked: $0) }
        )
    }

    private var boonRarityPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Label(text("hades2.rarity.title"), systemImage: "star.circle.fill").font(.subheadline.weight(.semibold))
                Spacer()
                TrainerShortcutBadge(text: model.shortcutText(.boonRarityEnabled))
                TrainerToggleControl(
                    isOn: model.boonRarityEnabled,
                    enabled: model.canEditDesired,
                    tint: model.featurePresentation(.boonRarityEnabled, enabled: model.boonRarityEnabled).trainerControlState(using: theme, localization: localization).indicatorColor,
                    onChange: { model.feature(.boonRarityEnabled, value: $0) }
                )
            }
            HStack(spacing: 12) {
                Text(text("hades2.rarity.minimum")).foregroundStyle(.secondary)
                Picker(text("hades2.rarity.minimum"), selection: Binding(get: { model.boonRarityTarget }, set: { model.setBoonRarity(target: $0, multiplier: boonRarityFactor, forceLegendary: model.boonForceLegendary, forceDuo: model.boonForceDuo) })) {
                    Text(text("hades2.rarity.Common")).tag("Common")
                    Text(text("hades2.rarity.Rare")).tag("Rare")
                    Text(text("hades2.rarity.Epic")).tag("Epic")
                    Text(text("hades2.rarity.Heroic")).tag("Heroic")
                }.labelsHidden().frame(width: 150).disabled(!model.canEditDesired)
                Spacer()
                Text(text("hades2.rarity.multiplier")).foregroundStyle(.secondary)
                TrainerNumberField(
                    text: intentBinding($boonRarityFactor) {
                        model.setBoonRarity(
                            target: model.boonRarityTarget,
                            multiplier: $0,
                            forceLegendary: model.boonForceLegendary,
                            forceDuo: model.boonForceDuo
                        )
                    },
                    placeholder: "100",
                    width: 72,
                    enabled: model.canEditDesired
                )
                .focused($focusedField, equals: .boonRarity)
                Text("%").foregroundStyle(.secondary)
            }
            Divider()
            HStack(spacing: 18) {
                HStack(spacing: 8) {
                    TrainerCheckboxControl(
                        title: text("hades2.rarity.legendary"),
                        isOn: model.boonForceLegendary,
                        enabled: model.canEditDesired && model.boonRarityEnabled,
                        onChange: { model.setBoonRarity(target: model.boonRarityTarget, multiplier: boonRarityFactor, forceLegendary: $0, forceDuo: model.boonForceDuo) }
                    )
                    TrainerShortcutBadge(text: model.shortcutText(.forceLegendary))
                }
                HStack(spacing: 8) {
                    TrainerCheckboxControl(
                        title: text("hades2.rarity.duo"),
                        isOn: model.boonForceDuo,
                        enabled: model.canEditDesired && model.boonRarityEnabled,
                        onChange: { model.setBoonRarity(target: model.boonRarityTarget, multiplier: boonRarityFactor, forceLegendary: model.boonForceLegendary, forceDuo: $0) }
                    )
                    TrainerShortcutBadge(text: model.shortcutText(.forceDuo))
                }
                Spacer()
            }
        }.trainerPanel()
    }

    private var nextRoomRewardPanel: some View {
        HStack(spacing: 14) {
            Label(text("hades2.nextRoom.title"), systemImage: "door.left.hand.open").font(.subheadline.weight(.semibold))
            Spacer()
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
            }.labelsHidden().frame(maxWidth: 360).disabled(!model.canEditDesired)
            TrainerShortcutBadge(text: model.shortcutText(.applyNextRoomReward))
            Button(text("hades2.nextRoom.apply")) { model.setNextRoomReward(model.selectedNextRoomReward.isEmpty ? nil : model.selectedNextRoomReward) }.disabled(!model.canEditDesired)
        }.trainerPanel()
    }

    private var resourcePanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            multiplierRow(text("hades2.feature.moneyMultiplier"), enabled: model.moneyMultiplierEnabled, actual: model.moneyMultiplier,
                text: $moneyFactor, feature: "moneyMultiplier", toggle: .moneyMultiplierEnabled, shortcut: .moneyMultiplierEnabled)
            Divider()
            TrainerResourceEditor(
                title: text("hades2.resource.materials"),
                icon: "diamond.fill",
                search: $search,
                selection: $selectedMaterial,
                amount: intentBinding($materialAmount) {
                    guard let material else { return }
                    model.setResource(material.id, amount: $0)
                },
                sections: resourceGroups(filtered),
                enabled: model.canSetResource,
                locked: material?.locked ?? false,
                itemLabel: { resource in
                    (resource.englishName.isEmpty ? resource.name : "\(resource.name) · \(resource.englishName)")
                        + " · \(number(resource.count))"
                        + (resource.locked ? " · " + text("hades2.vital.lockedSuffix") : "")
                },
                onLock: {
                    guard let material else { return }
                    model.lockResource(material.id, locked: !material.locked)
                }
            )
            Divider()
            multiplierRow(text("hades2.feature.resourceMultiplier"), enabled: model.resourceMultiplierEnabled, actual: model.resourceMultiplier,
                text: $materialFactor, feature: "resourceMultiplier", toggle: .resourceMultiplierEnabled, shortcut: .resourceMultiplierEnabled)
        }
        .trainerPanel()
    }

    private var boonPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            spawnRow(title: text("hades2.spawn.olympianBoons"), icon: "sparkles", options: olympianBoons, selection: $model.selectedOlympianReward, shortcut: .spawnOlympian, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            Divider()
            spawnRow(title: text("hades2.spawn.pickupRewards"), icon: "shippingbox.fill", options: pickupRewards, selection: $model.selectedPickupReward, shortcut: .spawnPickup, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            Divider()
            HStack {
                Label(text("hades2.spawn.characterRewards"), systemImage: "moon.stars.fill").font(.subheadline.weight(.medium))
                Spacer()
                TextField(text("hades2.spawn.search"), text: $specialSearch).textFieldStyle(.roundedBorder).frame(maxWidth: 280)
            }
            spawnRow(
                title: nil,
                icon: nil,
                options: specialBoons,
                selection: $model.selectedSpecialReward,
                shortcut: .spawnSpecial,
                enabled: model.canPerformSelectedSpecialReward,
                onAction: model.performSpecialReward
            )
            Divider()
            HStack {
                Label(text("hades2.spawn.exactBoons"), systemImage: "scope").font(.subheadline.weight(.medium))
                Spacer()
                TextField(text("hades2.spawn.search"), text: $exactSearch).textFieldStyle(.roundedBorder).frame(maxWidth: 280)
            }
            TrainerGroupedOptionPicker(
                title: nil,
                icon: nil,
                pickerLabel: text("hades2.spawn.exactBoons"),
                selection: $model.selectedExactBoon,
                sections: boonGroups(exactBoons),
                enabled: model.canSpawnReward,
                emptyLabel: text("hades2.spawn.noItems"),
                actionTitle: text("hades2.spawn.acquire"),
                shortcutText: nil,
                itemLabel: exactItemLabel,
                onAction: model.acquireExactBoon
            )
            Divider()
            HStack {
                Label(text("hades2.spawn.purgingPool"), systemImage: "arrow.left.arrow.right.circle").font(.subheadline.weight(.medium))
                Spacer()
                Button(text("hades2.spawn.open")) { model.openSellTraits() }
                    .disabled(!model.canOpenNativeBoonScreen)
            }
            if model.connected {
                Divider()
                currentRunTraitsPanel
            }
        }.trainerPanel()
    }

    private func exactItemLabel(_ option: BoonOption) -> String {
        let localizedName = localization.language == .en ? option.englishName : option.name
        if !localizedName.isEmpty { return localizedName }
        return text("hades2.spawn.unnamedEffect")
    }

    private func spawnRow(
        title: String?,
        icon: String?,
        options: [BoonOption],
        selection: Binding<String>,
        shortcut: ShortcutAction,
        enabled: Bool,
        onAction: @escaping (String) -> Void
    ) -> some View {
        TrainerGroupedOptionPicker(
            title: title,
            icon: icon,
            pickerLabel: title ?? text("hades2.spawn.characterRewards"),
            selection: selection,
            sections: boonGroups(options),
            enabled: enabled,
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
        TrainerCompactMultiplierRow(
            title: title,
            icon: feature == "moneyMultiplier" ? "circle.hexagongrid.fill" : "shippingbox.fill",
            state: model.featurePresentation(toggle, enabled: enabled).trainerControlState(using: theme, localization: localization),
            text: configIntentBinding(text, key: feature) { model.setMultiplier(feature, text: $0) },
            shortcutText: shortcut.map { model.shortcutText($0) }
        ) {
            model.feature(toggle, value: !enabled)
        }
    }

    private var management: some View {
        TrainerSection(title: text("hades2.section.management"), icon: "gearshape.2.fill") {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Spacer()
                    Button { model.disableAll() } label: {
                        Label("\(localization.localized("host.disableAll"))  \(model.shortcutText(.disableAll))", systemImage: "power")
                    }
                        .disabled(!model.connected || model.busy || model.exiting)
                }
                HStack(spacing: 12) {
                    Button { profileManager = true; model.listProfiles() } label: { Label(text("hades2.manage.profiles"), systemImage: "slider.horizontal.3") }
                    Button { diagnosticSheet = true; model.runDiagnostics() } label: { Label(text("hades2.manage.diagnostics"), systemImage: "stethoscope") }
                    Spacer()
                }
                HStack(spacing: 12) {
                    Button { model.prepareDebugging() } label: { Label(text("hades2.manage.prepareSigning"), systemImage: "signature") }
                    Button { model.restoreOriginalSignature() } label: { Label(text("hades2.manage.restoreSigning"), systemImage: "arrow.uturn.backward.circle") }
                    Button { model.openLog() } label: {
                        Label(localization.localized("host.viewLog"), systemImage: "doc.text.magnifyingglass")
                    }
                }.disabled(model.busy || model.exiting)
            }.trainerPanel()
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

    private func featureMultiplierRow(_ title: String, key: Hades2FeatureKey, icon: String, enabled: Bool,
        text: Binding<String>, shortcut: ShortcutAction?, action: @escaping () -> Void) -> some View {
        TrainerFeatureMultiplierRow(
            title: title,
            icon: icon,
            state: model.featurePresentation(key, enabled: enabled).trainerControlState(using: theme, localization: localization),
            text: text,
            shortcutText: shortcut.map { model.shortcutText($0) },
            action: action
        )
    }

    private var messageSlot: some View {
        ZStack(alignment: .leading) {
            Color.clear
            // A Hades-owned message is a token, so it re-renders on a language
            // switch. A Core-owned message arrives as a key/plain string and the
            // Host resolves it through the shared banner. Hades wins when both
            // are present because it is the more specific failure.
            if !model.errorText.key.isEmpty {
                TrainerMessageBanner(text: resolved(model.errorText), icon: "exclamationmark.triangle.fill", color: theme.warning)
            } else if !model.error.isEmpty {
                // The backend error envelope already carries the stable key and
                // arguments. Resolve by namespace here instead of dropping Host
                // arguments or treating a Host key as literal copy.
                TrainerMessageBanner(
                    text: resolved(model.backendErrorText),
                    icon: "exclamationmark.triangle.fill",
                    color: theme.warning
                )
            } else if !model.runtimeIssuePresentations.isEmpty {
                let issues = model.runtimeIssuePresentations.map {
                    "\($0.featureID): \(resolved($0.token))"
                }.joined(separator: "; ")
                TrainerMessageBanner(
                    text: text("hades2.status.runtimeInactive", arguments: [issues]),
                    icon: "exclamationmark.triangle.fill",
                    color: theme.warning
                )
            } else if !model.runtimeIssueText.key.isEmpty {
                TrainerMessageBanner(text: resolved(model.runtimeIssueText), icon: "exclamationmark.triangle.fill", color: theme.warning)
            } else if !model.runtimeIssue.isEmpty {
                TrainerMessageBanner(text: model.runtimeIssue, icon: "exclamationmark.triangle.fill", color: theme.warning)
            } else if !model.warning.isEmpty {
                TrainerMessageBanner(text: model.warning, icon: "exclamationmark.shield", color: theme.warning)
            } else if model.status == "incompatible" {
                TrainerMessageBanner(text: text("hades2.status.unverifiedBanner"), icon: "exclamationmark.shield", color: theme.warning)
            } else if !model.noticeText.key.isEmpty {
                TrainerMessageBanner(text: resolved(model.noticeText), icon: "checkmark.circle.fill", color: theme.success)
            } else if !model.notice.isEmpty {
                TrainerMessageBanner(text: model.notice, icon: "checkmark.circle.fill", color: theme.success)
            }
        }.frame(height: 52)
    }

    private func editableVitalMetric(_ title: String, icon: String, current: Binding<String>, maximum: Binding<String>,
        currentField: EditField, maxField: EditField, color: Color, vital: String, locked: Bool) -> some View {
        TrainerVitalMetricCard(
            title: title,
            icon: icon,
            tint: color,
            current: intentBinding(current) { model.setVital(vital, field: "current", text: $0) },
            maximum: intentBinding(maximum) { model.setVital(vital, field: "max", text: $0) },
            focus: $focusedField,
            currentField: currentField,
            maximumField: maxField,
            locked: locked,
            editable: model.canSetVitals,
            onLock: { model.lockVital(vital, locked: !locked) }
        )
    }

    private func editableAmountMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField, color: Color,
        locked: Bool, enabled: Bool, onEdit: @escaping (String) -> Void, onLock: @escaping () -> Void) -> some View {
        TrainerAmountMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: intentBinding(text, action: onEdit),
            focus: $focusedField,
            focusValue: focus,
            locked: locked,
            editable: enabled,
            onLock: onLock
        )
    }

    private func editableCounterMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField,
        color: Color, detail: String?, onEdit: @escaping (String) -> Void) -> some View {
        TrainerCounterMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: intentBinding(text, action: onEdit),
            focus: $focusedField,
            focusValue: focus,
            detail: detail,
            editable: model.canSetVitals
        )
    }

    private func editableStatMetric(_ title: String, icon: String, stat: String, text: Binding<String>, focus: EditField,
        suffix: String, locked: Bool) -> some View {
        TrainerStatMetricCard(
            title: title,
            icon: icon,
            text: intentBinding(text) {
                if locked { model.setStat(stat, text: $0, locked: true) }
            },
            focus: $focusedField,
            focusValue: focus,
            suffix: suffix,
            locked: locked,
            supported: model.statSupport[stat] != false,
            available: model.statAvailable[stat] != false,
            editable: model.canSetStats,
            onLock: { model.setStat(stat, text: text.wrappedValue, locked: !locked) }
        )
    }

    private func elementMetric(_ element: ElementCount) -> some View {
        let binding = Binding<String>(
            get: { elementInputs[element.id] ?? number(element.count) },
            set: {
                elementInputs[element.id] = $0
                model.setElement(element.id, text: $0)
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
            onLock: { model.lockElement(element.id, locked: !element.locked) }
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

    private func configIntentBinding(
        _ binding: Binding<String>,
        key: String,
        action: @escaping (String) -> Void
    ) -> Binding<String> {
        Binding(
            get: { binding.wrappedValue },
            set: {
                editedConfigDrafts.insert(key)
                binding.wrappedValue = $0
                action($0)
            }
        )
    }

    private func intentBinding(_ binding: Binding<String>, action: @escaping (String) -> Void) -> Binding<String> {
        Binding(
            get: { binding.wrappedValue },
            set: {
                binding.wrappedValue = $0
                action($0)
            }
        )
    }

    private func compactNumber(_ value: Double) -> String { String(format: "%.3g", value) }
    private func speedLabel(_ value: Double) -> String { String(format: "%g×", value) }
    private func number(_ value: Double?) -> String { value.map { String(format: "%.0f", $0) } ?? "—" }
    private func pair(_ value: Double?, _ maximum: Double?) -> String { "\(number(value)) / \(number(maximum))" }
}
