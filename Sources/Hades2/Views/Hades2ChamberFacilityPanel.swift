import SwiftUI

/// The options and one-shot scope tokens come from the live native chamber
/// owner. The offline row remains visible, with no fabricated selectable props.
struct Hades2ChamberFacilityPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerLabeledControlRow(
            title: text("hades2.facility.title"),
            icon: TrainerSemanticIcon.Action.generate,
            tint: model.canGenerateFacility ? theme.accent : theme.inactive,
            emphasized: false,
            layout: .pickerAction
        ) {
            Picker(text("hades2.facility.title"), selection: $model.selectedFacilityID) {
                if model.facilityOptions.isEmpty {
                    Text(text("hades2.facility.empty")).tag("")
                }
                ForEach(model.facilityOptions) { facility in
                    Text(text(facility.labelKey)).tag(facility.id)
                }
            }
            .labelsHidden()
            .trainerPicker(
                .rowAction,
                state: model.canGenerateFacility ? .interactive : .unavailable
            )
            .disabled(!model.canGenerateFacility)
            .accessibilityIdentifier("hades2.facility.selection")
            TrainerShortcutBadgeSlot(text: model.shortcutText(.generateChamberFacility))
            TrainerSecondaryActionButton(
                title: text("hades2.facility.generate"),
                systemImage: TrainerSemanticIcon.Action.generate,
                enabled: model.canGenerateFacility,
                helpText: text("hades2.facility.help"),
                accessibilityLabel: text("hades2.facility.title")
            ) { _ = model.generateChamberFacility() }
        }
        .trainerGroupedRows()
    }
}
