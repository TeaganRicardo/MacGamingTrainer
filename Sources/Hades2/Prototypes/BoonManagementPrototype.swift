import SwiftUI

// PROTOTYPE ONLY — Variant F.
// Disclosure-first version embedded in the real Hades page. Existing/new
// special-owner actions are represented as presentation-only dummies.
struct BoonManagementPrototypeView: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var acquireSearch = ""
    @State private var runSearch = ""
    @State private var expandedSources: Set<String> = ["olympian"]
    @State private var expandedCurrent: Set<String> = ["chaos"]
    @State private var levelDrafts: [String: String] = ["zeus": "4", "hex": "5", "familiar": "4"]
    @State private var rarityDrafts: [String: String] = ["zeus": "英雄"]

    private enum Special {
        case ordinary
        case chaos
        case hex
        case hammer
        case familiar
    }

    private struct Item: Identifiable {
        let id: String
        let group: String
        let groupZh: String
        let groupEn: String
        let zh: String
        let en: String
        let sourceZh: String
        let sourceEn: String
        let stateZh: String
        let stateEn: String
        let detailZh: String
        let detailEn: String
        let canLevel: Bool
        let canRarity: Bool
        let special: Special
    }

    private let available: [Item] = [
        .init(
            id: "static", group: "olympian", groupZh: "奥林匹斯诸神", groupEn: "Olympians",
            zh: "静电震颤", en: "Static Shock", sourceZh: "宙斯", sourceEn: "Zeus",
            stateZh: "可直接获取", stateEn: "Direct acquisition",
            detailZh: "常规祝福", detailEn: "Standard boon",
            canLevel: true, canRarity: true, special: .ordinary
        ),
        .init(
            id: "dash", group: "olympian", groupZh: "奥林匹斯诸神", groupEn: "Olympians",
            zh: "疾风冲刺", en: "Gale Dash", sourceZh: "赫尔墨斯", sourceEn: "Hermes",
            stateZh: "可直接获取", stateEn: "Direct acquisition",
            detailZh: "常规祝福", detailEn: "Standard boon",
            canLevel: true, canRarity: true, special: .ordinary
        ),
        .init(
            id: "chaos-acquire", group: "chaos", groupZh: "卡俄斯", groupEn: "Chaos",
            zh: "丰盛", en: "Abundance", sourceZh: "卡俄斯", sourceEn: "Chaos",
            stateZh: "配对生命周期", stateEn: "Paired lifecycle",
            detailZh: "获取时建立诅咒 → 祝福配对", detailEn: "Acquisition creates a curse → blessing pair",
            canLevel: true, canRarity: true, special: .chaos
        ),
        .init(
            id: "hex-acquire", group: "selene", groupZh: "塞勒涅", groupEn: "Selene",
            zh: "月光射线", en: "Moonlight Ray", sourceZh: "塞勒涅 · 巫咒", sourceEn: "Selene · Hex",
            stateZh: "后端待接入", stateEn: "Backend pending",
            detailZh: "用于验证未来巫咒操作的信息密度", detailEn: "Dummy row for future Hex action density",
            canLevel: true, canRarity: false, special: .hex
        ),
        .init(
            id: "hammer-acquire", group: "weapon", groupZh: "武器强化", groupEn: "Weapon Upgrades",
            zh: "旋月重击", en: "Moon-Arc Smash", sourceZh: "代达罗斯", sourceEn: "Daedalus",
            stateZh: "后端待接入", stateEn: "Backend pending",
            detailZh: "用于验证替换/移除动作布局", detailEn: "Dummy row for replace/remove actions",
            canLevel: false, canRarity: false, special: .hammer
        ),
    ]

    private let current: [Item] = [
        .init(
            id: "zeus", group: "olympian", groupZh: "奥林匹斯诸神", groupEn: "Olympians",
            zh: "静电震颤", en: "Static Shock", sourceZh: "宙斯", sourceEn: "Zeus",
            stateZh: "Lv. 3 · 史诗", stateEn: "Lv. 3 · Epic",
            detailZh: "普通祝福，只显示通用编辑能力。", detailEn: "Ordinary boon with common edit capabilities only.",
            canLevel: true, canRarity: true, special: .ordinary
        ),
        .init(
            id: "hermes", group: "olympian", groupZh: "奥林匹斯诸神", groupEn: "Olympians",
            zh: "迅捷恢复", en: "Quick Recovery", sourceZh: "赫尔墨斯", sourceEn: "Hermes",
            stateZh: "Lv. 1 · 稀有", stateEn: "Lv. 1 · Rare",
            detailZh: "普通祝福保持单行摘要；需要修改时再展开。", detailEn: "Ordinary row stays compact until editing is requested.",
            canLevel: true, canRarity: true, special: .ordinary
        ),
        .init(
            id: "chaos", group: "chaos", groupZh: "卡俄斯", groupEn: "Chaos",
            zh: "命定诅咒", en: "Doomed Curse", sourceZh: "卡俄斯", sourceEn: "Chaos",
            stateZh: "诅咒 · 剩余 2 场 → 丰盛", stateEn: "Curse · 2 encounters → Abundance",
            detailZh: "当前阶段完成后转化为「丰盛」。立即转化与取消配对属于上下文动作。",
            detailEn: "Transforms into Abundance after the current phase. Transform/cancel are contextual actions.",
            canLevel: false, canRarity: false, special: .chaos
        ),
        .init(
            id: "hex", group: "selene", groupZh: "塞勒涅", groupEn: "Selene",
            zh: "月光射线", en: "Moonlight Ray", sourceZh: "塞勒涅", sourceEn: "Selene",
            stateZh: "巫咒 · 4 点强化", stateEn: "Hex · 4 upgrades",
            detailZh: "未来能力占位：强化树/重置等操作只在展开区出现。",
            detailEn: "Future placeholder: talent/reset actions appear only in disclosure.",
            canLevel: true, canRarity: false, special: .hex
        ),
        .init(
            id: "hammer", group: "weapon", groupZh: "武器强化", groupEn: "Weapon Upgrades",
            zh: "旋月重击", en: "Moon-Arc Smash", sourceZh: "代达罗斯", sourceEn: "Daedalus",
            stateZh: "武器强化", stateEn: "Weapon upgrade",
            detailZh: "未来能力占位：替换或强制移除。", detailEn: "Future placeholder: replace or force-remove.",
            canLevel: false, canRarity: false, special: .hammer
        ),
        .init(
            id: "familiar", group: "familiar", groupZh: "魔宠", groupEn: "Familiars",
            zh: "魔宠强化", en: "Familiar Upgrade", sourceZh: "魔宠", sourceEn: "Familiar",
            stateZh: "成长等级 3", stateEn: "Progression level 3",
            detailZh: "未来能力占位：成长效果相关操作。", detailEn: "Future placeholder: progression-linked actions.",
            canLevel: true, canRarity: false, special: .familiar
        ),
    ]

    private var isEnglish: Bool { localization.language == .en }
    private func t(_ zh: String, _ en: String) -> String { isEnglish ? en : zh }
    private func name(_ item: Item) -> String { isEnglish ? item.en : item.zh }
    private func source(_ item: Item) -> String { isEnglish ? item.sourceEn : item.sourceZh }
    private func state(_ item: Item) -> String { isEnglish ? item.stateEn : item.stateZh }
    private func detail(_ item: Item) -> String { isEnglish ? item.detailEn : item.detailZh }
    private func groupName(_ item: Item) -> String { isEnglish ? item.groupEn : item.groupZh }

    private var filteredAvailable: [Item] {
        guard !acquireSearch.isEmpty else { return available }
        return available.filter {
            [name($0), source($0), state($0), groupName($0)].contains {
                $0.localizedCaseInsensitiveContains(acquireSearch)
            }
        }
    }

    private var filteredCurrent: [Item] {
        guard !runSearch.isEmpty else { return current }
        return current.filter {
            [name($0), source($0), state($0), detail($0)].contains {
                $0.localizedCaseInsensitiveContains(runSearch)
            }
        }
    }

    private var availableGroups: [(String, [Item])] {
        let order = ["olympian", "chaos", "selene", "weapon"]
        return order.compactMap { key in
            let rows = filteredAvailable.filter { $0.group == key }
            return rows.isEmpty ? nil : (key, rows)
        }
    }

    private func levelBinding(_ id: String) -> Binding<String> {
        Binding(
            get: { levelDrafts[id] ?? "2" },
            set: { levelDrafts[id] = $0 }
        )
    }

    private func rarityBinding(_ id: String) -> Binding<String> {
        Binding(
            get: { rarityDrafts[id] ?? t("英雄", "Heroic") },
            set: { rarityDrafts[id] = $0 }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            acquisitionBlock
            Divider()
            currentRunBlock
            Text(t(
                "PROTOTYPE F · 摘要优先 / 按需展开 · 所有新增动作均为 dummy，不写入游戏。",
                "PROTOTYPE F · Summary-first disclosure · new actions are dummy-only."
            ))
            .font(.caption2)
            .foregroundStyle(theme.mutedFill)
        }
    }

    private var acquisitionBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            header(
                title: t("指定祝福", "Exact Boons"),
                icon: "scope",
                count: filteredAvailable.count,
                search: $acquireSearch,
                placeholder: t("搜索名称或来源", "Search name or source")
            )

            if filteredAvailable.isEmpty {
                TrainerEmptyState(text: t("没有匹配项", "No matches"))
            } else {
                VStack(spacing: 8) {
                    ForEach(availableGroups, id: \.0) { group in
                        acquisitionGroup(group.0, items: group.1)
                    }
                }
            }
        }
    }

    private func acquisitionGroup(_ key: String, items: [Item]) -> some View {
        let open = acquireSearch.isEmpty ? expandedSources.contains(key) : true
        return TrainerListCard {
            VStack(alignment: .leading, spacing: open ? 8 : 0) {
                Button {
                    if expandedSources.contains(key) {
                        expandedSources.remove(key)
                    } else {
                        expandedSources.insert(key)
                    }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: open ? "chevron.down" : "chevron.right")
                            .font(.caption.weight(.semibold))
                            .frame(width: 12)
                        Text(groupName(items[0]))
                            .font(.subheadline.weight(.semibold))
                        Text("\(items.count)")
                            .font(.caption2)
                            .foregroundStyle(theme.mutedFill)
                        Spacer()
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if open {
                    Divider()
                    VStack(spacing: 1) {
                        ForEach(items) { item in
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(name(item)).font(.subheadline.weight(.medium))
                                    Text(source(item))
                                        .font(.caption2)
                                        .foregroundStyle(theme.mutedFill)
                                }
                                Spacer()
                                if item.special != .ordinary {
                                    Text(state(item))
                                        .font(.caption2)
                                        .foregroundStyle(theme.mutedFill)
                                }
                                Button(t("获取", "Acquire")) {}
                                    .buttonStyle(.bordered)
                            }
                            .padding(.vertical, 6)
                        }
                    }
                }
            }
        }
    }

    private var currentRunBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Label(t("本局祝福与效果", "Current Boons & Effects"), systemImage: "list.bullet.rectangle")
                    .font(.subheadline.weight(.medium))
                Text("\(filteredCurrent.count)")
                    .font(.caption)
                    .foregroundStyle(theme.mutedFill)
                Spacer()
                Button {
                } label: {
                    Label(t("净化之池", "Pool of Purging"), systemImage: "arrow.left.arrow.right.circle")
                }
                .buttonStyle(.bordered)
                TextField(t("搜索当前效果", "Search current effects"), text: $runSearch)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 240)
            }

            if filteredCurrent.isEmpty {
                TrainerEmptyState(text: t("本局没有匹配项", "No matching current effects"))
            } else {
                VStack(spacing: 1) {
                    ForEach(filteredCurrent) { item in
                        disclosureRow(item)
                    }
                }
                .trainerGroupedRows()
            }
        }
    }

    private func disclosureRow(_ item: Item) -> some View {
        let open = expandedCurrent.contains(item.id)
        return TrainerRow(minimumHeight: open ? 118 : 52) {
            VStack(alignment: .leading, spacing: open ? 10 : 0) {
                Button {
                    if expandedCurrent.contains(item.id) {
                        expandedCurrent.remove(item.id)
                    } else {
                        expandedCurrent.insert(item.id)
                    }
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: open ? "chevron.down" : "chevron.right")
                            .font(.caption.weight(.semibold))
                            .frame(width: 12)
                            .foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(name(item)).font(.subheadline.weight(.semibold))
                            Text(source(item))
                                .font(.caption2)
                                .foregroundStyle(theme.mutedFill)
                        }
                        Spacer(minLength: 12)
                        Text(state(item))
                            .font(.caption)
                            .foregroundStyle(theme.mutedFill)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if open {
                    Divider()
                    Text(detail(item))
                        .font(.caption2)
                        .foregroundStyle(theme.mutedFill)

                    HStack(spacing: 10) {
                        if item.canLevel {
                            compactEditor(
                                title: t("等级", "Level"),
                                text: levelBinding(item.id),
                                width: 52
                            )
                        }
                        if item.canLevel && item.canRarity {
                            Divider().frame(height: 24)
                        }
                        if item.canRarity {
                            compactEditor(
                                title: t("稀有度", "Rarity"),
                                text: rarityBinding(item.id),
                                width: 82
                            )
                        }

                        Spacer(minLength: 8)

                        if item.special == .chaos {
                            Button(t("立即转化", "Transform Now")) {}
                                .buttonStyle(.bordered)
                        } else if item.special != .ordinary {
                            TrainerOverflowMenu {
                                Button(t("特殊操作（dummy）", "Special Action (dummy)")) {}
                                Button(t("查看关联状态", "View Related State")) {}
                            }
                        }

                        Button(role: .destructive) {
                        } label: {
                            Text(item.special == .chaos
                                ? t("取消这一对", "Cancel Pair")
                                : t("删除", "Remove"))
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
        }
    }

    private func header(
        title: String,
        icon: String,
        count: Int,
        search: Binding<String>,
        placeholder: String
    ) -> some View {
        HStack(spacing: 10) {
            Label(title, systemImage: icon)
                .font(.subheadline.weight(.medium))
            Text("\(count)")
                .font(.caption)
                .foregroundStyle(theme.mutedFill)
            Spacer()
            TextField(placeholder, text: search)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)
        }
    }

    private func compactEditor(title: String, text: Binding<String>, width: CGFloat) -> some View {
        HStack(spacing: 5) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            TextField(title, text: text)
                .textFieldStyle(.roundedBorder)
                .frame(width: width)
            Button(t("应用", "Apply")) {}
                .buttonStyle(.bordered)
        }
    }
}
