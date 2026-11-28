import SwiftUI
import TrainerCore

struct Hades2BoonRarityPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String {
        localization.string(key)
    }

    private var forceOptions: some View {
        let enabled = model.canEditDesired && model.boonRarityEnabled
        return HStack(spacing: 8) {
            TrainerCheckboxControl(
                title: text("hades2.rarity.legendary"), isOn: model.boonForceLegendary, enabled: enabled,
                onChange: { model.setBoonRarity(target: model.boonRarityTarget,
                    forceLegendary: $0, forceDuo: model.boonForceDuo) }
            )
            .fixedSize(horizontal: true, vertical: false)
            .accessibilityIdentifier("hades2.feature.forceLegendary")
            TrainerCheckboxControl(
                title: text("hades2.rarity.duo"), isOn: model.boonForceDuo, enabled: enabled,
                onChange: { model.setBoonRarity(target: model.boonRarityTarget,
                    forceLegendary: model.boonForceLegendary, forceDuo: $0) }
            )
            .fixedSize(horizontal: true, vertical: false)
            .accessibilityIdentifier("hades2.feature.forceDuo")
        }
    }

    var body: some View {
        let definition = Hades2CheatCatalog.definition(id: "boonRarityEnabled")!
        let title = definition.label.resolve(using: localization)
        let state = model.featurePresentation(.boonRarityEnabled, enabled: model.boonRarityEnabled)
            .trainerControlState(using: theme, localization: localization)
        return TrainerLabeledControlRow(
            title: title, icon: definition.icon,
            tint: state.indicatorColor, emphasized: state.isOn, opacity: state.opacity
        ) {
            forceOptions
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
            .trainerPicker(.compactValue, state: model.canEditDesired ? .interactive : .unavailable)
            TrainerShortcutBadgeSlot(text: model.shortcutText(.boonRarityEnabled))
            TrainerToggleControl(
                title: title, isOn: model.boonRarityEnabled,
                enabled: state.isInteractive, helpText: state.helpText,
                tint: state.indicatorColor,
                onChange: { model.feature(.boonRarityEnabled, value: $0) }
            )
        }
        .trainerGroupedRows()
    }
}
