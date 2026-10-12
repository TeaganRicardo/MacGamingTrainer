import SwiftUI

struct Hades2ChaosGatePanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var editing = false
    @State private var custom = false
    @State private var percentage = "100"

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }
    private func synchronize() {
        guard !editing else { return }
        custom = model.chaosGateProbability != nil
        percentage = model.chaosGateProbability.map { String(format: "%g", $0) } ?? "100"
    }
    var body: some View {
        let generation = model.editGeneration
        return TrainerSection(title: text("hades2.chaosGate.title"), icon: "door.left.hand.open") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Toggle(text("hades2.gathering.custom"), isOn: Binding(
                        get: { custom },
                        set: { enabled in
                            custom = enabled
                            if !enabled {
                                model.setChaosGateProbability(custom: false, text: "")
                            } else {
                                model.setChaosGateProbability(custom: true, text: percentage)
                            }
                        }
                    ))
                    .toggleStyle(.switch)
                    .disabled(!model.canEditDesired)
                    TrainerTextField(title: text("hades2.gathering.percent"), text: $percentage, onEditingChanged: { editing = $0 }, onCommit: { value in
                        model.completeTextEdit(.chaosGate, text: value.text, changed: value.changed, generation: generation)
                    })
                    .frame(width: 65)
                    .disabled(!model.canEditDesired || !custom)
                    .accessibilityLabel(Text(text("hades2.chaosGate.title") + " " + text("hades2.gathering.percent")))
                    Text("%").foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
            }
        }
        .onAppear { synchronize() }
        .onChange(of: model.chaosGateProbability) { synchronize() }
    }
}
