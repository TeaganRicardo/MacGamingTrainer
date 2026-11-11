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
    @State private var doorTarget = ""
    @State private var occurrenceTarget = ""
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
    private func routeName(_ identifier: String) -> String {
        switch identifier {
        case "combat": text("hades.route.combat")
        case "story": text("hades.route.story")
        case "shop": text("hades.route.shop")
        case "reprieve": text("hades.route.reprieve")
        case "miniboss": text("hades.route.miniboss")
        default: identifier
        }
    }
    private func worldTargetName(_ target: HadesWorldActionTarget) -> String {
        target.kind == "reward" ? rewardName(target.id) : routeName(target.id)
    }
    private func occurrenceName(_ identifier: String) -> String {
        switch identifier {
        case "sisyphus": text("hades.worldActions.occurrence.sisyphus")
        case "eurydice": text("hades.worldActions.occurrence.eurydice")
        case "patroclus": text("hades.worldActions.occurrence.patroclus")
        case "thanatos": text("hades.worldActions.occurrence.thanatos")
        case "charon": text("hades.worldActions.occurrence.charon")
        default: identifier
        }
    }
    private func repairDoorTarget() {
        guard let door else { doorTarget = ""; return }
        if let lease = door.activeLease {
            doorTarget = lease.kind + ":" + lease.target
        } else if !door.targets.contains(where: { $0.stableID == doorTarget }) {
            doorTarget = door.targets.first?.stableID ?? ""
        }
    }
    private func repairOccurrenceTarget() {
        let targets = model.world?.occurrenceTargets ?? []
        if let active = model.world?.occurrence {
            occurrenceTarget = active.target
        } else if !targets.contains(occurrenceTarget) {
            occurrenceTarget = targets.first ?? ""
        }
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
                worldExitRow
                worldOccurrenceRow
            }
            .trainerGroupedRows()
            .help(text("hades.doorHelp"))
        }
        .onChange(of: doors, initial: true) { _, values in
            if !values.contains(where: { $0.id == doorID }) { doorID = values.first?.id ?? "" }
            repairDoorTarget()
        }
        .onChange(of: model.world?.objects, initial: true) { _, values in
            if let values, !values.contains(chamberObject) { chamberObject = values.first ?? "trove" }
        }
        .onChange(of: doorID) { _, _ in repairDoorTarget() }
        .onChange(of: model.world?.occurrenceTargets, initial: true) { _, _ in repairOccurrenceTarget() }
        .onChange(of: model.world?.occurrence) { _, _ in repairOccurrenceTarget() }
    }

    private var worldExitRow: some View {
        let selectedDoor = door
        let rewards = selectedDoor?.targets.filter { $0.kind == "reward" } ?? []
        let routes = selectedDoor?.targets.filter { $0.kind == "roomCategory" } ?? []
        let activeSelection = selectedDoor?.activeLease.map { $0.kind + ":" + $0.target }
        let selectedTarget = selectedDoor?.targets.first { $0.stableID == doorTarget }
        let canAct = model.canMutate && selectedDoor != nil
            && (selectedDoor?.activeLease != nil || selectedTarget != nil)
        return TrainerLabeledControlRow(
            title: text("hades.worldActions.modifyExit"),
            icon: TrainerSemanticIcon.Context.doorway,
            tint: model.canMutate && !doors.isEmpty ? theme.accent : theme.inactive,
            emphasized: selectedDoor?.activeLease != nil,
            layout: .pickerAction
        ) {
            HStack(spacing: 8) {
                Picker(text("hades.exitDoor"), selection: $doorID) {
                    if doors.isEmpty { Text(text("hades.noReadyDoors")).tag("") }
                    ForEach(Array(doors.enumerated()), id: \.element.id) { index, row in
                        Text("\(index + 1) · \(rewardName(row.reward))").tag(row.id)
                    }
                }
                .labelsHidden()
                .trainerPicker(.expanding, state: doors.isEmpty ? .unavailable : .interactive)

                Picker(text("hades.worldActions.target"), selection: $doorTarget) {
                    if let lease = selectedDoor?.activeLease,
                       !((selectedDoor?.targets ?? []).contains { $0.stableID == (activeSelection ?? "") }) {
                        Text(worldTargetName(.init(kind: lease.kind, id: lease.target)))
                            .tag(lease.kind + ":" + lease.target)
                    }
                    if !rewards.isEmpty {
                        Section(text("hades.worldActions.rewards")) {
                            ForEach(rewards, id: \.stableID) { target in
                                Text(worldTargetName(target)).tag(target.stableID)
                            }
                        }
                    }
                    if !routes.isEmpty {
                        Section(text("hades.worldActions.routes")) {
                            ForEach(routes, id: \.stableID) { target in
                                Text(worldTargetName(target)).tag(target.stableID)
                            }
                        }
                    }
                    if selectedDoor != nil && rewards.isEmpty && routes.isEmpty
                        && selectedDoor?.activeLease == nil {
                        Text(text("hades.worldActions.noTarget")).tag("")
                    }
                }
                .labelsHidden()
                .trainerPicker(
                    .expanding,
                    state: model.canMutate && selectedDoor?.activeLease == nil
                        && (!rewards.isEmpty || !routes.isEmpty) ? .interactive : .unavailable
                )
            }

            TrainerSecondaryActionButton(
                title: text("hades.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: canAct,
                latched: selectedDoor?.activeLease != nil
            ) {
                guard let selectedDoor else { return }
                _ = model.toggleWorldExit(door: selectedDoor, target: selectedTarget)
            }
        }
    }

    private var worldOccurrenceRow: some View {
        let targets = model.world?.occurrenceTargets ?? []
        let active = model.world?.occurrence
        let canAct = model.canMutate && (active != nil || targets.contains(occurrenceTarget))
        return TrainerLabeledControlRow(
            title: text("hades.worldActions.specifyOccurrence"),
            icon: HadesWorkbenchIcon.route,
            tint: model.canMutate ? theme.accent : theme.inactive,
            emphasized: active != nil,
            layout: .pickerAction
        ) {
            Picker(text("hades.worldActions.specifyOccurrence"), selection: $occurrenceTarget) {
                if targets.isEmpty { Text(text("hades.worldActions.noOccurrence")).tag("") }
                ForEach(targets, id: \.self) { target in
                    Text(occurrenceName(target)).tag(target)
                }
            }
            .labelsHidden()
            .trainerPicker(
                .rowAction,
                state: model.canMutate && active == nil && !targets.isEmpty
                    ? .interactive : .unavailable
            )
            TrainerSecondaryActionButton(
                title: text("hades.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: canAct,
                latched: model.world?.occurrence != nil
            ) {
                _ = model.toggleWorldOccurrence(target: occurrenceTarget)
            }
        }
    }
}
