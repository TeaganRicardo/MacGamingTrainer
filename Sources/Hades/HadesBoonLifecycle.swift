import SwiftUI

struct HadesEffectLifecycleControls: View {
    @ObservedObject var model: HadesTrainerModel
    let trait: HadesCurrentTrait
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var uses = HadesNumberDraft(value: 0)

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    private var canApplyUses: Bool {
        guard model.canMutate, trait.canSetUses == true,
              let remaining = trait.remainingUses,
              let value = Int(uses.text), (0...1000).contains(value) else { return false }
        return value != remaining
    }

    var body: some View {
        HStack(spacing: 6) {
            if let remaining = trait.remainingUses {
                Text(text("hades.remainingUses"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                TrainerNumberField(
                    text: Binding(get: { uses.text }, set: { uses.update($0) }),
                    accessibilityLabel: text("hades.remainingUses"),
                    width: 64,
                    enabled: model.canMutate && trait.canSetUses == true,
                    onEditingChanged: { active in
                        if active { uses.begin(target: model.target) } else { uses.end() }
                    },
                    onCommit: { completed in
                        guard completed.changed else { return completed.text }
                        guard let value = Int(completed.text), (0...1000).contains(value) else {
                            model.rejectInvalidValue()
                            return completed.rejected(message: text("hades.error.invalidValue"))
                        }
                        return String(value)
                    }
                )

                TrainerSecondaryActionButton(
                    title: text("hades.apply"),
                    systemImage: TrainerSemanticIcon.Action.apply,
                    enabled: canApplyUses,
                    widthRole: .compactRow
                ) {
                    guard let value = Int(uses.text), (0...1000).contains(value) else {
                        model.rejectInvalidValue()
                        return
                    }
                    model.setTraitUses(trait, uses: value, target: uses.target ?? model.target)
                }
                .onChange(of: remaining, initial: true) { _, value in
                    uses.observe(Double(value))
                }
            }

            if trait.canRefresh == true {
                TrainerSecondaryActionButton(
                    title: text("hades.refreshEffect"),
                    systemImage: TrainerSemanticIcon.Concept.refresh,
                    enabled: model.canMutate,
                    widthRole: .compactRow
                ) {
                    model.refreshTrait(trait)
                }
            }

            if trait.canExpire == true {
                TrainerSecondaryActionButton(
                    title: text(trait.blessing == nil ? "hades.expireEffect" : "hades.activateBlessing"),
                    systemImage: trait.blessing == nil ? "hourglass.bottomhalf.filled" : "bolt.fill",
                    enabled: model.canMutate && trait.canRemove,
                    widthRole: .compactRow
                ) {
                    model.expireTrait(trait)
                }
            }

            Spacer(minLength: 0)
        }
    }
}

