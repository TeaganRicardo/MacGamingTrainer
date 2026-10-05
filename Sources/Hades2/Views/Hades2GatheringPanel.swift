import SwiftUI

/// Hades wire families. Native generation and collection strategy stays in Lua.
enum Hades2GatheringFamily: String, CaseIterable, Identifiable {
    case flora, mining, digging, shades, fishing
    var id: String { rawValue }
    var titleKey: String { "hades2.gathering.family.\(rawValue)" }
    var collectionKey: String { "hades2.gathering.collection.\(rawValue)" }
}

struct Hades2GatheringTarget {
    let available: Bool
    let scopeToken: String?
    let reason: String?
}

struct Hades2GatheringPanel: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var custom: [Hades2GatheringFamily: Bool] = [:]
    @State private var percentages: [Hades2GatheringFamily: String] = [:]

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }
    private func synchronize(_ families: [Hades2GatheringFamily] = Hades2GatheringFamily.allCases) {
        for family in families {
            custom[family] = model.gatheringProbabilities[family] != nil
            percentages[family] = model.gatheringProbabilities[family].map { String(format: "%g", $0) } ?? "100"
        }
    }
    var body: some View {
        TrainerSection(title: text("hades2.gathering.title"), icon: "leaf") {
            VStack(alignment: .leading, spacing: 12) {
                Text(text("hades2.gathering.explanation")).font(.caption).foregroundStyle(.secondary)
                ForEach(Hades2GatheringFamily.allCases) { family in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 10) {
                            Text(text(family.titleKey)).font(.subheadline.weight(.medium)).frame(width: 120, alignment: .leading)
                            Picker(text("hades2.gathering.mode"), selection: Binding(get: { custom[family] ?? false }, set: { custom[family] = $0 })) {
                                Text(text("hades2.gathering.native")).tag(false)
                                Text(text("hades2.gathering.custom")).tag(true)
                            }.labelsHidden().frame(width: 150).disabled(!model.canEditDesired)
                            TextField(text("hades2.gathering.percent"), text: Binding(get: { percentages[family] ?? "100" }, set: { percentages[family] = $0 }))
                                .textFieldStyle(.roundedBorder).frame(width: 65).disabled(!model.canEditDesired || custom[family] != true)
                                .accessibilityLabel(Text(text(family.titleKey) + " " + text("hades2.gathering.percent")))
                            Text("%").foregroundStyle(.secondary)
                            Button(text("hades2.gathering.apply")) {
                                model.setGatheringProbability(family, custom: custom[family] == true, text: percentages[family] ?? "100")
                            }.disabled(!model.canEditDesired || (custom[family] == true && !model.validGatheringPercentage(percentages[family] ?? "")))
                            Spacer(minLength: 0)
                            Button(text("hades2.gathering.generate")) { model.generateGathering(family) }
                                .disabled(!model.canGenerateGathering(family))
                        }
                        Text(text(family.collectionKey)).font(.caption).foregroundStyle(.secondary)
                        if let reason = model.gatheringTargets[family]?.reason {
                            Text(text(reason)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if family != Hades2GatheringFamily.allCases.last { Divider() }
                }
                Text(text("hades2.gathering.generateHelp")).font(.caption).foregroundStyle(.secondary)
            }
        }
        .onAppear { synchronize() }
        .onChange(of: model.gatheringProbabilities) { previous, current in
            synchronize(Hades2GatheringFamily.allCases.filter { previous[$0] != current[$0] })
        }
    }
}
