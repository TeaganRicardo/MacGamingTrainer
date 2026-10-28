import SwiftUI

struct Hades2BoonRarityPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        let state = model.featurePresentation(.boonRarityEnabled, enabled: model.boonRarityEnabled)
            .trainerControlState(using: theme, localization: localization)
        return VStack(spacing: 1) {
            TrainerLabeledControlRow(
                title: text("hades2.rarity.title"), icon: TrainerSemanticIcon.Concept.quality,
                tint: state.indicatorColor, emphasized: state.isOn, opacity: state.opacity
            ) {
                Picker(text("hades2.rarity.minimum"), selection: Binding(
                    get: { model.boonRarityTarget },
                    set: { model.setBoonRarity(target: $0,
                        forceLegendary: model.boonForceLegendary, forceDuo: model.boonForceDuo) }
                )) {
                    ForEach(["Common", "Rare", "Epic", "Heroic"], id: \.self) { rarity in
                        Text(text("hades2.rarity." + rarity)).tag(rarity)
                    }
                }
                .labelsHidden()
                .frame(width: 150)
                .disabled(!model.canEditDesired)
                TrainerShortcutBadgeSlot(text: model.shortcutText(.boonRarityEnabled))
                TrainerToggleControl(
                    title: text("hades2.rarity.title"), isOn: model.boonRarityEnabled,
                    enabled: state.isInteractive, helpText: state.helpText,
                    tint: state.indicatorColor,
                    onChange: { model.feature(.boonRarityEnabled, value: $0) }
                )
            }
            TrainerRow {
                HStack(spacing: 18) {
                    HStack(spacing: 8) {
                        TrainerCheckboxControl(
                            title: text("hades2.rarity.legendary"), isOn: model.boonForceLegendary,
                            enabled: model.canEditDesired && model.boonRarityEnabled,
                            onChange: { model.setBoonRarity(target: model.boonRarityTarget,
                                forceLegendary: $0, forceDuo: model.boonForceDuo) }
                        )
                        TrainerShortcutBadge(text: model.shortcutText(.forceLegendary))
                    }
                    HStack(spacing: 8) {
                        TrainerCheckboxControl(
                            title: text("hades2.rarity.duo"), isOn: model.boonForceDuo,
                            enabled: model.canEditDesired && model.boonRarityEnabled,
                            onChange: { model.setBoonRarity(target: model.boonRarityTarget,
                                forceLegendary: model.boonForceLegendary, forceDuo: $0) }
                        )
                        TrainerShortcutBadge(text: model.shortcutText(.forceDuo))
                    }
                    Spacer()
                }
            }
        }
        .trainerGroupedRows()
    }
}
