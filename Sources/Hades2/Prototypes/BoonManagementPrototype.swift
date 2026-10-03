import SwiftUI

// PROTOTYPE ONLY — Variant G.
// Exact acquisition stays unchanged. This prototypes a two-row mounted-effect
// manager. #237–#240 owner families below are interactive dummy state.
struct BoonManagementPrototypeView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var selection = "dummy:chaos"
    @State private var search = ""
    @State private var liveLevelDrafts: [String: String] = [:]
    @State private var liveRarityDrafts: [String: String] = [:]
    @State private var dummyLevelDrafts: [String: String] = [:]
    @State private var dummyRarityDrafts: [String: String] = [:]
    @State private var dummyStatusOverrides: [String: String] = [:]
    @State private var dummyRemoved: Set<String> = []
    @State private var dummyToggleStates: [String: Bool] = [:]
    @State private var dummyReplacement: [String: String] = [
        "dummy:hammer": "B",
        "dummy:costume": "B",
    ]
    @State private var dummyRemaining: [String: String] = ["dummy:temporary": "3"]

    private enum DummyKind: String {
        case chaos, hex, hexTalent, hammer, npc, costume, echo, temporary, familiar, progression
    }

    private struct DummyEffect: Identifiable {
        let id: String
        let groupZh: String
        let groupEn: String
        let nameZh: String
        let nameEn: String
        let sourceZh: String
        let sourceEn: String
        let initialStatusZh: String
        let initialStatusEn: String
        let level: Int
        let rarity: String
        let rarities: [String]
        let canLevel: Bool
        let canRarity: Bool
        let canRemove: Bool
        let kind: DummyKind
    }

    private struct PickerOption: Identifiable {
        let id: String
        let groupID: String
        let groupTitle: String
        let title: String
        let subtitle: String
    }

    private struct PickerGroup: Identifiable {
        let id: String
        let title: String
        let items: [PickerOption]
    }

    private let dummyEffects: [DummyEffect] = [
        .init(
            id: "dummy:chaos",
            groupZh: "卡俄斯", groupEn: "Chaos",
            nameZh: "卡俄斯配对效果（示意）", nameEn: "Chaos Paired Effect (dummy)",
            sourceZh: "诅咒 → 祝福", sourceEn: "Curse → Blessing",
            initialStatusZh: "诅咒阶段 · 剩余 2 场 · 将转化为祝福",
            initialStatusEn: "Curse phase · 2 encounters · transforms to blessing",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .chaos
        ),
        .init(
            id: "dummy:hex",
            groupZh: "塞勒涅", groupEn: "Selene",
            nameZh: "巫咒（示意）", nameEn: "Hex (dummy)",
            sourceZh: "巫咒本体", sourceEn: "Hex",
            initialStatusZh: "已装备 · 天赋 4 / 8",
            initialStatusEn: "Slotted · talents 4 / 8",
            level: 3, rarity: "", rarities: [],
            canLevel: true, canRarity: false, canRemove: true, kind: .hex
        ),
        .init(
            id: "dummy:hexTalent",
            groupZh: "塞勒涅", groupEn: "Selene",
            nameZh: "巫咒天赋（示意）", nameEn: "Hex Talent (dummy)",
            sourceZh: "天赋树", sourceEn: "Talent Tree",
            initialStatusZh: "天赋 ON · 隶属当前巫咒",
            initialStatusEn: "Talent ON · linked to current Hex",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .hexTalent
        ),
        .init(
            id: "dummy:hammer",
            groupZh: "武器 / 代达罗斯", groupEn: "Weapon / Daedalus",
            nameZh: "武器强化（示意）", nameEn: "Hammer Upgrade (dummy)",
            sourceZh: "当前武器", sourceEn: "Current Weapon",
            initialStatusZh: "当前强化：强化 A",
            initialStatusEn: "Current upgrade: Upgrade A",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .hammer
        ),
        .init(
            id: "dummy:npc",
            groupZh: "特殊 NPC", groupEn: "Special NPC",
            nameZh: "NPC 一次性效果（示意）", nameEn: "NPC One-shot Effect (dummy)",
            sourceZh: "特殊 NPC 奖励", sourceEn: "Special NPC Reward",
            initialStatusZh: "一次性结算完成 · 无持续等级/稀有度",
            initialStatusEn: "One-shot resolved · no persistent level/rarity",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: false, kind: .npc
        ),
        .init(
            id: "dummy:costume",
            groupZh: "阿拉克涅服装", groupEn: "Arachne Costume",
            nameZh: "服装效果（示意）", nameEn: "Costume Effect (dummy)",
            sourceZh: "外观 + 护甲状态", sourceEn: "Appearance + armor state",
            initialStatusZh: "当前服装：服装 A · 护甲 30",
            initialStatusEn: "Current costume: Costume A · Armor 30",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .costume
        ),
        .init(
            id: "dummy:echo",
            groupZh: "Echo / 上局祝福", groupEn: "Echo / Previous-run Boon",
            nameZh: "Echo 上局祝福（示意）", nameEn: "Echo Previous-run Boon (dummy)",
            sourceZh: "上局继承", sourceEn: "Previous-run inheritance",
            initialStatusZh: "已落地为当前祝福 · 后续按祝福本体管理",
            initialStatusEn: "Materialized as current boon · managed by resulting boon",
            level: 2, rarity: "Rare", rarities: ["Common", "Rare", "Epic", "Heroic"],
            canLevel: true, canRarity: true, canRemove: true, kind: .echo
        ),
        .init(
            id: "dummy:temporary",
            groupZh: "卡戎之井 / 临时效果", groupEn: "Well / Temporary Effects",
            nameZh: "临时效果（示意）", nameEn: "Temporary Effect (dummy)",
            sourceZh: "房间持续效果", sourceEn: "Room-duration effect",
            initialStatusZh: "剩余 3 场 · 删除=取消；到期=执行到期语义",
            initialStatusEn: "3 encounters left · Remove=cancellation; Expire=expiry semantics",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .temporary
        ),
        .init(
            id: "dummy:familiar",
            groupZh: "魔宠", groupEn: "Familiar",
            nameZh: "魔宠运行时效果（示意）", nameEn: "Familiar Runtime Effect (dummy)",
            sourceZh: "当前魔宠实体", sourceEn: "Current Familiar entity",
            initialStatusZh: "成长等级 3 · 与魔宠实体关联",
            initialStatusEn: "Progression level 3 · linked to Familiar entity",
            level: 3, rarity: "", rarities: [],
            canLevel: true, canRarity: false, canRemove: true, kind: .familiar
        ),
        .init(
            id: "dummy:progression",
            groupZh: "装备 / 奥秘卡运行时效果", groupEn: "Equipment / Arcana Runtime",
            nameZh: "Progression-owned 效果（示意）", nameEn: "Progression-owned Effect (dummy)",
            sourceZh: "纪念品 / 奥秘卡等", sourceEn: "Keepsake / Arcana etc.",
            initialStatusZh: "仅修改本局运行时效果 · 不改永久解锁",
            initialStatusEn: "Runtime-only edit · permanent ownership unchanged",
            level: 1, rarity: "", rarities: [],
            canLevel: false, canRarity: false, canRemove: true, kind: .progression
        ),
    ]

    private var isEnglish: Bool { localization.language == .en }

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    private func liveName(_ trait: CurrentRunTrait) -> String {
        isEnglish ? trait.englishName : trait.displayName
    }

    private func liveSource(_ trait: CurrentRunTrait) -> String {
        let source = isEnglish ? trait.sourceEnglishName : trait.sourceName
        if !source.isEmpty { return source }
        let key = "hades2.traits.family.\(trait.family)"
        let localized = text(key)
        return localized == key ? trait.family : localized
    }

    private func rarityLabel(_ rarity: String) -> String {
        let key = "hades2.rarity.\(rarity)"
        let localized = text(key)
        return localized == key ? rarity : localized
    }

    private func dummyName(_ effect: DummyEffect) -> String { isEnglish ? effect.nameEn : effect.nameZh }
    private func dummySource(_ effect: DummyEffect) -> String { isEnglish ? effect.sourceEn : effect.sourceZh }
    private func dummyGroup(_ effect: DummyEffect) -> String { isEnglish ? effect.groupEn : effect.groupZh }

    private func dummyStatus(_ effect: DummyEffect) -> String {
        if dummyRemoved.contains(effect.id) {
            return isEnglish ? "Removed (dummy)" : "已删除（dummy）"
        }
        return dummyStatusOverrides[effect.id] ?? (isEnglish ? effect.initialStatusEn : effect.initialStatusZh)
    }

    private var selectedLive: CurrentRunTrait? {
        guard selection.hasPrefix("live:") else { return nil }
        let raw = String(selection.dropFirst(5))
        return model.currentRunTraits.first { $0.id == raw }
    }

    private var selectedDummy: DummyEffect? {
        dummyEffects.first { $0.id == selection }
    }

    private var allPickerOptions: [PickerOption] {
        var result: [PickerOption] = []
        for trait in model.currentRunTraits {
            let source = liveSource(trait)
            result.append(.init(
                id: "live:\(trait.id)",
                groupID: "live:\(source)",
                groupTitle: source,
                title: liveName(trait),
                subtitle: source
            ))
        }
        for effect in dummyEffects {
            result.append(.init(
                id: effect.id,
                groupID: "dummy:\(effect.kind.rawValue)",
                groupTitle: dummyGroup(effect),
                title: dummyName(effect),
                subtitle: dummySource(effect)
            ))
        }
        return result
    }

    private var pickerGroups: [PickerGroup] {
        let filtered = allPickerOptions.filter {
            search.isEmpty
                || $0.title.localizedCaseInsensitiveContains(search)
                || $0.subtitle.localizedCaseInsensitiveContains(search)
                || $0.groupTitle.localizedCaseInsensitiveContains(search)
        }
        var order: [String] = []
        var titles: [String: String] = [:]
        var buckets: [String: [PickerOption]] = [:]
        for option in filtered {
            if buckets[option.groupID] == nil {
                order.append(option.groupID)
                titles[option.groupID] = option.groupTitle
            }
            buckets[option.groupID, default: []].append(option)
        }
        return order.map {
            PickerGroup(id: $0, title: titles[$0] ?? "", items: buckets[$0] ?? [])
        }
    }

    private func liveLevelBinding(_ trait: CurrentRunTrait) -> Binding<String> {
        Binding(
            get: { liveLevelDrafts[trait.id] ?? String(trait.level + 1) },
            set: { liveLevelDrafts[trait.id] = $0 }
        )
    }

    private func liveRarityBinding(_ trait: CurrentRunTrait) -> Binding<String> {
        Binding(
            get: {
                if let draft = liveRarityDrafts[trait.id] { return draft }
                guard let index = trait.availableRarities.firstIndex(of: trait.rarity),
                      trait.availableRarities.indices.contains(index + 1) else { return trait.rarity }
                return trait.availableRarities[index + 1]
            },
            set: { liveRarityDrafts[trait.id] = $0 }
        )
    }

    private func dummyLevelBinding(_ effect: DummyEffect) -> Binding<String> {
        Binding(
            get: { dummyLevelDrafts[effect.id] ?? String(effect.level + 1) },
            set: { dummyLevelDrafts[effect.id] = $0 }
        )
    }

    private func dummyRarityBinding(_ effect: DummyEffect) -> Binding<String> {
        Binding(
            get: {
                if let draft = dummyRarityDrafts[effect.id] { return draft }
                guard let index = effect.rarities.firstIndex(of: effect.rarity),
                      effect.rarities.indices.contains(index + 1) else { return effect.rarity }
                return effect.rarities[index + 1]
            },
            set: { dummyRarityDrafts[effect.id] = $0 }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Label(isEnglish ? "Boon Management" : "祝福管理", systemImage: "slider.horizontal.3")
                    .font(.subheadline.weight(.medium))
                    .fixedSize()

                Picker(isEnglish ? "Managed Effect" : "管理对象", selection: $selection) {
                    ForEach(pickerGroups) { group in
                        Section(header: Text(group.title)) {
                            ForEach(group.items) { option in
                                Text("\(option.title) · \(option.subtitle)").tag(option.id)
                            }
                        }
                    }
                }
                .labelsHidden()
                .frame(maxWidth: .infinity)

                TextField(isEnglish ? "Search current effects" : "搜索本局效果", text: $search)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 250)
            }

            HStack(spacing: 10) {
                selectedStatus
                    .frame(minWidth: 160, maxWidth: 230, alignment: .leading)

                specialControls

                Spacer(minLength: 10)

                commonLevelControls
                Divider().frame(height: 26)
                commonRarityControls
                commonRemoveControl
            }
            .frame(minHeight: 34)
        }
    }

    private var selectedStatus: some View {
        Group {
            if let trait = selectedLive {
                let rarity = trait.rarity.isEmpty ? "" : " · \(rarityLabel(trait.rarity))"
                Text("\(liveName(trait)) · Lv. \(trait.level)\(rarity)")
            } else if let effect = selectedDummy {
                Text(dummyStatus(effect))
            } else {
                Text(isEnglish ? "Select an effect" : "请选择一个效果")
            }
        }
        .font(.caption)
        .foregroundStyle(theme.mutedFill)
        .lineLimit(2)
    }

    @ViewBuilder
    private var specialControls: some View {
        if let trait = selectedLive, trait.family == "chaos", trait.canAdvanceLifecycle {
            Button(text("hades2.traits.chaos.advance")) {
                model.advanceTraitLifecycle(trait)
            }
            .buttonStyle(.bordered)
            .disabled(!model.canOpenNativeBoonScreen)
        } else if let effect = selectedDummy, !dummyRemoved.contains(effect.id) {
            switch effect.kind {
            case .chaos:
                Button(isEnglish ? "Transform Now" : "立即转化") {
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Blessing phase · transformed immediately (dummy)"
                        : "祝福阶段 · 已立即完成转化（dummy）"
                }
                .buttonStyle(.bordered)

            case .hex:
                Button(isEnglish ? "Reset Talents" : "重置天赋") {
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Slotted · talents 0 / 8 (dummy)"
                        : "已装备 · 天赋 0 / 8（dummy）"
                }
                .buttonStyle(.bordered)
                Button(isEnglish ? "Activate All" : "全部激活") {
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Slotted · talents 8 / 8 (forced dummy)"
                        : "已装备 · 天赋 8 / 8（强制 dummy）"
                }
                .buttonStyle(.bordered)

            case .hexTalent:
                Button(isEnglish ? "Toggle Talent" : "切换天赋") {
                    let next = !(dummyToggleStates[effect.id] ?? true)
                    dummyToggleStates[effect.id] = next
                    dummyStatusOverrides[effect.id] = next
                        ? (isEnglish ? "Talent ON · linked to current Hex (dummy)" : "天赋 ON · 隶属当前巫咒（dummy）")
                        : (isEnglish ? "Talent OFF · linked state retained (dummy)" : "天赋 OFF · 保留关联状态（dummy）")
                }
                .buttonStyle(.bordered)

            case .hammer:
                Picker("", selection: Binding(
                    get: { dummyReplacement[effect.id] ?? "B" },
                    set: { dummyReplacement[effect.id] = $0 }
                )) {
                    Text(isEnglish ? "Upgrade B" : "强化 B").tag("B")
                    Text(isEnglish ? "Upgrade C" : "强化 C").tag("C")
                }
                .labelsHidden()
                .frame(width: 105)
                Button(isEnglish ? "Replace" : "替换") {
                    let target = dummyReplacement[effect.id] ?? "B"
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Current upgrade: Upgrade \(target) (dummy)"
                        : "当前强化：强化 \(target)（dummy）"
                }
                .buttonStyle(.bordered)

            case .costume:
                Picker("", selection: Binding(
                    get: { dummyReplacement[effect.id] ?? "B" },
                    set: { dummyReplacement[effect.id] = $0 }
                )) {
                    Text(isEnglish ? "Costume B" : "服装 B").tag("B")
                    Text(isEnglish ? "Costume C" : "服装 C").tag("C")
                }
                .labelsHidden()
                .frame(width: 105)
                Button(isEnglish ? "Change" : "更换") {
                    let target = dummyReplacement[effect.id] ?? "B"
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Costume \(target) · appearance/armor synced (dummy)"
                        : "服装 \(target) · 外观/护甲已同步（dummy）"
                }
                .buttonStyle(.bordered)

            case .temporary:
                TextField(isEnglish ? "Uses" : "剩余场次", text: Binding(
                    get: { dummyRemaining[effect.id] ?? "3" },
                    set: { dummyRemaining[effect.id] = $0 }
                ))
                .textFieldStyle(.roundedBorder)
                .frame(width: 68)
                Button(isEnglish ? "Apply Duration" : "应用时长") {
                    let value = dummyRemaining[effect.id] ?? "3"
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "\(value) encounters left (dummy)"
                        : "剩余 \(value) 场（dummy）"
                }
                .buttonStyle(.bordered)
                Button(isEnglish ? "Expire Now" : "立即到期") {
                    dummyStatusOverrides[effect.id] = isEnglish
                        ? "Expired · expiry side effects executed (dummy)"
                        : "已到期 · 已执行到期副作用（dummy）"
                }
                .buttonStyle(.bordered)

            case .npc, .echo, .familiar, .progression:
                EmptyView()
            }
        }
    }

    @ViewBuilder
    private var commonLevelControls: some View {
        if let trait = selectedLive {
            commonLevelEditor(
                binding: liveLevelBinding(trait),
                enabled: model.canOpenNativeBoonScreen && trait.canIncreaseLevel
            ) {
                model.setTraitLevel(trait, targetLevel: liveLevelBinding(trait).wrappedValue)
            }
        } else if let effect = selectedDummy {
            commonLevelEditor(
                binding: dummyLevelBinding(effect),
                enabled: effect.canLevel && !dummyRemoved.contains(effect.id)
            ) {
                let value = dummyLevelBinding(effect).wrappedValue
                dummyStatusOverrides[effect.id] = isEnglish
                    ? "Level changed to \(value) (dummy)"
                    : "等级已改为 \(value)（dummy）"
            }
        } else {
            commonLevelEditor(binding: .constant(""), enabled: false) {}
        }
    }

    private func commonLevelEditor(
        binding: Binding<String>,
        enabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 5) {
            Text(isEnglish ? "Level" : "等级").font(.caption2).foregroundStyle(.secondary)
            TextField("", text: binding)
                .textFieldStyle(.roundedBorder)
                .frame(width: 52)
                .disabled(!enabled)
            Button(text("hades2.traits.apply"), action: action)
                .buttonStyle(.bordered)
                .disabled(!enabled)
        }
    }

    @ViewBuilder
    private var commonRarityControls: some View {
        if let trait = selectedLive {
            commonRarityEditor(
                selection: liveRarityBinding(trait),
                options: trait.availableRarities,
                enabled: model.canOpenNativeBoonScreen && trait.canSetRarity
            ) {
                model.setTraitRarity(trait, rarity: liveRarityBinding(trait).wrappedValue)
            }
        } else if let effect = selectedDummy {
            commonRarityEditor(
                selection: dummyRarityBinding(effect),
                options: effect.rarities,
                enabled: effect.canRarity && !dummyRemoved.contains(effect.id)
            ) {
                let rarity = dummyRarityBinding(effect).wrappedValue
                dummyStatusOverrides[effect.id] = isEnglish
                    ? "Rarity changed to \(rarityLabel(rarity)) (dummy)"
                    : "稀有度已改为 \(rarityLabel(rarity))（dummy）"
            }
        } else {
            commonRarityEditor(selection: .constant(""), options: [], enabled: false) {}
        }
    }

    private func commonRarityEditor(
        selection: Binding<String>,
        options: [String],
        enabled: Bool,
        action: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 5) {
            Text(isEnglish ? "Rarity" : "稀有度").font(.caption2).foregroundStyle(.secondary)
            Picker("", selection: selection) {
                if options.isEmpty {
                    Text("—").tag("")
                } else {
                    ForEach(options, id: \.self) { rarity in
                        Text(rarityLabel(rarity)).tag(rarity)
                    }
                }
            }
            .labelsHidden()
            .frame(width: 102)
            .disabled(!enabled)
            Button(text("hades2.traits.apply"), action: action)
                .buttonStyle(.bordered)
                .disabled(!enabled)
        }
    }

    @ViewBuilder
    private var commonRemoveControl: some View {
        if let trait = selectedLive {
            Button(role: .destructive) {
                model.removeTrait(trait)
            } label: {
                Text(text("hades2.traits.remove"))
            }
            .buttonStyle(.bordered)
            .disabled(!model.canOpenNativeBoonScreen || !trait.canRemove)
        } else if let effect = selectedDummy {
            Button(role: .destructive) {
                dummyRemoved.insert(effect.id)
                dummyStatusOverrides[effect.id] = isEnglish
                    ? removalOutcomeEnglish(effect)
                    : removalOutcomeChinese(effect)
            } label: {
                Text(text("hades2.traits.remove"))
            }
            .buttonStyle(.bordered)
            .disabled(!effect.canRemove || dummyRemoved.contains(effect.id))
        } else {
            Button(role: .destructive) {} label: {
                Text(text("hades2.traits.remove"))
            }
            .buttonStyle(.bordered)
            .disabled(true)
        }
    }

    private func removalOutcomeChinese(_ effect: DummyEffect) -> String {
        switch effect.kind {
        case .chaos: return "已取消配对 · 不触发转化（dummy）"
        case .costume: return "已删除 · 外观与护甲已恢复（dummy）"
        case .temporary: return "已取消临时效果 · 不执行到期副作用（dummy）"
        case .familiar: return "已清理本局关联效果 · 永久成长不变（dummy）"
        case .progression: return "已清理本局效果 · 永久解锁/装备不变（dummy）"
        default: return "已删除（dummy）"
        }
    }

    private func removalOutcomeEnglish(_ effect: DummyEffect) -> String {
        switch effect.kind {
        case .chaos: return "Pair cancelled · no transformation triggered (dummy)"
        case .costume: return "Removed · appearance and armor restored (dummy)"
        case .temporary: return "Temporary effect cancelled · no expiry side effects (dummy)"
        case .familiar: return "Runtime-linked effect cleaned · permanent progression unchanged (dummy)"
        case .progression: return "Runtime effect cleaned · permanent ownership/equipment unchanged (dummy)"
        default: return "Removed (dummy)"
        }
    }
}