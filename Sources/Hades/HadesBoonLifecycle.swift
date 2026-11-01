import SwiftUI

struct HadesChaosPairControls: View {
    @ObservedObject var model: HadesTrainerModel
    let blessing: HadesCatalogEntry
    let rarity: String
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var curse = ""
    @State private var encounters = "3"

    private var curses: [HadesCatalogEntry] { model.catalog.filter { $0.kind == "curse" } }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            TrainerLabeledControlRow(title: text("hades.chaosCurse"), icon: TrainerSemanticIcon.Section.effects, tint: theme.accent, emphasized: model.canMutate) {
                Picker(text("hades.chaosCurse"), selection: $curse) {
                    ForEach(curses) { item in
                        Text(item.name(language: localization.language.rawValue)).tag(item.id)
                    }
                }
                .labelsHidden()
                .trainerPickerWidth(.standard)
            }
            TrainerLabeledControlRow(title: text("hades.chaosEncounters"), icon: TrainerSemanticIcon.Concept.duration, tint: theme.accent, emphasized: model.canMutate) {
                TrainerNumberField(text: $encounters, accessibilityLabel: text("hades.chaosEncounters"), width: 60,
                    onCommit: { completion in
                        guard let count = Int(completion.text), (1...100).contains(count) else {
                            return completion.rejected(message: text("hades.error.invalidValue"))
                        }
                        return String(count)
                    })
                    .id(blessing.id)
                TrainerSecondaryActionButton(title: text("hades.chaosPair"), systemImage: TrainerSemanticIcon.Action.acquire, enabled: model.canMutate && !curse.isEmpty) {
                    guard let count = Int(encounters), (1...100).contains(count) else {
                        model.rejectInvalidValue(); return
                    }
                    model.addChaosPair(blessing: blessing, curse: curse, rarity: rarity, encounters: count)
                }
            }
        }
        .onChange(of: curses.map(\.id), initial: true) { _, ids in
            if !ids.contains(curse) { curse = ids.first ?? "" }
        }
    }
}

struct HadesEffectLifecycleControls: View {
    @ObservedObject var model: HadesTrainerModel
    let trait: HadesCurrentTrait
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var uses = HadesNumberDraft(value: 0)

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let remaining = trait.remainingUses, trait.canSetUses == true {
                TrainerLabeledControlRow(title: text("hades.remainingUses"), icon: TrainerSemanticIcon.Concept.duration, tint: theme.accent, emphasized: model.canMutate) {
                    TrainerNumberField(
                        text: Binding(get: { uses.text }, set: { uses.update($0) }),
                        accessibilityLabel: text("hades.remainingUses"), width: 64, enabled: model.canMutate,
                        onEditingChanged: { active in
                            if active { uses.begin(target: model.target) } else { uses.end() }
                        },
                        onCommit: { completed in
                            guard completed.changed else { return completed.text }
                            guard let value = Int(completed.text), (0...1000).contains(value) else {
                                model.rejectInvalidValue()
                                return completed.rejected(message: text("hades.error.invalidValue"))
                            }
                            model.setTraitUses(trait, uses: value, target: uses.target)
                            return String(value)
                        }
                    )
                }
                .onChange(of: remaining, initial: true) { _, value in uses.observe(Double(value)) }
            }
            HStack(spacing: 10) {
                if trait.canRefresh == true {
                    TrainerSecondaryActionButton(title: text("hades.refreshEffect"), systemImage: TrainerSemanticIcon.Concept.refresh, enabled: model.canMutate) {
                        model.refreshTrait(trait)
                    }
                }
                if trait.canExpire == true {
                    TrainerSecondaryActionButton(
                        title: text(trait.blessing == nil ? "hades.expireEffect" : "hades.activateBlessing"),
                        systemImage: trait.blessing == nil ? "hourglass.bottomhalf.filled" : "bolt.fill",
                        enabled: model.canMutate && trait.canRemove
                    ) { model.expireTrait(trait) }
                }
                if trait.canRemove {
                    TrainerSecondaryActionButton(
                        title: text(trait.canExpire == true && trait.blessing != nil ? "hades.cancelCurse" : "hades.remove"),
                        systemImage: TrainerSemanticIcon.Action.remove,
                        enabled: model.canMutate
                    ) { model.removeTrait(trait) }
                }
                Spacer()
            }
        }
    }
}
