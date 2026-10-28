import SwiftUI

struct HadesGatheringPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var resource = "MetaPoints"
    @State private var amount = "100"
    @State private var capturedTarget: HadesHeroTarget?

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }

    private func gain() {
        guard let value = Double(amount), value.isFinite, value.rounded() == value,
              value >= 1, value <= 1_000_000 else { model.rejectInvalidValue(); return }
        model.gainResource(resource, amount: value, target: capturedTarget ?? model.target)
    }

    var body: some View {
        VStack(spacing: 0) {
            TrainerLabeledControlRow(title: text("hades.gainResource"), icon: TrainerSemanticIcon.Action.acquire, tint: theme.accent, emphasized: false) {
                Picker(text("hades.resources"), selection: $resource) {
                    Text(text("hades.money")).tag("Money")
                    ForEach(model.resourceCatalog) { row in
                        Text(row.name(language: localization.language.rawValue)).tag(row.id)
                    }
                }
                .labelsHidden().frame(maxWidth: 155)
                TrainerNumberField(
                    text: $amount, accessibilityLabel: text("hades.gainAmount"), width: 72,
                    enabled: model.canMutate,
                    onEditingChanged: { editing in if editing { capturedTarget = model.target } },
                    onCommit: { $0.text }
                )
                TrainerSecondaryActionButton(title: text("hades.gain"), enabled: model.canMutate, action: gain)
            }
            TrainerLabeledControlRow(title: text("hades.generateFishing"), icon: TrainerSemanticIcon.Context.fishing, tint: theme.accent, emphasized: false) {
                TrainerSecondaryActionButton(
                    title: text("hades.generate"), enabled: model.canMutate && model.world?.canFish == true,
                    action: model.generateFishing
                )
                TrainerShortcutBadgeSlot(text: model.shortcutText(.generateFishing))
            }
        }
        .trainerGroupedRows()
        .help(text("hades.fishingHelp"))
    }
}

struct HadesRoomsPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var reward = "ZeusUpgrade"
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

    var body: some View {
        TrainerSection(title: text(HadesWorkbenchSection.rooms.titleKey), icon: HadesWorkbenchSection.rooms.icon) {
            VStack(spacing: 0) {
                TrainerLabeledControlRow(title: text("hades.spawnReward"), icon: TrainerSemanticIcon.Context.reward, tint: theme.accent, emphasized: false) {
                    Picker(text("hades.reward"), selection: $reward) {
                        ForEach(model.worldRewards) { row in
                            Text(row.name(language: localization.language)).tag(row.id)
                        }
                    }
                    .labelsHidden().frame(maxWidth: 210)
                    TrainerSecondaryActionButton(title: text("hades.generate"), enabled: model.canMutate && model.world != nil) {
                        action("spawn_reward", operation: "hades.spawnReward", params: ["reward": reward])
                    }
                }
                TrainerLabeledControlRow(title: text("hades.generateChaosGate"), icon: TrainerSemanticIcon.Context.portal, tint: theme.accent, emphasized: false) {
                    TrainerSecondaryActionButton(
                        title: text("hades.generate"), enabled: model.canMutate && model.world?.canChaos == true,
                        action: model.generateChaosGate
                    )
                    TrainerShortcutBadgeSlot(text: model.shortcutText(.generateChaosGate))
                }
                .help(text("hades.chaosGateHelp"))
                if let objects = model.world?.objects, !objects.isEmpty {
                    TrainerLabeledControlRow(title: text("hades.chamberObject"), icon: "shippingbox", tint: theme.accent, emphasized: false) {
                        Picker(text("hades.chamberObject"), selection: $chamberObject) {
                            ForEach(objects, id: \.self) { item in Text(termName(item)).tag(item) }
                        }
                        .labelsHidden().frame(maxWidth: 210)
                        TrainerSecondaryActionButton(title: text("hades.generate"), enabled: model.canMutate) {
                            action("generate_chamber_object", operation: "hades.chamberObject", params: ["object": chamberObject])
                        }
                    }
                }
            }
            .trainerGroupedRows()

            if doors.isEmpty {
                Text(text("hades.noReadyDoors")).font(.caption).foregroundStyle(.secondary)
            } else {
                VStack(spacing: 0) {
                    TrainerLabeledControlRow(title: text("hades.exitDoor"), icon: TrainerSemanticIcon.Context.doorway, tint: theme.accent, emphasized: false) {
                        Picker(text("hades.exitDoor"), selection: $doorID) {
                            ForEach(Array(doors.enumerated()), id: \.element.id) { index, row in
                                Text("\(index + 1) · \(rewardName(row.reward))").tag(row.id)
                            }
                        }
                        .labelsHidden().frame(maxWidth: 250)
                    }
                    if let door {
                        if door.canReward {
                            TrainerLabeledControlRow(title: text("hades.doorReward"), icon: TrainerSemanticIcon.Context.reward, tint: theme.accent, emphasized: false) {
                                Picker(text("hades.reward"), selection: $doorReward) {
                                    ForEach(model.worldRewards.filter(\.doorAllowed)) { row in
                                        Text(row.name(language: localization.language)).tag(row.id)
                                    }
                                }
                                .labelsHidden().frame(maxWidth: 210)
                                TrainerSecondaryActionButton(title: text("hades.apply"), enabled: model.canMutate) {
                                    action("set_door_reward", operation: "hades.doorReward", params: ["doorId": door.id, "reward": doorReward])
                                }
                            }
                        }
                        if !door.routes.isEmpty {
                            TrainerLabeledControlRow(title: text("hades.doorRoute"), icon: "arrow.triangle.branch", tint: theme.accent, emphasized: false) {
                                Picker(text("hades.doorRoute"), selection: $route) {
                                    ForEach(door.routes, id: \.self) { item in
                                        Text(text("hades.route.\(item)")).tag(item)
                                    }
                                }
                                .labelsHidden().frame(maxWidth: 210)
                                TrainerSecondaryActionButton(title: text("hades.apply"), enabled: model.canMutate) {
                                    action("set_door_route", operation: "hades.doorRoute", params: ["doorId": door.id, "route": route])
                                }
                            }
                        }
                        if door.pendingEncounter {
                            Text(text("hades.thanatosPending")).font(.caption).foregroundStyle(.secondary).padding(10)
                        }
                        if door.canRestore {
                            TrainerLabeledControlRow(title: text("hades.restoreDoor"), icon: TrainerSemanticIcon.Action.restore, tint: theme.accent, emphasized: false) {
                                TrainerSecondaryActionButton(title: text("hades.restore"), enabled: model.canMutate) {
                                    action("restore_door", operation: "hades.restoreDoor", params: ["doorId": door.id])
                                }
                            }
                        }
                    }
                }
                .trainerGroupedRows()
                .help(text("hades.doorHelp"))
            }
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
