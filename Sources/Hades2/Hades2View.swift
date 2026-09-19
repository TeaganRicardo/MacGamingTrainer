import Foundation
import SwiftUI
import AppKit

// Select the property-wrapper type explicitly: CLT does not ship SwiftUIMacros.
private typealias ViewState<Value> = SwiftUI.State<Value>

struct Hades2TrainerView: View {
    private enum EditField: Hashable {
        case healthCurrent, healthMax, manaCurrent, manaMax, armorCurrent, spellCharge
        case coins, material, rerolls, damageMultiplier, moneyMultiplier, resourceMultiplier
        case grasp, dodge, crit, chargeSpeed, moveSpeed, sprintSpeed, dashSpeed, attackSpeed, manaRegen, enemyDamage, enemyHealth
        case element(String)
    }

    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
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
    @ViewState<String> private var rerollAmount = ""
    @ViewState<Bool> private var rerollsInitialized = false
    @ViewState<String> private var specialSearch = ""
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
        sortedBoons(model.specialRewardOptions.filter { specialSearch.isEmpty || $0.name.localizedCaseInsensitiveContains(specialSearch) || $0.englishName.localizedCaseInsensitiveContains(specialSearch) || $0.id.localizedCaseInsensitiveContains(specialSearch) || $0.category.localizedCaseInsensitiveContains(specialSearch) })
    }
    private var material: MaterialResource? { filtered.first { $0.id == selectedMaterial } }

    private func resourceGroups(_ options: [MaterialResource]) -> [TrainerPickerSection<MaterialResource>] {
        var titles: [String] = []
        var buckets: [String: [MaterialResource]] = [:]
        for item in options.sorted(by: { $0.sortOrder < $1.sortOrder }) {
            let title = item.sectionTitle.isEmpty ? "资源" : item.sectionTitle
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
            let title = item.sectionTitle.isEmpty ? item.category : item.sectionTitle
            if buckets[title] == nil { titles.append(title); buckets[title] = [] }
            buckets[title, default: []].append(item)
        }
        return titles.enumerated().map { index, title in
            TrainerPickerSection(id: index, title: title, items: buckets[title] ?? [])
        }
    }

    var body: some View {
        catalogObservedContent
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
        TrainerSectionHeader(title: "局内数据", icon: "gauge.with.dots.needle.67percent") {
            Button { withAnimation(.easeInOut(duration: 0.18)) { statsExpanded.toggle() } } label: {
                HStack(spacing: 5) {
                    Text(statsExpanded ? "收起" : "展开")
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
        TrainerSection(title: "战斗辅助", icon: "shield.checkered") {
            VStack(spacing: 1) {
                featureRow("God Mode", key: "godMode", icon: "shield.fill", enabled: model.godMode, shortcut: .godMode) { model.feature("godMode", value: !model.godMode) }
                featureRow("无限生命", key: "infiniteHealth", icon: "heart.fill", enabled: model.infiniteHealth, shortcut: .infiniteHealth) { model.feature("infiniteHealth", value: !model.infiniteHealth) }
                featureRow("无限魔力", key: "infiniteMana", icon: "sparkles", enabled: model.infiniteMana, shortcut: .infiniteMana) { model.feature("infiniteMana", value: !model.infiniteMana) }
                featureRow("法阵始终可用", key: "instantCastCooldown", icon: "circle.dotted.circle", enabled: model.instantCastCooldown, shortcut: .instantCastCooldown) { model.feature("instantCastCooldown", value: !model.instantCastCooldown) }
                featureRow("巫咒始终可用", key: "hexAlwaysReady", icon: "moon.stars.fill", enabled: model.hexAlwaysReady, shortcut: .hexAlwaysReady) { model.feature("hexAlwaysReady", value: !model.hexAlwaysReady) }
                featureRow("无限弹药", key: "infiniteAmmo", icon: "scope", enabled: model.infiniteAmmo, shortcut: .infiniteAmmo) { model.feature("infiniteAmmo", value: !model.infiniteAmmo) }
                featureMultiplierRow(
                    "伤害倍率",
                    key: "damageEnabled",
                    icon: "bolt.fill",
                    enabled: model.damageEnabled,
                    text: $multiplier,
                    shortcut: .damageEnabled
                ) {
                    model.feature("damageEnabled", value: !model.damageEnabled)
                }
            }
            .trainerGroupedRows()

            gameSpeedPanel

            VStack(spacing: 1) {
                featureRow("小游戏自动成功", key: "autoMiniGames", icon: "gamecontroller.fill", enabled: model.autoMiniGames, shortcut: .autoMiniGames) { model.feature("autoMiniGames", value: !model.autoMiniGames) }
                featureRow("花园便捷操作", key: "gardenQoL", icon: "leaf.fill", enabled: model.gardenQoL, shortcut: .gardenQoL) { model.feature("gardenQoL", value: !model.gardenQoL) }
            }
            .trainerGroupedRows()
        }
    }

    private var buildSection: some View {
        TrainerSection(title: "构筑数据", icon: "chart.bar.xaxis") {
            metaStatPanel
            boonRarityPanel
            HStack {
                Label("祝福管理", systemImage: "arrow.left.arrow.right.circle").font(.subheadline.weight(.medium))
                Spacer()
                Button("打开祝福出售界面") { model.openSellTraits() }
                    .disabled(!model.canOpenNativeBoonScreen)
            }
            .trainerPanel()
        }
    }

    private var resourceSection: some View {
        TrainerSection(title: "资源管理", icon: "shippingbox.fill") {
            resourcePanel
        }
    }

    private var spawnSection: some View {
        VStack(alignment: .leading, spacing: theme.pageSpacing) {
            TrainerSection(title: "生成内容", icon: "sparkles") {
                boonPanel
                nextRoomRewardPanel
            }
            TrainerSection(title: "元素数量", icon: "circle.hexagongrid.fill") {
                elementPanel
            }
        }
    }

    @ViewBuilder
    private var gameSpeedPanel: some View {
        if model.featureSupport["gameSpeed"] == true {
            HStack {
                Text("游戏速度").font(.headline)
                Text("当前 \(model.gameSpeed, specifier: "%.2g")×").foregroundStyle(.secondary)
                Spacer()
                ForEach([0.25, 0.5, 1.0, 1.5, 2.0, 3.0], id: \.self) { speed in
                    Button(speed == 1 ? "恢复 1×" : speedLabel(speed)) {
                        model.feature("gameSpeed", value: speed)
                    }
                    .disabled(!model.canEditDesired)
                }
            }
            .trainerPanel()
        }
    }

    private var presentedContent: some View {
        rootContent
            .sheet(isPresented: $model.shortcutSettingsPresented) { Hades2ShortcutSettingsView(model: model) }
            .sheet(isPresented: $model.saveManagerPresented) { Hades2SaveManagerView(model: model) }
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
            resourceMultiplier: model.resourceMultiplier
        )
    }

    private var inputSnapshot: Hades2ViewInputSnapshot {
        Hades2ViewInputSnapshot(
            healthCurrent: healthCurrent,
            healthMaximum: healthMaximum,
            manaCurrent: manaCurrent,
            manaMaximum: manaMaximum,
            armorCurrent: armorCurrent,
            spellCharge: spellCharge,
            coins: coins,
            materialAmount: materialAmount,
            selectedMaterial: selectedMaterial,
            rerollAmount: rerollAmount,
            multiplier: multiplier,
            moneyFactor: moneyFactor,
            materialFactor: materialFactor
        )
    }

    private var lockedStatInputSnapshot: Hades2ViewLockedStatInputSnapshot {
        Hades2ViewLockedStatInputSnapshot(
            grasp: graspLimit,
            dodge: dodgeChance,
            crit: critChance,
            chargeSpeed: chargeSpeed,
            moveSpeed: moveSpeed,
            sprintSpeed: sprintSpeed,
            dashSpeed: dashSpeed,
            attackSpeed: attackSpeed,
            manaRegen: manaRegen,
            enemyDamage: enemyDamage,
            enemyHealth: enemyHealth
        )
    }

    private var catalogSnapshot: Hades2ViewCatalogSnapshot {
        Hades2ViewCatalogSnapshot(
            elementInputs: elementInputs,
            materialID: material?.id,
            boonRarityFactor: boonRarityFactor,
            olympianIDs: olympianBoons.map(\.id),
            pickupIDs: pickupRewards.map(\.id),
            specialIDs: specialBoons.map(\.id),
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

    private var inputObservedContent: some View {
        gameConfigObservedContent
            .onChange(of: inputSnapshot) { oldValue, newValue in
                applyInputChanges(from: oldValue, to: newValue)
            }
    }

    private var lockedStatObservedContent: some View {
        inputObservedContent
            .onChange(of: lockedStatInputSnapshot) { oldValue, newValue in
                applyLockedStatChanges(from: oldValue, to: newValue)
            }
    }

    private var catalogObservedContent: some View {
        lockedStatObservedContent
            .onChange(of: catalogSnapshot, initial: true) { oldValue, newValue in
                applyCatalogChanges(from: oldValue, to: newValue)
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
        } else if focusedField == nil {
            boonRarityFactor = compactNumber(snapshot.boonRarityMultiplier)
        }
        model.selectedNextRoomReward = snapshot.nextRoomReward ?? ""
        syncElementInputs(snapshot.elements)
        multiplier = compactNumber(snapshot.damageMultiplier)
        moneyFactor = compactNumber(snapshot.moneyMultiplier)
        materialFactor = compactNumber(snapshot.resourceMultiplier)
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

    private func applyInputChanges(from oldValue: Hades2ViewInputSnapshot, to newValue: Hades2ViewInputSnapshot) {
        if vitalsInitialized {
            if oldValue.healthCurrent != newValue.healthCurrent { model.setVital("health", field: "current", text: newValue.healthCurrent) }
            if oldValue.healthMaximum != newValue.healthMaximum { model.setVital("health", field: "max", text: newValue.healthMaximum) }
            if oldValue.manaCurrent != newValue.manaCurrent { model.setVital("mana", field: "current", text: newValue.manaCurrent) }
            if oldValue.manaMaximum != newValue.manaMaximum { model.setVital("mana", field: "max", text: newValue.manaMaximum) }
            if oldValue.armorCurrent != newValue.armorCurrent { model.setVital("armor", field: "current", text: newValue.armorCurrent) }
            if oldValue.spellCharge != newValue.spellCharge { model.setCounter("spellCharge", text: newValue.spellCharge) }
        }
        if coinsInitialized, oldValue.coins != newValue.coins { model.setResource("Money", amount: newValue.coins) }
        if !newValue.selectedMaterial.isEmpty, oldValue.materialAmount != newValue.materialAmount {
            model.setResource(newValue.selectedMaterial, amount: newValue.materialAmount)
        }
        if rerollsInitialized, oldValue.rerollAmount != newValue.rerollAmount { model.setRerolls(newValue.rerollAmount) }
        if oldValue.multiplier != newValue.multiplier { model.setMultiplier("damageMultiplier", text: newValue.multiplier) }
        if oldValue.moneyFactor != newValue.moneyFactor { model.setMultiplier("moneyMultiplier", text: newValue.moneyFactor) }
        if oldValue.materialFactor != newValue.materialFactor { model.setMultiplier("resourceMultiplier", text: newValue.materialFactor) }
    }

    private func applyLockedStatChanges(from oldValue: Hades2ViewLockedStatInputSnapshot, to newValue: Hades2ViewLockedStatInputSnapshot) {
        guard statsInitialized else { return }
        if model.graspLocked, oldValue.grasp != newValue.grasp { model.setStat("grasp", text: newValue.grasp, locked: true) }
        if model.dodgeLocked, oldValue.dodge != newValue.dodge { model.setStat("dodge", text: newValue.dodge, locked: true) }
        if model.critLocked, oldValue.crit != newValue.crit { model.setStat("crit", text: newValue.crit, locked: true) }
        if model.chargeSpeedLocked, oldValue.chargeSpeed != newValue.chargeSpeed { model.setStat("chargeSpeed", text: newValue.chargeSpeed, locked: true) }
        if model.moveSpeedLocked, oldValue.moveSpeed != newValue.moveSpeed { model.setStat("moveSpeed", text: newValue.moveSpeed, locked: true) }
        if model.sprintSpeedLocked, oldValue.sprintSpeed != newValue.sprintSpeed { model.setStat("sprintSpeed", text: newValue.sprintSpeed, locked: true) }
        if model.dashSpeedLocked, oldValue.dashSpeed != newValue.dashSpeed { model.setStat("dashSpeed", text: newValue.dashSpeed, locked: true) }
        if model.attackSpeedLocked, oldValue.attackSpeed != newValue.attackSpeed { model.setStat("attackSpeed", text: newValue.attackSpeed, locked: true) }
        if model.manaRegenLocked, oldValue.manaRegen != newValue.manaRegen { model.setStat("manaRegen", text: newValue.manaRegen, locked: true) }
        if model.enemyDamageLocked, oldValue.enemyDamage != newValue.enemyDamage { model.setStat("enemyDamage", text: newValue.enemyDamage, locked: true) }
        if model.enemyHealthLocked, oldValue.enemyHealth != newValue.enemyHealth { model.setStat("enemyHealth", text: newValue.enemyHealth, locked: true) }
    }

    private func applyCatalogChanges(from oldValue: Hades2ViewCatalogSnapshot, to newValue: Hades2ViewCatalogSnapshot) {
        if elementsInitialized, oldValue.elementInputs != newValue.elementInputs {
            let keys = Set(oldValue.elementInputs.keys).union(newValue.elementInputs.keys)
            for id in keys where oldValue.elementInputs[id] != newValue.elementInputs[id] {
                if let text = newValue.elementInputs[id] { model.setElement(id, text: text) }
            }
        }

        if oldValue.materialID != newValue.materialID {
            materialAmount = material.map { number($0.count) } ?? ""
        }
        if boonConfigInitialized, oldValue.boonRarityFactor != newValue.boonRarityFactor {
            model.setBoonRarity(
                target: model.boonRarityTarget,
                multiplier: newValue.boonRarityFactor,
                forceLegendary: model.boonForceLegendary,
                forceDuo: model.boonForceDuo
            )
        }
        if !newValue.olympianIDs.contains(model.selectedOlympianReward) { model.selectedOlympianReward = newValue.olympianIDs.first ?? "" }
        if !newValue.pickupIDs.contains(model.selectedPickupReward) { model.selectedPickupReward = newValue.pickupIDs.first ?? "" }
        if !newValue.specialIDs.contains(model.selectedSpecialReward) { model.selectedSpecialReward = newValue.specialIDs.first ?? "" }
        if !newValue.filteredResourceIDs.contains(selectedMaterial) {
            selectedMaterial = search.isEmpty && newValue.filteredResourceIDs.contains("MetaCurrency")
                ? "MetaCurrency"
                : (newValue.filteredResourceIDs.first ?? "")
        }
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
            "生命", icon: "heart.fill", current: $healthCurrent, maximum: $healthMaximum,
            currentField: .healthCurrent, maxField: .healthMax, color: .pink,
            vital: "health", locked: model.healthLocked
        )
        editableVitalMetric(
            "魔力", icon: "sparkles", current: $manaCurrent, maximum: $manaMaximum,
            currentField: .manaCurrent, maxField: .manaMax, color: .cyan,
            vital: "mana", locked: model.manaLocked
        )
        editableAmountMetric(
            "本局金币", icon: "circle.hexagongrid.fill", text: $coins, focus: .coins,
            color: .yellow, locked: model.moneyLocked, enabled: model.canSetResource
        ) {
            model.lockResource("Money", locked: !model.moneyLocked)
        }
        editableAmountMetric(
            "护甲", icon: "shield.lefthalf.filled", text: $armorCurrent, focus: .armorCurrent,
            color: theme.warning, locked: model.armorLocked, enabled: model.canSetVitals
        ) {
            model.lockVital("armor", locked: !model.armorLocked)
        }
    }

    @ViewBuilder
    private var expandedSessionMetrics: some View {
        editableAmountMetric(
            "重骰", icon: "dice.fill", text: $rerollAmount, focus: .rerolls,
            color: accent, locked: model.rerollsLocked, enabled: model.canSetResource
        ) {
            model.lockRerolls(!model.rerollsLocked)
        }
        editableCounterMetric(
            "巫咒充能", icon: "moonphase.waxing.crescent", text: $spellCharge,
            focus: .spellCharge, color: .purple,
            detail: model.spellChargeCost.map { "需求 \(number($0))" } ?? nil
        )
        editableStatMetric("闪避率", icon: "figure.run", stat: "dodge", text: $dodgeChance, focus: .dodge, suffix: "%", locked: model.dodgeLocked)
        editableStatMetric("最终暴击率", icon: "scope", stat: "crit", text: $critChance, focus: .crit, suffix: "%", locked: model.critLocked)
        editableStatMetric("敌人伤害", icon: "burst.fill", stat: "enemyDamage", text: $enemyDamage, focus: .enemyDamage, suffix: "%", locked: model.enemyDamageLocked)
        editableStatMetric("敌人生命", icon: "heart.text.square.fill", stat: "enemyHealth", text: $enemyHealth, focus: .enemyHealth, suffix: "%", locked: model.enemyHealthLocked)
        editableStatMetric("蓄力速度倍率", icon: "timer", stat: "chargeSpeed", text: $chargeSpeed, focus: .chargeSpeed, suffix: "%", locked: model.chargeSpeedLocked)
        editableStatMetric("移动速度倍率", icon: "figure.walk", stat: "moveSpeed", text: $moveSpeed, focus: .moveSpeed, suffix: "%", locked: model.moveSpeedLocked)
        editableStatMetric("奔跑速度倍率", icon: "hare.fill", stat: "sprintSpeed", text: $sprintSpeed, focus: .sprintSpeed, suffix: "%", locked: model.sprintSpeedLocked)
        editableStatMetric("冲刺速度倍率", icon: "forward.end.fill", stat: "dashSpeed", text: $dashSpeed, focus: .dashSpeed, suffix: "%", locked: model.dashSpeedLocked)
        editableStatMetric("攻击速度倍率", icon: "bolt.fill", stat: "attackSpeed", text: $attackSpeed, focus: .attackSpeed, suffix: "%", locked: model.attackSpeedLocked)
        editableStatMetric("额外魔力恢复", icon: "drop.circle.fill", stat: "manaRegen", text: $manaRegen, focus: .manaRegen, suffix: "/s", locked: model.manaRegenLocked)
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
            statRow("悟性上限", stat: "grasp", text: $graspLimit, locked: model.graspLocked, suffix: "", focus: .grasp)
        }.trainerGroupedRows()
    }

    private func statRow(_ title: String, stat: String, text: Binding<String>, locked: Bool, suffix: String, focus: EditField) -> some View {
        TrainerInlineStatEditor(
            title: title,
            text: text,
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
                Label("祝福稀有度控制", systemImage: "star.circle.fill").font(.subheadline.weight(.semibold))
                Spacer()
                TrainerShortcutBadge(text: model.shortcutText(.boonRarityEnabled))
                TrainerToggleControl(
                    isOn: model.boonRarityEnabled,
                    enabled: model.canEditDesired,
                    tint: model.featurePresentation("boonRarityEnabled", enabled: model.boonRarityEnabled).trainerControlState(using: theme).indicatorColor,
                    onChange: { model.feature("boonRarityEnabled", value: $0) }
                )
            }
            HStack(spacing: 12) {
                Text("最低稀有度").foregroundStyle(.secondary)
                Picker("最低稀有度", selection: Binding(get: { model.boonRarityTarget }, set: { model.setBoonRarity(target: $0, multiplier: boonRarityFactor, forceLegendary: model.boonForceLegendary, forceDuo: model.boonForceDuo) })) {
                    Text("普通 Common").tag("Common"); Text("稀有 Rare").tag("Rare"); Text("史诗 Epic").tag("Epic"); Text("英雄 Heroic").tag("Heroic")
                }.labelsHidden().frame(width: 150).disabled(!model.canEditDesired)
                Spacer()
                Text("稀有度概率倍率").foregroundStyle(.secondary)
                TextField("100", text: $boonRarityFactor).textFieldStyle(.roundedBorder).frame(width: 72).multilineTextAlignment(.center)
                    .disabled(!model.canEditDesired)
                Text("%").foregroundStyle(.secondary)
            }
            Divider()
            HStack(spacing: 18) {
                HStack(spacing: 8) {
                    TrainerCheckboxControl(
                        title: "强制传奇 Legendary",
                        isOn: model.boonForceLegendary,
                        enabled: model.canEditDesired && model.boonRarityEnabled,
                        onChange: { model.setBoonRarity(target: model.boonRarityTarget, multiplier: boonRarityFactor, forceLegendary: $0, forceDuo: model.boonForceDuo) }
                    )
                    TrainerShortcutBadge(text: model.shortcutText(.forceLegendary))
                }
                HStack(spacing: 8) {
                    TrainerCheckboxControl(
                        title: "强制双重 Duo",
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
            Label("下一房奖励", systemImage: "door.left.hand.open").font(.subheadline.weight(.semibold))
            Spacer()
            Picker("下一房奖励", selection: $model.selectedNextRoomReward) {
                Text("不覆盖").tag("")
                Section("常规") {
                    Text("金币 · Gold Crowns").tag("RoomMoneyDrop")
                    Text("尘灰 · Ashes").tag("MetaCardPointsCommonDrop")
                    Text("魂魄 · Psyche").tag("MemPointsCommonDrop")
                    Text("骨骸 · Bones").tag("MetaCurrencyDrop")
                    Text("半人马之心 · Centaur Heart").tag("MaxHealthDrop")
                    Text("灵魂之水 · Soul Tonic").tag("MaxManaDrop")
                    Text("力量石榴 · Pom of Power").tag("StackUpgrade")
                    Text("狄德勒斯之锤 · Daedalus Hammer").tag("WeaponUpgrade")
                    Text("月之礼赠 · Gift of the Moon").tag("SpellDrop")
                }
                Section("诸神") {
                    ForEach(olympianBoons) { boon in Text(boon.englishName.isEmpty ? boon.name : "\(boon.name) · \(boon.englishName)").tag(boon.id) }
                }
            }.labelsHidden().frame(maxWidth: 360).disabled(!model.canEditDesired)
            TrainerShortcutBadge(text: model.shortcutText(.applyNextRoomReward))
            Button("应用") { model.setNextRoomReward(model.selectedNextRoomReward.isEmpty ? nil : model.selectedNextRoomReward) }.disabled(!model.canEditDesired)
        }.trainerPanel()
    }

    private var resourcePanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            multiplierRow("金币获取倍率", enabled: model.moneyMultiplierEnabled, actual: model.moneyMultiplier,
                text: $moneyFactor, feature: "moneyMultiplier", toggle: "moneyMultiplierEnabled", shortcut: .moneyMultiplierEnabled)
            Divider()
            TrainerResourceEditor(
                title: "材料",
                icon: "diamond.fill",
                search: $search,
                selection: $selectedMaterial,
                amount: $materialAmount,
                sections: resourceGroups(filtered),
                enabled: model.canSetResource,
                locked: material?.locked ?? false,
                itemLabel: { resource in
                    (resource.englishName.isEmpty ? resource.name : "\(resource.name) · \(resource.englishName)")
                        + " · \(number(resource.count))"
                        + (resource.locked ? " · 已锁定" : "")
                },
                onLock: {
                    guard let material else { return }
                    model.lockResource(material.id, locked: !material.locked)
                }
            )
            Divider()
            multiplierRow("材料获取倍率", enabled: model.resourceMultiplierEnabled, actual: model.resourceMultiplier,
                text: $materialFactor, feature: "resourceMultiplier", toggle: "resourceMultiplierEnabled", shortcut: .resourceMultiplierEnabled)
        }
        .trainerPanel()
    }

    private var boonPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            spawnRow(title: "诸神祝福", icon: "sparkles", options: olympianBoons, selection: $model.selectedOlympianReward, shortcut: .spawnOlympian, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            Divider()
            spawnRow(title: "资源与常规掉落", icon: "shippingbox.fill", options: pickupRewards, selection: $model.selectedPickupReward, shortcut: .spawnPickup, enabled: model.canSpawnReward, onAction: model.spawnBoon)
            Divider()
            HStack {
                Label("特殊祝福", systemImage: "moon.stars.fill").font(.subheadline.weight(.medium))
                Spacer()
                TextField("搜索官方中英文名或内部 ID", text: $specialSearch).textFieldStyle(.roundedBorder).frame(maxWidth: 280)
            }
            spawnRow(
                title: nil,
                icon: nil,
                options: specialBoons,
                selection: $model.selectedSpecialReward,
                shortcut: .spawnSpecial,
                enabled: model.canPerformSelectedSpecialReward,
                actionTitle: model.selectedSpecialRewardIsNativeChoice ? "打开三选一" : "直接添加",
                onAction: model.performSpecialReward
            )
        }.trainerPanel()
    }

    private func spawnRow(
        title: String?,
        icon: String?,
        options: [BoonOption],
        selection: Binding<String>,
        shortcut: ShortcutAction,
        enabled: Bool,
        actionTitle: String = "生成",
        onAction: @escaping (String) -> Void
    ) -> some View {
        TrainerGroupedOptionPicker(
            title: title,
            icon: icon,
            pickerLabel: title ?? "特殊祝福",
            selection: selection,
            sections: boonGroups(options),
            enabled: enabled,
            emptyLabel: "没有可用项目",
            actionTitle: actionTitle,
            shortcutText: model.shortcutText(shortcut),
            itemLabel: { option in
                option.englishName.isEmpty ? option.name : "\(option.name) · \(option.englishName)"
            },
            onAction: onAction
        )
    }

    private func multiplierRow(_ title: String, enabled: Bool, actual: Double, text: Binding<String>, feature: String, toggle: String, shortcut: ShortcutAction? = nil) -> some View {
        TrainerCompactMultiplierRow(
            title: title,
            icon: feature == "moneyMultiplier" ? "circle.hexagongrid.fill" : "shippingbox.fill",
            state: model.featurePresentation(toggle, enabled: enabled).trainerControlState(using: theme),
            text: text,
            shortcutText: shortcut.map { model.shortcutText($0) }
        ) {
            model.feature(toggle, value: !enabled)
        }
    }

    private func openSaveManager() {
        model.saveManagerPresented = true
        model.refreshBackups()
    }

    private var management: some View {
        TrainerSection(title: "游戏管理", icon: "gearshape.2.fill") {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Spacer()
                    Button { model.disableAll() } label: { Label("全部关闭  \(model.shortcutText(.disableAll))", systemImage: "power") }
                        .disabled(!model.connected || model.busy || model.exiting)
                }
                HStack(spacing: 12) {
                    Button { openSaveManager() } label: { Label("存档管理", systemImage: "externaldrive.fill") }
                    Button { profileManager = true; model.listProfiles() } label: { Label("自定义配置", systemImage: "slider.horizontal.3") }
                    Button { diagnosticSheet = true; model.runDiagnostics() } label: { Label("运行自检", systemImage: "stethoscope") }
                    Spacer()
                }
                HStack(spacing: 12) {
                    Button { model.prepareDebugging() } label: { Label("准备调试签名", systemImage: "signature") }
                    Button { model.restoreOriginalSignature() } label: { Label("恢复原始签名", systemImage: "arrow.uturn.backward.circle") }
                    Button { model.openLog() } label: { Label("打开日志", systemImage: "doc.text.magnifyingglass") }
                }.disabled(model.busy || model.exiting)
            }.trainerPanel()
        }
    }

    private func featureRow(_ title: String, key: String, icon: String, enabled: Bool, shortcut: ShortcutAction? = nil, action: @escaping () -> Void) -> some View {
        TrainerFeatureToggleRow(
            title: title,
            icon: icon,
            state: model.featurePresentation(key, enabled: enabled).trainerControlState(using: theme),
            shortcutText: shortcut.map { model.shortcutText($0) },
            action: action
        )
    }

    private func featureMultiplierRow(_ title: String, key: String, icon: String, enabled: Bool,
        text: Binding<String>, shortcut: ShortcutAction?, action: @escaping () -> Void) -> some View {
        TrainerFeatureMultiplierRow(
            title: title,
            icon: icon,
            state: model.featurePresentation(key, enabled: enabled).trainerControlState(using: theme),
            text: text,
            shortcutText: shortcut.map { model.shortcutText($0) },
            action: action
        )
    }

    private var messageSlot: some View {
        ZStack(alignment: .leading) {
            Color.clear
            if !model.error.isEmpty {
                TrainerMessageBanner(text: model.error, icon: "exclamationmark.triangle.fill", color: theme.warning)
            } else if !model.runtimeIssue.isEmpty {
                TrainerMessageBanner(text: model.runtimeIssue, icon: "exclamationmark.triangle.fill", color: theme.warning)
            } else if !model.warning.isEmpty {
                TrainerMessageBanner(text: model.warning, icon: "exclamationmark.shield", color: theme.warning)
            } else if model.status == "incompatible" {
                TrainerMessageBanner(text: "当前版本尚未验证，可继续尝试连接。", icon: "exclamationmark.shield", color: theme.warning)
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
            current: current,
            maximum: maximum,
            focus: $focusedField,
            currentField: currentField,
            maximumField: maxField,
            locked: locked,
            editable: model.canSetVitals,
            onLock: { model.lockVital(vital, locked: !locked) }
        )
    }

    private func editableAmountMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField, color: Color,
        locked: Bool, enabled: Bool, onLock: @escaping () -> Void) -> some View {
        TrainerAmountMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: text,
            focus: $focusedField,
            focusValue: focus,
            locked: locked,
            editable: enabled,
            onLock: onLock
        )
    }

    private func editableCounterMetric(_ title: String, icon: String, text: Binding<String>, focus: EditField,
        color: Color, detail: String?) -> some View {
        TrainerCounterMetricCard(
            title: title,
            icon: icon,
            tint: color,
            text: text,
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
            text: text,
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
            set: { elementInputs[element.id] = $0 }
        )
        let style = elementStyle(element.id)
        return TrainerAmountMetricCard(
            title: element.name + "元素",
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

    private func compactNumber(_ value: Double) -> String { String(format: "%.3g", value) }
    private func speedLabel(_ value: Double) -> String { String(format: "%g×", value) }
    private func number(_ value: Double?) -> String { value.map { String(format: "%.0f", $0) } ?? "—" }
    private func pair(_ value: Double?, _ maximum: Double?) -> String { "\(number(value)) / \(number(maximum))" }
}
