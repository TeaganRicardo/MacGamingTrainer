import SwiftUI

struct Hades2GatheringPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var focusedFamily: Hades2GatheringFamily?
    @State private var custom: [Hades2GatheringFamily: Bool] = [:]
    @State private var percentages: [Hades2GatheringFamily: String] = [:]

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }
    private func synchronize(_ families: [Hades2GatheringFamily] = Hades2GatheringFamily.allCases) {
        for family in families where focusedFamily != family {
            custom[family] = model.gatheringProbabilities[family] != nil
            percentages[family] = model.gatheringProbabilities[family].map { String(format: "%g", $0) } ?? "100"
        }
    }
    var body: some View {
        let generation = model.editGeneration
        return TrainerSection(title: text("hades2.gathering.title"), icon: "leaf") {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Hades2GatheringFamily.allCases) { family in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 10) {
                            Text(text(family.titleKey)).font(.subheadline.weight(.medium)).frame(width: 120, alignment: .leading)
                            Toggle(text("hades2.gathering.custom"), isOn: Binding(
                                get: { custom[family] ?? false },
                                set: { enabled in
                                    custom[family] = enabled
                                    if !enabled {
                                        model.setGatheringProbability(family, custom: false, text: "")
                                    } else {
                                        model.setGatheringProbability(family, custom: true, text: percentages[family] ?? "100")
                                    }
                                }
                            ))
                            .toggleStyle(.switch)
                            .disabled(!model.canEditDesired)
                            let draft = Binding<String>(get: { percentages[family] ?? "100" }, set: { percentages[family] = $0 })
                            TrainerTextField(title: text("hades2.gathering.percent"), text: draft, onEditingChanged: TrainerTextField.editingTracker($focusedFamily, equals: family), onCommit: { value in
                                model.completeTextEdit(.gathering(family), text: value.text, changed: value.changed, generation: generation)
                            })
                            .frame(width: 65)
                            .disabled(!model.canEditDesired || custom[family] != true)
                            .accessibilityLabel(Text(text(family.titleKey) + " " + text("hades2.gathering.percent")))
                            Text("%").foregroundStyle(.secondary)
                            Spacer(minLength: 0)
                            Button(text("hades2.gathering.generate")) { model.generateGathering(family) }
                                .disabled(!model.canGenerateGathering(family))
                        }
                        if let reason = model.gatheringTargets[family]?.reason {
                            Text(text(reason)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if family != Hades2GatheringFamily.allCases.last { Divider() }
                }
            }
        }
        .onAppear { synchronize() }
        .onChange(of: model.gatheringProbabilities) { previous, current in
            synchronize(Hades2GatheringFamily.allCases.filter { previous[$0] != current[$0] })
        }
    }
}
