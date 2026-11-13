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
    @State private var chamberObject = "trove"

    private func text(_ key: String) -> String { HadesPresentation.text(key, language: localization.language) }
    private var doors: [HadesWorldDoor] { model.world?.doors ?? [] }
    private func termName(_ identifier: String) -> String {
        model.worldTerms[identifier]?[localization.language.rawValue]
            ?? model.worldTerms[identifier]?["en"] ?? text("hades.chamberObject")
    }
    private func rewardName(_ identifier: String) -> String {
        model.worldRewards.first { $0.id == identifier }?.name(language: localization.language)
            ?? text("hades.currentReward")
    }
    private func worldTargetLabel(kind: String, id: String) -> String {
        if kind == "roomCategory" { return text("hades.route.\(id)") }
        return model.worldRewards.first { $0.id == id }?.name(language: localization.language) ?? id
    }
    private func worldExitLabel(_ door: HadesWorldDoor, index: Int) -> String {
        let current = door.reward.isEmpty
            ? (door.roomName ?? text("hades.worldActions.unknownTarget"))
            : rewardName(door.reward)
        return "\(index + 1) · \(current)"
    }
    private func occurrenceLabel(_ target: HadesWorldOccurrenceTarget) -> String {
        text("hades.occurrence.target.\(target.sourceId)")
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

    private var worldExitRow: some View {
        let exit = model.selectedWorldExit
        let rewardTargets = exit?.worldActionTargets.filter { $0.kind == "reward" } ?? []
        let routeTargets = exit?.worldActionTargets.filter { $0.kind == "roomCategory" } ?? []
        let leaseSelection = exit?.activeLease.map { $0.kind + ":" + $0.target }
        return TrainerDualPickerActionRow(
            title: text("hades.worldActions.modifyExit"),
            icon: TrainerSemanticIcon.Context.doorway,
            tint: model.canSelectWorldExit ? theme.accent : theme.inactive,
            emphasized: model.selectedWorldExitLease != nil
        ) {
            Picker(
                text("hades.worldActions.exit"),
                selection: Binding(
                    get: { model.selectedWorldExitToken },
                    set: {
                        model.selectedWorldExitToken = $0
                        model.repairWorldActionSelection()
                    }
                )
            ) {
                if doors.isEmpty {
                    Text(text("hades.worldActions.noExit")).tag("")
                }
                ForEach(Array(doors.enumerated()), id: \.element.id) { index, row in
                    Text(worldExitLabel(row, index: index)).tag(row.effectiveDoorToken)
                }
            }
            .labelsHidden()
            .trainerPicker(.layoutAllocated, state: model.canSelectWorldExit ? .interactive : .unavailable)
            .accessibilityIdentifier("hades.worldActions.currentExit")
        } secondPicker: {
            Picker(
                text("hades.worldActions.target"),
                selection: $model.selectedWorldExitTarget
            ) {
                if let lease = exit?.activeLease,
                   !((exit?.worldActionTargets ?? []).contains { $0.stableID == (leaseSelection ?? "") }) {
                    Text(worldTargetLabel(kind: lease.kind, id: lease.target))
                        .tag(lease.kind + ":" + lease.target)
                }
                if !rewardTargets.isEmpty {
                    Section(text("hades.worldActions.rewards")) {
                        ForEach(rewardTargets, id: \.stableID) { target in
                            Text(worldTargetLabel(kind: target.kind, id: target.id))
                                .tag(target.stableID)
                        }
                    }
                }
                if !routeTargets.isEmpty {
                    Section(text("hades.worldActions.routes")) {
                        ForEach(routeTargets, id: \.stableID) { target in
                            Text(worldTargetLabel(kind: target.kind, id: target.id))
                                .tag(target.stableID)
                        }
                    }
                }
                if exit != nil && rewardTargets.isEmpty && routeTargets.isEmpty && exit?.activeLease == nil {
                    Text(text("hades.worldActions.noTarget")).tag("")
                }
            }
            .labelsHidden()
            .trainerPicker(
                .layoutAllocated,
                state: model.canSelectWorldExit && !model.selectedWorldExitTargetLocked
                    && (!rewardTargets.isEmpty || !routeTargets.isEmpty)
                    ? .interactive : .unavailable
            )
            .accessibilityIdentifier("hades.worldActions.target")
        } shortcut: {
            EmptyView()
        } action: {
            TrainerSecondaryActionButton(
                title: text(model.selectedWorldExitLease != nil ? "hades.cancel" : "hades.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: model.selectedWorldExitActionAvailable,
                latched: model.selectedWorldExitLease != nil,
                subduedLatched: true,
                widthRole: .compactRow,
                helpText: text(model.selectedWorldExitLease != nil ? "hades.cancel" : "hades.apply")
            ) {
                _ = model.toggleSelectedWorldExit()
            }
            .accessibilityIdentifier("hades.worldActions.apply")
        }
    }

    private var worldOccurrenceRow: some View {
        let targets = model.worldOccurrenceTargets
        let characters = targets.filter { $0.kind == "character" }
        let shops = targets.filter { $0.kind == "shop" }
        let pending = model.worldOccurrenceLease != nil
        return TrainerLabeledControlRow(
            title: text("hades.occurrence.title"),
            icon: TrainerSemanticIcon.Context.characterReward,
            tint: model.canMutate && model.canAcceptRuntimeAction ? theme.accent : theme.inactive,
            emphasized: pending,
            layout: .pickerAction
        ) {
            Picker(text("hades.occurrence.title"), selection: $model.selectedWorldOccurrenceTarget) {
                if targets.isEmpty {
                    Text(text("hades.occurrence.noTarget")).tag("")
                }
                if !characters.isEmpty {
                    Section(text("hades.occurrence.characters")) {
                        ForEach(characters) { target in
                            Text(occurrenceLabel(target)).tag(target.id)
                        }
                    }
                }
                if !shops.isEmpty {
                    Section(text("hades.occurrence.shop")) {
                        ForEach(shops) { target in
                            Text(occurrenceLabel(target)).tag(target.id)
                        }
                    }
                }
            }
            .labelsHidden()
            .trainerPicker(
                .rowAction,
                state: model.canMutate && model.canAcceptRuntimeAction && !pending && !targets.isEmpty
                    ? .interactive : .unavailable
            )
            TrainerSecondaryActionButton(
                title: text(pending ? "hades.cancel" : "hades.apply"),
                systemImage: TrainerSemanticIcon.Action.apply,
                enabled: model.worldOccurrenceActionAvailable,
                latched: pending,
                subduedLatched: true,
                helpText: text(pending ? "hades.cancel" : "hades.apply")
            ) {
                _ = model.toggleWorldOccurrence()
            }
        }
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

            VStack(spacing: 0) {
                worldExitRow
                worldOccurrenceRow
            }
            .trainerGroupedRows()
        }
        .onChange(of: doors, initial: true) { _, _ in
            model.repairWorldActionSelection()
        }
        .onChange(of: model.world?.objects, initial: true) { _, values in
            if let values, !values.contains(chamberObject) { chamberObject = values.first ?? "trove" }
        }
    }
}
