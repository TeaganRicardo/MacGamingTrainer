import SwiftUI

struct HadesGatheringPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var resource = "MetaPoints"
    @State private var amount = "100"
    @State private var capturedTarget: HadesHeroTarget?

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    /// The current-room observation explains why Generate is unavailable.
    private var fishingHelp: String {
        guard let world = model.world else { return text("hades.fishing.unavailable.scene") }
        return text(world.canFish ? "hades.fishingHelp" : "hades.fishing.unavailable.room")
    }

    private func gain() {
        guard let value = Double(amount), value.isFinite, value.rounded() == value,
              value >= 1, value <= 1_000_000 else { model.rejectInvalidValue(); return }
        model.gainResource(resource, amount: value, target: capturedTarget ?? model.target)
    }

    var body: some View {
        VStack(spacing: 0) {
            TrainerLabeledControlRow(title: text("hades.gainResource"), icon: TrainerSemanticIcon.Action.acquire, tint: theme.accent, emphasized: false, layout: .pickerAction) {
                Picker(text("hades.resources"), selection: $resource) {
                    Text(text("hades.money")).tag("Money")
                    ForEach(model.resourceCatalog) { row in
                        Text(row.name(language: localization.language.rawValue)).tag(row.id)
                    }
                }
                .labelsHidden().trainerPicker(.rowAction)
                TrainerNumberField(
                    text: $amount, accessibilityLabel: text("hades.gainAmount"), width: 72,
                    enabled: model.canMutate,
                    onEditingChanged: { editing in if editing { capturedTarget = model.target } },
                    onCommit: { $0.text }
                )
                TrainerSecondaryActionButton(title: text("hades.gain"), systemImage: TrainerSemanticIcon.Action.acquire, enabled: model.canMutate, action: gain)
            }
            TrainerLabeledControlRow(title: text("hades.generateFishing"), icon: TrainerSemanticIcon.Context.fishing, tint: theme.accent, emphasized: false) {
                TrainerShortcutBadgeSlot(text: model.shortcutText(.generateFishing))
                TrainerSecondaryActionButton(
                    title: text("hades.generate"), systemImage: TrainerSemanticIcon.Action.generate,
                    enabled: model.canMutate && model.world?.canFish == true,
                    helpText: fishingHelp,
                    accessibilityLabel: text("hades.generateFishing")
                ) { model.generateFishing() }
            }
        }
        .trainerGroupedRows()
    }
}

struct HadesRoomsPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var doorID = ""
    @State private var doorReward = "ZeusUpgrade"
    @State private var route = "combat"
    @State private var chamberObject = "trove"

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    private var doors: [HadesWorldDoor] { model.world?.doors ?? [] }
    private var door: HadesWorldDoor? { doors.first { $0.id == doorID } }
    private func termName(_ identifier: String) -> String {
        model.worldTerms[identifier]?[localization.language.rawValue]
            ?? model.worldTerms[identifier]?["en"] ?? text("hades.chamberObject")
    }
    private func rewardName(_ identifier: String) -> String {
        model.worldRewards.first { $0.id == identifier }?.name(language: localization.language)
            ?? text("hades.currentReward")
    }
    private func action(_ command: String, operation: String, params: [String: Any] = [:]) {
        model.worldAction(command, roomID: model.world?.roomId, params: params, operation: operation)
    }

    /// The world catalog assigns each reward its section; sections keep catalog order.
    private func rewardSections(_ group: HadesRewardGroup) -> [TrainerPickerSection<HadesWorldReward>] {
        var order: [String] = []
        var titles: [String: String] = [:]
        var buckets: [String: [HadesWorldReward]] = [:]
        for reward in model.rewards(in: group) {
            if buckets[reward.section] == nil {
                order.append(reward.section)
                titles[reward.section] = reward.sectionNames?[localization.language.rawValue]
                    ?? text("hades.rewardSection.\(reward.section)")
            }
            buckets[reward.section, default: []].append(reward)
        }
        return order.enumerated().map { index, section in
            TrainerPickerSection(id: index, title: titles[section] ?? "", items: buckets[section] ?? [])
        }
    }

    /// Hades II's Generate row: grouped picker, shortcut badge, then Generate.
    private func spawnRow(_ group: HadesRewardGroup, title key: String, icon: String) -> some View {
        TrainerGroupedOptionPicker(
            title: text(key),
            icon: icon,
            pickerLabel: text(key),
            selection: Binding(get: { model.selectedRewards[group] ?? "" },
                               set: { model.selectedRewards[group] = $0 }),
            sections: rewardSections(group),
            enabled: model.canSpawnReward,
            inline: true,
            emptyLabel: text("hades.spawn.noItems"),
            actionTitle: text("hades.generate"),
            shortcutText: model.shortcutText(group.shortcut),
            itemLabel: \.bilingualName,
            onAction: { _ = model.spawnReward($0, in: group) }
        )
    }

    var body: some View {
        TrainerSection(title: text(HadesWorkbenchSection.rooms.titleKey), icon: HadesWorkbenchSection.rooms.icon) {
            VStack(spacing: 0) {
                TrainerLabeledControlRow(title: text("hades.generateChaosGate"), icon: TrainerSemanticIcon.Context.portal, tint: theme.accent, emphasized: false) {
                    TrainerShortcutBadgeSlot(text: model.shortcutText(.generateChaosGate))
                    TrainerSecondaryActionButton(
                        title: text("hades.generate"), systemImage: TrainerSemanticIcon.Action.generate,
                        enabled: model.canMutate && model.world?.canChaos == true
                    ) { model.generateChaosGate() }
                }
                .help(text("hades.chaosGateHelp"))
                TrainerLabeledControlRow(title: text("hades.chamberObject"), icon: HadesWorkbenchIcon.chamberObject, tint: theme.accent, emphasized: false, layout: .pickerAction) {
                    Picker(text("hades.chamberObject"), selection: $chamberObject) {
                        ForEach(model.world?.objects ?? [], id: \.self) { item in Text(termName(item)).tag(item) }
                    }
                    .labelsHidden().trainerPicker(.rowAction, state: model.world?.objects.isEmpty == false ? .interactive : .unavailable)
                    TrainerSecondaryActionButton(title: text("hades.generate"), systemImage: TrainerSemanticIcon.Action.generate,
                                                 enabled: model.canMutate && model.world?.objects.isEmpty == false) {
                        guard model.world?.objects.contains(chamberObject) == true else { return }
                        action("generate_chamber_object", operation: "hades.chamberObject", params: ["object": chamberObject])
                    }
                }
            }
            .trainerGroupedRows()

            // As in Hades II, the Generate reward rows follow the Chaos Gate.
            VStack(spacing: 0) {
                spawnRow(.olympian, title: "hades.spawn.olympianBoons", icon: TrainerSemanticIcon.Section.effects)
                spawnRow(.pickup, title: "hades.spawn.pickupRewards", icon: TrainerSemanticIcon.Section.inventory)
                spawnRow(.special, title: "hades.spawn.characterRewards", icon: TrainerSemanticIcon.Context.characterReward)
            }
            .trainerGroupedRows()

            if doors.isEmpty {
                Text(text("hades.noReadyDoors")).font(.caption).foregroundStyle(.secondary)
            }
            VStack(spacing: 0) {
                TrainerLabeledControlRow(title: text("hades.exitDoor"), icon: TrainerSemanticIcon.Context.doorway, tint: theme.accent, emphasized: false, layout: .pickerAction) {
                    Picker(text("hades.exitDoor"), selection: $doorID) {
                        if doors.isEmpty { Text(text("hades.noReadyDoors")).tag("") }
                        ForEach(Array(doors.enumerated()), id: \.element.id) { index, row in
                            Text("\(index + 1) · \(rewardName(row.reward))").tag(row.id)
                        }
                    }
                    .labelsHidden().trainerPicker(.rowAction, state: doors.isEmpty ? .unavailable : .interactive)
                }
                TrainerLabeledControlRow(title: text("hades.doorReward"), icon: TrainerSemanticIcon.Context.reward, tint: theme.accent, emphasized: false, layout: .pickerAction) {
                    Picker(text("hades.reward"), selection: $doorReward) {
                        ForEach(model.worldRewards.filter(\.doorAllowed)) { row in
                            Text(row.name(language: localization.language)).tag(row.id)
                        }
                    }
                    .labelsHidden().trainerPicker(.rowAction, state: door?.canReward == true ? .interactive : .unavailable)
                    TrainerSecondaryActionButton(title: text("hades.apply"), systemImage: TrainerSemanticIcon.Action.apply,
                                                 enabled: model.canMutate && door?.canReward == true) {
                        guard let door, door.canReward else { return }
                        action("set_door_reward", operation: "hades.doorReward", params: ["doorId": door.id, "reward": doorReward])
                    }
                }
                TrainerLabeledControlRow(title: text("hades.doorRoute"), icon: HadesWorkbenchIcon.route, tint: theme.accent, emphasized: false, layout: .pickerAction) {
                    Picker(text("hades.doorRoute"), selection: $route) {
                        ForEach(door?.routes ?? [], id: \.self) { item in
                            Text(text("hades.route.\(item)")).tag(item)
                        }
                    }
                    .labelsHidden().trainerPicker(.rowAction, state: door?.routes.isEmpty == false ? .interactive : .unavailable)
                    TrainerSecondaryActionButton(title: text("hades.apply"), systemImage: TrainerSemanticIcon.Action.apply,
                                                 enabled: model.canMutate && door?.routes.isEmpty == false) {
                        guard let door, !door.routes.isEmpty else { return }
                        action("set_door_route", operation: "hades.doorRoute", params: ["doorId": door.id, "route": route])
                    }
                }
                if door?.pendingEncounter == true {
                    Text(text("hades.thanatosPending")).font(.caption).foregroundStyle(.secondary).padding(10)
                }
                TrainerLabeledControlRow(title: text("hades.restoreDoor"), icon: TrainerSemanticIcon.Action.restore, tint: theme.accent, emphasized: false) {
                    TrainerSecondaryActionButton(title: text("hades.restore"), systemImage: TrainerSemanticIcon.Action.restore,
                                                 enabled: model.canMutate && door?.canRestore == true) {
                        guard let door, door.canRestore else { return }
                        action("restore_door", operation: "hades.restoreDoor", params: ["doorId": door.id])
                    }
                }
            }
            .trainerGroupedRows()
            .help(text("hades.doorHelp"))
        }
        .onChange(of: doors, initial: true) { _, values in
            if !values.contains(where: { $0.id == doorID }) { doorID = values.first?.id ?? "" }
            if let door, !door.routes.contains(route) { route = door.routes.first ?? "combat" }
        }
        .onChange(of: model.world?.objects, initial: true) { _, values in
            if let values, !values.contains(chamberObject) { chamberObject = values.first ?? "trove" }
        }
        .onChange(of: doorID) { _, _ in
            if let door, !door.routes.contains(route) { route = door.routes.first ?? "combat" }
        }
    }
}
