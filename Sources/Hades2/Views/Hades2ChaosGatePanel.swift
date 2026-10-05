import SwiftUI

struct Hades2ChaosGatePanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var custom = false
    @State private var percentage = "100"

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }
    private func synchronize() {
        custom = model.chaosGateProbability != nil
        percentage = model.chaosGateProbability.map { String(format: "%g", $0) } ?? "100"
    }
    var body: some View {
        TrainerSection(title: text("hades2.chaosGate.title"), icon: "door.left.hand.open") {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Picker(text("hades2.gathering.mode"), selection: $custom) {
                        Text(text("hades2.gathering.native")).tag(false)
                        Text(text("hades2.gathering.custom")).tag(true)
                    }.frame(width: 240).disabled(!model.canEditDesired)
                    TextField(text("hades2.gathering.percent"), text: $percentage)
                        .textFieldStyle(.roundedBorder).frame(width: 65)
                        .disabled(!model.canEditDesired || !custom)
                        .accessibilityLabel(Text(text("hades2.chaosGate.title") + " " + text("hades2.gathering.percent")))
                    Text("%").foregroundStyle(.secondary)
                    Button(text("hades2.chaosGate.apply")) { model.setChaosGateProbability(custom: custom, text: percentage) }
                        .disabled(!model.canEditDesired || (custom && !model.validProbabilityPercentage(percentage)))
                    Spacer(minLength: 0)
                }
                Text(text("hades2.chaosGate.explanation")).font(.caption).foregroundStyle(.secondary)
                Text(text("hades2.chaosGate.lifecycle")).font(.caption).foregroundStyle(.secondary)
            }
        }
        .onAppear { synchronize() }
        .onChange(of: model.chaosGateProbability) { synchronize() }
    }
}
