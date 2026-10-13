import SwiftUI

struct Hades2GatheringPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var focusedFamily: Hades2GatheringFamily?
    @State private var percentages: [Hades2GatheringFamily: String] = [:]

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    private func synchronize(_ families: [Hades2GatheringFamily] = Hades2GatheringFamily.allCases) {
        for family in families where focusedFamily != family {
            percentages[family] = model.gatheringProbabilities[family].map { String(format: "%g", $0) } ?? ""
        }
    }

    private func icon(for family: Hades2GatheringFamily) -> String {
        switch family {
        case .flora: "leaf.fill"
        case .mining: "hammer.fill"
        case .digging: "mountain.2.fill"
        case .shades: "person.crop.circle"
        case .fishing: "fish.fill"
        }
    }

    var body: some View {
        let generation = model.editGeneration
        return TrainerSection(title: text("hades2.gathering.title"), icon: "leaf") {
            VStack(spacing: 1) {
                ForEach(Hades2GatheringFamily.allCases) { family in
                    Hades2ProbabilityRow(
                        title: text(family.titleKey),
                        icon: icon(for: family),
                        input: Binding(
                            get: { percentages[family] ?? "" },
                            set: { percentages[family] = $0 }
                        ),
                        hasOverride: model.gatheringProbabilities[family] != nil,
                        enabled: model.canEditDesired,
                        probabilityLabel: text("hades2.gathering.percent"),
                        nativeLabel: text("hades2.gathering.native"),
                        resetLabel: text("hades2.gathering.restoreNative"),
                        probabilityHelp: text("hades2.gathering.explanation") + "\n" + text(family.collectionKey),
                        onEditingChanged: TrainerTextField.editingTracker($focusedFamily, equals: family),
                        onCommit: { completion in
                            model.completeTextEdit(.gathering(family), text: completion.text,
                                changed: completion.changed, generation: generation)
                        },
                        onReset: { model.setGatheringProbability(family, probability: nil) },
                        generateLabel: text("hades2.gathering.generate"),
                        generateHelp: model.gatheringTargets[family]?.reason.map { text($0) }
                            ?? text("hades2.gathering.generateHelp"),
                        canGenerate: model.canGenerateGathering(family),
                        onGenerate: { model.generateGathering(family) }
                    )
                }
            }
        }
        .onAppear { synchronize() }
        .onChange(of: model.gatheringProbabilities) { previous, current in
            synchronize(Hades2GatheringFamily.allCases.filter { previous[$0] != current[$0] })
        }
    }
}
