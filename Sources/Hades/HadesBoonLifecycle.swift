import SwiftUI

struct HadesChaosPairControls: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var blessingID = ""
    @State private var curseID = ""
    @State private var rarity = "Heroic"
    @State private var encounters = "3"

    private var blessings: [HadesCatalogEntry] { model.catalog.filter { $0.kind == "chaos" } }
    private var curses: [HadesCatalogEntry] { model.catalog.filter { $0.kind == "curse" } }
    private var blessing: HadesCatalogEntry? { blessings.first { $0.id == blessingID } }
    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    private func repairSelections() {
        if !blessings.contains(where: { $0.id == blessingID }) {
            blessingID = blessings.first?.id ?? ""
        }
        if !curses.contains(where: { $0.id == curseID }) {
            curseID = curses.first?.id ?? ""
        }
        let rarities = blessing?.rarities ?? []
        if !rarities.contains(rarity) {
            rarity = rarities.contains("Heroic") ? "Heroic" : rarities.first ?? "Common"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(text("hades.chaosPair"))
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.chaosBlessing")).font(.caption).foregroundStyle(.secondary)
                    Picker(text("hades.chaosBlessing"), selection: $blessingID) {
                        if blessings.isEmpty { Text(text("hades.emptyCatalog")).tag("") }
                        ForEach(blessings) { item in
                            Text(item.name(language: localization.language.rawValue)).tag(item.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.expanding, state: model.canMutate && !blessings.isEmpty ? .interactive : .unavailable)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text(text("hades.chaosCurse")).font(.caption).foregroundStyle(.secondary)
                    Picker(text("hades.chaosCurse"), selection: $curseID) {
                        if curses.isEmpty { Text(text("hades.emptyCatalog")).tag("") }
                        ForEach(curses) { item in
                            Text(item.name(language: localization.language.rawValue)).tag(item.id)
                        }
                    }
                    .labelsHidden()
                    .trainerPicker(.expanding, state: model.canMutate && !curses.isEmpty ? .interactive : .unavailable)
                }
                Picker(text("hades.rarity"), selection: $rarity) {
                    ForEach(blessing?.rarities ?? [], id: \.self) {
                        Text(text("hades.rarity.\($0)")).tag($0)
                    }
                }
                .labelsHidden()
                .trainerPicker(.compactValue, state: model.canMutate && blessing != nil ? .interactive : .unavailable)

                TrainerNumberField(
                    text: $encounters,
                    accessibilityLabel: text("hades.chaosEncounters"),
                    width: 58,
                    enabled: model.canMutate,
                    onCommit: { completion in
                        guard let count = Int(completion.text), (1...100).contains(count) else {
                            return completion.rejected(message: text("hades.error.invalidValue"))
                        }
                        return String(count)
                    }
                )

                TrainerSecondaryActionButton(
                    title: text("hades.acquire"),
                    systemImage: TrainerSemanticIcon.Action.acquire,
                    enabled: model.canMutate && blessing != nil && !curseID.isEmpty,
                    widthRole: .compactRow
                ) {
                    guard let blessing, let count = Int(encounters), (1...100).contains(count) else {
                        model.rejectInvalidValue()
                        return
                    }
                    model.addChaosPair(blessing: blessing, curse: curseID, rarity: rarity, encounters: count)
                }
            }
        }
        .onChange(of: blessings.map(\.id), initial: true) { _, _ in repairSelections() }
        .onChange(of: curses.map(\.id)) { _, _ in repairSelections() }
        .onChange(of: blessingID) { _, _ in repairSelections() }
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
