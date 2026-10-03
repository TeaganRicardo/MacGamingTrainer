import SwiftUI

// PROTOTYPE ONLY — Variant D.
// Native SwiftUI insertion inside the real Hades page. All actions below are
// presentation-only dummies so UX can be judged before #237–#240 are complete.
struct BoonManagementPrototypeView: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var acquireSearch = ""
    @State private var runSearch = ""
    @State private var levelDrafts: [String: String] = [
        "zeus": "4", "hex": "5", "familiar": "4",
    ]
    @State private var rarityDrafts: [String: String] = [
        "zeus": "英雄",
    ]

    private struct Item: Identifiable {
        let id: String
        let zh: String
        let en: String
        let sourceZh: String
        let sourceEn: String
        let stateZh: String
        let stateEn: String
        let canLevel: Bool
        let canRarity: Bool
        let special: Special
    }

    private enum Special {
        case ordinary
        case chaos
        case hex
        case hammer
        case familiar
    }

    private let available: [Item] = [
        .init(id: "static", zh: "静电震颤", en: "Static Shock", sourceZh: "宙斯 · 奥林匹斯", sourceEn: "Zeus · Olympian", stateZh: "可直接获取", stateEn: "Direct acquisition", canLevel: true, canRarity: true, special: .ordinary),
        .init(id: "chaos-acquire", zh: "丰盛", en: "Abundance", sourceZh: "卡俄斯 · 祝福", sourceEn: "Chaos · Blessing", stateZh: "配对生命周期", stateEn: "Paired lifecycle", canLevel: true, canRarity: true, special: .chaos),
        .init(id: "hex-acquire", zh: "月光射线", en: "Moonlight Ray", sourceZh: "塞勒涅 · 巫咒", sourceEn: "Selene · Hex", stateZh: "能力后端待接入", stateEn: "Backend pending", canLevel: true, canRarity: false, special: .hex),
        .init(id: "hammer-acquire", zh: "旋月重击", en: "Moon-Arc Smash", sourceZh: "代达罗斯 · 武器强化", sourceEn: "Daedalus · Weapon upgrade", stateZh: "能力后端待接入", stateEn: "Backend pending", canLevel: false, canRarity: false, special: .hammer),
        .init(id: "familiar-acquire", zh: "魔宠强化", en: "Familiar Upgrade", sourceZh: "魔宠 · 成长效果", sourceEn: "Familiar · Progression effect", stateZh: "能力后端待接入", stateEn: "Backend pending", canLevel: true, canRarity: false, special: .familiar),
    ]

    private let current: [Item] = [
        .init(id: "zeus", zh: "静电震颤", en: "Static Shock", sourceZh: "宙斯", sourceEn: "Zeus", stateZh: "Lv. 3 · 史诗", stateEn: "Lv. 3 · Epic", canLevel: true, canRarity: true, special: .ordinary),
        .init(id: "chaos", zh: "命定诅咒", en: "Doomed Curse", sourceZh: "卡俄斯", sourceEn: "Chaos", stateZh: "诅咒 · 剩余 2 场 → 丰盛", stateEn: "Curse · 2 encounters → Abundance", canLevel: false, canRarity: false, special: .chaos),
        .init(id: "hex", zh: "月光射线", en: "Moonlight Ray", sourceZh: "塞勒涅", sourceEn: "Selene", stateZh: "巫咒 · 4 点强化", stateEn: "Hex · 4 upgrades", canLevel: true, canRarity: false, special: .hex),
        .init(id: "hammer", zh: "旋月重击", en: "Moon-Arc Smash", sourceZh: "代达罗斯", sourceEn: "Daedalus", stateZh: "武器强化", stateEn: "Weapon upgrade", canLevel: false, canRarity: false, special: .hammer),
        .init(id: "familiar", zh: "魔宠强化", en: "Familiar Upgrade", sourceZh: "魔宠", sourceEn: "Familiar", stateZh: "成长等级 3", stateEn: "Progression level 3", canLevel: true, canRarity: false, special: .familiar),
    ]

    private var isEnglish: Bool { localization.language == .en }
    private func t(_ zh: String, _ en: String) -> String { isEnglish ? en : zh }
    private func name(_ item: Item) -> String { isEnglish ? item.en : item.zh }
    private func source(_ item: Item) -> String { isEnglish ? item.sourceEn : item.sourceZh }
    private func state(_ item: Item) -> String { isEnglish ? item.stateEn : item.stateZh }

    private var filteredAvailable: [Item] {
        guard !acquireSearch.isEmpty else { return available }
        return available.filter {
            [name($0), source($0), state($0)].contains {
                $0.localizedCaseInsensitiveContains(acquireSearch)
            }
        }
    }

    private var filteredCurrent: [Item] {
        guard !runSearch.isEmpty else { return current }
        return current.filter {
            [name($0), source($0), state($0)].contains {
                $0.localizedCaseInsensitiveContains(runSearch)
            }
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
                "PROTOTYPE D · 紧凑行式工作区 · 所有新动作均为 dummy，不写入游戏。",
                "PROTOTYPE D · Compact row workspace · new actions are dummy-only."
            ))
            .font(.caption2)
            .foregroundStyle(theme.mutedFill)
        }
    }

    private var acquisitionBlock: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Label(t("指定祝福", "Exact Boons"), systemImage: "scope")
                    .font(.subheadline.weight(.medium))
                Text("\(filteredAvailable.count)")
                    .font(.caption)
                    .foregroundStyle(theme.mutedFill)
                Spacer()
                TextField(t("搜索名称、来源或效果", "Search name, source, or effect"), text: $acquireSearch)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 280)
            }

            if filteredAvailable.isEmpty {
                TrainerEmptyState(text: t("没有匹配项", "No matches"))
            } else {
                VStack(spacing: 1) {
                    ForEach(filteredAvailable) { item in
                        TrainerRow(minimumHeight: 54) {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(name(item)).font(.subheadline.weight(.semibold))
                                    Text(source(item))
                                        .font(.caption2)
                                        .foregroundStyle(theme.mutedFill)
                                }
                                Spacer(minLength: 16)
                                Text(state(item))
                                    .font(.caption)
                                    .foregroundStyle(theme.mutedFill)
                                Button(t("获取", "Acquire")) {}
                                    .buttonStyle(.bordered)
                            }
                        }
                    }
                }
                .trainerGroupedRows()
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
                        currentRow(item)
                    }
                }
                .trainerGroupedRows()
            }
        }
    }

    @ViewBuilder
    private func currentRow(_ item: Item) -> some View {
        TrainerRow(minimumHeight: 62) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(name(item)).font(.subheadline.weight(.semibold))
                    Text(source(item))
                        .font(.caption2)
                        .foregroundStyle(theme.mutedFill)
                }
                .frame(minWidth: 140, maxWidth: 190, alignment: .leading)

                Text(state(item))
                    .font(.caption)
                    .foregroundStyle(theme.mutedFill)
                    .frame(minWidth: 100, alignment: .leading)

                Spacer(minLength: 6)

                if item.canLevel {
                    compactEditor(
                        title: t("等级", "Level"),
                        text: levelBinding(item.id),
                        width: 52
                    )
                }

                if item.canRarity {
                    Divider().frame(height: 24)
                    compactEditor(
                        title: t("稀有度", "Rarity"),
                        text: rarityBinding(item.id),
                        width: 82
                    )
                }

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
