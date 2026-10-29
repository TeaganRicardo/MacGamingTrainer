import SwiftUI

struct Hades2ChaosGatePanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var editing = false
    @State private var percentage = ""

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    private func synchronize() {
        guard !editing else { return }
        percentage = model.chaosGateProbability.map { String(format: "%g", $0) } ?? ""
    }

    var body: some View {
        let generation = model.editGeneration
        return Hades2OccurrenceSetting(
            title: text("hades2.chaosGate.probability"),
            icon: Hades2WorkbenchIcon.chaosProbability,
            input: $percentage,
            hasOverride: model.chaosGateProbability != nil,
            enabled: model.canEditDesired,
            probabilityLabel: text("hades2.gathering.percent"),
            nativeLabel: text("hades2.gathering.native"),
            resetLabel: text("hades2.gathering.restoreNative"),
            probabilityHelp: text("hades2.chaosGate.explanation") + "\n"
                + text("hades2.chaosGate.lifecycle"),
            onEditingChanged: { editing = $0 },
            onCommit: { completion in
                model.completeTextEdit(.chaosGate, text: completion.text,
                    changed: completion.changed, generation: generation)
            },
            onReset: { model.setChaosGateProbability(nil) }
        )
        .trainerGroupedRows()
        .onAppear { synchronize() }
        .onChange(of: model.chaosGateProbability) { _, _ in synchronize() }
        .onChange(of: model.editGeneration) { _, _ in synchronize() }
    }
}
