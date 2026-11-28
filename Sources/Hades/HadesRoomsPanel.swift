import SwiftUI
import TrainerCore

private struct HadesOccurrenceSetting: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var input: String
    let hasOverride: Bool
    let enabled: Bool
    let probabilityLabel: String
    let nativeLabel: String
    let resetLabel: String
    let probabilityHelp: String
    let onEditingChanged: (Bool) -> Void
    let onCommit: (TrainerTextField.Completion) -> String
    let onReset: () -> Void
    let generateLabel: String
    let generateShortcutText: String?
    let generateHelp: String
    let canGenerate: Bool
    var generateAccessibilityLabel: String? = nil
    let onGenerate: () -> Void

    var body: some View {
        TrainerLabeledControlRow(
            title: title,
            icon: icon,
            tint: hasOverride ? theme.accent : theme.inactive,
            emphasized: hasOverride,
            helpText: probabilityHelp
        ) {
            TrainerNumberField(
                text: $input,
                placeholder: nativeLabel,
                accessibilityLabel: title + " " + probabilityLabel,
                width: theme.occurrenceFieldWidth,
                enabled: enabled,
                onEditingChanged: onEditingChanged,
                onCommit: onCommit
            )
            .help(probabilityHelp)
            Text(input.isEmpty ? "" : "%")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(width: 14)
            if hasOverride {
                TrainerResetButton(title: resetLabel, enabled: enabled, action: onReset)
            } else {
                TrainerLockSlot()
            }
            TrainerShortcutBadgeSlot(text: generateShortcutText)
            TrainerSecondaryActionButton(
                title: generateLabel,
                enabled: canGenerate,
                helpText: generateHelp,
                accessibilityLabel: generateAccessibilityLabel ?? (title + " " + generateLabel),
                action: onGenerate
            )
        }
    }
}

struct HadesGatheringPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var resource = "MetaPoints"
    @State private var amount = "100"
    @State private var capturedTarget: HadesHeroTarget?
    @State private var fishingInput = ""
    @State private var fishingEditing = false

    private func text(_ key: String) -> String { localization.string(key) }

    /// The current-room observation explains why Generate is unavailable.
    private var fishingHelp: String {
        guard let world = model.world else { return text("hades.fishing.unavailable.scene") }
        if world.canFish { return text("hades.fishingHelp") }
        let known: Set<String> = ["scene", "native", "existing", "placement", "rod", "spacing", "progression"]
        if let reason = world.fishingReason, known.contains(reason) {
            return text("hades.fishing.unavailable.\(reason)")
        }
        return text("hades.fishing.unavailable.room")
    }

    private func gain() {
        guard let value = Double(amount), value.isFinite, value.rounded() == value,
              value >= 1, value <= 1_000_000 else { model.rejectInvalidValue(); return }
        model.gainResource(resource, amount: value, target: capturedTarget ?? model.target)
    }

    var body: some View {
        VStack(spacing: 1) {
            TrainerLabeledControlRow(title: text("hades.gainResource"), icon: TrainerSemanticIcon.Action.acquire, tint: model.canMutate ? theme.accent : theme.inactive, emphasized: false, layout: .pickerAction) {
                Picker(text("hades.resources"), selection: $resource) {
                    Text(text("hades.money")).tag("Money")
                    ForEach(model.resourceCatalog) { row in
                        Text(row.name(language: localization.language.rawValue)).tag(row.id)
                    }
                }
                .labelsHidden().trainerPicker(.rowAction, state: model.canMutate ? .interactive : .unavailable)
                TrainerNumberField(
                    text: $amount, accessibilityLabel: text("hades.gainAmount"), width: 72,
                    enabled: model.canMutate,
                    onEditingChanged: { editing in if editing { capturedTarget = model.target } },
                    onCommit: { $0.text }
                )
                TrainerSecondaryActionButton(title: text("hades.gain"), enabled: model.canMutate, action: gain)
            }
            HadesOccurrenceSetting(
                title: text("hades.fishing.title"),
                icon: HadesWorkbenchIcon.fishing,
                input: $fishingInput,
                hasOverride: model.fishingChance != nil,
                enabled: model.canEditIntent,
                probabilityLabel: text("hades.fishing.probability"),
                nativeLabel: text("hades.occurrence.native"),
                resetLabel: text("hades.occurrence.resetToNative"),
                probabilityHelp: text("hades.fishing.probabilityHelp"),
                onEditingChanged: { fishingEditing = $0 },
                onCommit: { completion in
                    model.completeTextEdit(
                        .fishingChance,
                        text: completion.text,
                        changed: completion.changed,
                        target: nil
                    ) { key in
                        _ = completion.rejected(message: text(key))
                    }
                },
                onReset: {
                    fishingEditing = false
                    model.setFishingChance(nil)
                },
                generateLabel: text("hades.generate"),
                generateShortcutText: model.shortcutText(.generateFishing),
                generateHelp: fishingHelp,
                canGenerate: model.canMutate && model.canAcceptRuntimeAction && model.world?.canFish == true,
                generateAccessibilityLabel: text("hades.generateFishing"),
                onGenerate: { _ = model.generateFishing() }
            )
            .onChange(of: model.fishingChance, initial: true) { _, value in
                if !fishingEditing {
                    fishingInput = value.map(HadesTrainerModel.displayText) ?? ""
                }
            }
            .onChange(of: model.busy) { _, busy in
                if !busy && !fishingEditing {
                    fishingInput = model.fishingChance.map(HadesTrainerModel.displayText) ?? ""
                }
            }
        }
        .trainerGroupedRows()
    }
}

struct HadesRoomsPanel: View {
    @ObservedObject var model: HadesTrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @State private var chaosGateInput = ""
    @State private var chaosGateEditing = false

    private static let worldActionGodIDs: Set<String> = [
        "ZeusUpgrade", "PoseidonUpgrade", "AthenaUpgrade", "AphroditeUpgrade", "AresUpgrade",
        "ArtemisUpgrade", "DionysusUpgrade", "DemeterUpgrade", "HermesUpgrade",
    ]

    private static let worldActionReasonIDs: Set<String> = [
        "biome_depth_too_high",
        "biome_depth_too_low",
        "door_forced_destination",
        "door_forced_room_set",
        "door_returns_to_previous_room",
        "game_state_requirements",
        "global_forced_destination",
        "god_eligibility_requires_rng",
        "god_eligibility_unavailable",
        "god_limit",
        "god_not_eligible",
        "max_appearances_this_biome",
        "max_creations_this_run",
        "native_forced_room_present",
        "native_ineligible",
        "no_room_route",
        "reward_eligibility_probe_error",
        "reward_eligibility_requires_rng",
        "reward_eligibility_unavailable",
        "reward_not_available",
        "reward_not_eligible",
        "reward_not_in_current_store",
        "reward_store_name_missing",
        "reward_store_unavailable",
        "room_eligibility_probe_error",
        "room_eligibility_requires_rng",
        "room_eligibility_unavailable",
        "room_excluded_by_exit_rules",
        "room_has_fixed_reward_category",
        "room_has_forced_reward",
        "room_linked_route_required",
        "room_max_appearances_this_run",
        "room_miniboss_wing_required",
        "room_no_reward",
        "room_reward_deferred",
        "room_same_as_source",
        "room_starting_not_allowed",
        "room_wrong_wing_end",
        "source_forced_room_set",
        "source_linked_destination",
        "source_next_room_set",
        "source_persistent_door_rooms",
        "source_uses_previous_room_set",
    ]

    private func text(_ key: String) -> String { localization.string(key) }
    private var doors: [HadesWorldDoor] { model.world?.doors ?? [] }
    private func termName(_ identifier: String) -> String {
        model.worldTerms[identifier]?[localization.language.rawValue]
            ?? model.worldTerms[identifier]?["en"] ?? text("hades.chamberObject")
    }
    private func worldActionReason(_ id: String?) -> String? {
        guard let id, !id.isEmpty else { return nil }
        let known = Self.worldActionReasonIDs.contains(id) ? id : "native_ineligible"
        let key = "hades.worldActions.unavailable.\(known)"
        let localized = text(key)
        return localized == key ? text("hades.worldActions.unavailable.native_ineligible") : localized
    }
    private func worldActionRoomLabel(_ id: String) -> String {
        if id == "current" { return text("hades.worldActions.currentRoom") }
        switch id {
        case "combat", "miniboss", "story", "shop", "reprieve":
            return text("hades.worldActions.route.\(id)")
        default:
            return id
        }
    }
    private func worldActionRewardLabel(_ id: String) -> String {
        if let reward = model.worldRewards.first(where: { $0.id == id }) {
            return reward.name(language: localization.language)
        }
        if id.hasSuffix("RunProgress") {
            let baseID = String(id.dropLast("RunProgress".count))
            if let reward = model.worldRewards.first(where: { $0.id == baseID }) {
                return reward.name(language: localization.language)
            }
        }
        switch id {
        case "Story": return text("hades.worldActions.route.story")
        case "Shop": return text("hades.worldActions.route.shop")
        default: return id
        }
    }
    private func worldActionPopupLabel(_ label: String, enabled: Bool = true,
                                       reason: String? = nil, warning: String? = nil) -> TrainerPopupLabel {
        if !enabled {
            let reasonText = worldActionReason(reason ?? "native_ineligible") ?? ""
            return TrainerPopupLabel(primary: label, mutedSuffixes: reasonText.isEmpty ? [] : [" · \(reasonText)"])
        }
        guard let warningText = worldActionReason(warning) else { return TrainerPopupLabel(primary: label) }
        return TrainerPopupLabel(primary: label, mutedSuffixes: [" · ⚠︎ \(warningText)"])
    }
    /// `Exit 1 · Combat · Zeus`: what the door holds now, as the game reports it.
    private func worldExitLabel(_ door: HadesWorldDoor, index: Int) -> String {
        var parts = [localization.string("hades.worldActions.exitNumber", arguments: [String(index + 1)])]
        if !door.effectiveRoomKind.isEmpty {
            parts.append(worldActionRoomLabel(door.effectiveRoomKind))
        } else {
            parts.append(
                door.roomName?.isEmpty == false
                    ? worldActionRoomLabel(door.roomName!)
                    : text("hades.worldActions.unknownTarget")
            )
        }
        if door.reward.isEmpty {
            parts.append(text("hades.worldActions.noReward"))
        } else if door.reward != "Empty",
                  !(door.reward == "Story" && door.effectiveRoomKind == "story"),
                  !(door.reward == "Shop" && door.effectiveRoomKind == "shop") {
            parts.append(worldActionRewardLabel(door.reward))
        }
        return parts.joined(separator: " · ")
    }
    private func worldExitChoiceLabel(_ choice: HadesWorldExitChoice, in exit: HadesWorldDoor) -> TrainerPopupLabel {
        let room = worldActionRoomLabel(choice.room)
        let label: String
        if let reward = choice.reward {
            label = "\(room) · \(worldActionRewardLabel(reward))"
        } else {
            let acceptsReward = exit.roomTargets.first { $0.id == choice.room }?.acceptsReward ?? false
            label = acceptsReward ? "\(room) · \(text("hades.worldActions.anyReward"))" : room
        }
        return worldExitChoiceItemLabel(label, choice: choice, in: exit)
    }
    private func worldExitChoiceItemLabel(_ label: String, choice: HadesWorldExitChoice,
                                          in exit: HadesWorldDoor, enabled: Bool = true,
                                          reason: String? = nil) -> TrainerPopupLabel {
        guard enabled else { return worldActionPopupLabel(label, enabled: false, reason: reason) }
        let room = exit.roomTargets.first { $0.id == choice.room }
        let reward = exit.rewardTargets.first { $0.id == choice.reward }
        let warnings = [choice.reward != nil && exit.isCurrentRoom(choice.room)
            ? exit.rewardWarning : room?.warning, reward?.warning]
        var seen = Set<String>()
        let suffixes = warnings
            .compactMap { $0 }
            .filter { seen.insert($0).inserted }
            .compactMap { worldActionReason($0).map { " · ⚠︎ \($0)" } }
        return TrainerPopupLabel(primary: label, mutedSuffixes: suffixes)
    }
    private func worldExitRewardEntries(_ exit: HadesWorldDoor, room: HadesWorldActionTarget) -> [TrainerPopupMenuEntry] {
        let rewardRank = Dictionary(uniqueKeysWithValues: model.worldRewards.enumerated().map { ($1.id, $0) })
        let orderedRewards = exit.rewardTargets.sorted {
            (rewardRank[$0.id] ?? Int.max) < (rewardRank[$1.id] ?? Int.max)
        }
        let gods = orderedRewards.filter { Self.worldActionGodIDs.contains($0.id) }
        let others = orderedRewards.filter { !Self.worldActionGodIDs.contains($0.id) }
        var entries: [TrainerPopupMenuEntry] = []
        if exit.offersAnyReward(room) {
            let choice = HadesWorldExitChoice(room: room.id)
            entries.append(.item(
                id: choice.id,
                label: worldExitChoiceItemLabel(text("hades.worldActions.anyReward"), choice: choice, in: exit),
                enabled: true,
                selected: model.selectedWorldExitTarget == choice.id
            ))
        }
        if !gods.isEmpty {
            entries.append(.sectionHeader(text("hades.worldActions.gods")))
            for reward in gods {
                let choice = HadesWorldExitChoice(room: room.id, reward: reward.id)
                entries.append(.item(
                    id: choice.id,
                    label: worldExitChoiceItemLabel(worldActionRewardLabel(reward.id), choice: choice, in: exit,
                        enabled: reward.enabled, reason: reward.reason),
                    enabled: reward.enabled,
                    selected: model.selectedWorldExitTarget == choice.id
                ))
            }
        }
        if !others.isEmpty {
            entries.append(.sectionHeader(text("hades.worldActions.rewards")))
            for reward in others {
                let choice = HadesWorldExitChoice(room: room.id, reward: reward.id)
                entries.append(.item(
                    id: choice.id,
                    label: worldExitChoiceItemLabel(worldActionRewardLabel(reward.id), choice: choice, in: exit,
                        enabled: reward.enabled, reason: reward.reason),
                    enabled: reward.enabled,
                    selected: model.selectedWorldExitTarget == choice.id
                ))
            }
        }
        return entries
    }
    private func worldExitTargetMenu(_ exit: HadesWorldDoor?) -> some View {
        let title: TrainerPopupLabel
        if let exit, let lease = exit.activeLease {
            title = worldExitChoiceLabel(lease.choice, in: exit)
        } else if let exit, let choice = model.selectedWorldExitChoice, exit.isEnabled(choice) {
            title = worldExitChoiceLabel(choice, in: exit)
        } else {
            title = TrainerPopupLabel(primary: text("hades.worldActions.noTarget"))
        }
        let entries: [TrainerPopupMenuEntry]
        if let exit {
            entries = exit.roomTargets.map { room in
                if room.acceptsReward {
                    return .submenu(
                        label: worldActionPopupLabel(worldActionRoomLabel(room.id), enabled: room.enabled,
                            reason: room.reason),
                        enabled: room.enabled,
                        entries: worldExitRewardEntries(exit, room: room)
                    )
                }
                let choice = HadesWorldExitChoice(room: room.id)
                return .item(
                    id: choice.id,
                    label: worldExitChoiceItemLabel(worldActionRoomLabel(room.id), choice: choice, in: exit,
                        enabled: room.enabled, reason: room.reason),
                    enabled: room.enabled,
                    selected: model.selectedWorldExitTarget == choice.id
                )
            }
        } else {
            entries = []
        }
        return TrainerNestedPopupButton(
            title: title,
            entries: entries,
            accessibilityLabel: text("hades.worldActions.target"),
            accessibilityIdentifier: "hades.worldActions.target"
        ) { selectedID in
            model.selectedWorldExitTarget = selectedID
        }
    }
    private func occurrenceLabel(_ target: HadesWorldOccurrenceTarget) -> String {
        text("hades.occurrence.target.\(target.sourceId)")
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
            itemLabel: { $0.label(for: localization.language) },
            onAction: { _ = model.spawnReward($0, in: group) }
        )
    }

    private var worldExitRow: some View {
        let exit = model.selectedWorldExit
        return TrainerDualPickerActionRow(
            title: text("hades.worldActions.modifyExit"),
            icon: HadesWorkbenchIcon.doorway,
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
            worldExitTargetMenu(exit)
                .trainerPicker(
                    .layoutAllocated,
                    state: model.canSelectWorldExitTarget ? .interactive : .unavailable
                )
        } shortcut: {
            TrainerShortcutBadgeSlot(text: model.shortcutText(.applyWorldExit))
        } action: {
            TrainerSecondaryActionButton(
                title: text(model.selectedWorldExitLease != nil ? "hades.cancel" : "hades.apply"),
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
            icon: HadesWorkbenchIcon.characterReward,
            tint: model.canSelectWorldOccurrence ? theme.accent : theme.inactive,
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
                state: model.canSelectWorldOccurrence && !pending && !targets.isEmpty
                    ? .interactive : .unavailable
            )
            TrainerShortcutBadgeSlot(text: model.shortcutText(.applyWorldOccurrence))
            TrainerSecondaryActionButton(
                title: text(pending ? "hades.cancel" : "hades.apply"),
                enabled: model.worldOccurrenceActionAvailable,
                latched: pending,
                subduedLatched: true,
                helpText: text(pending ? "hades.cancel" : "hades.apply")
            ) {
                _ = model.toggleWorldOccurrence()
            }
        }
    }

    private var chamberObjectRow: some View {
        let objects = model.world?.objects ?? []
        let selection = Binding<String>(
            get: { objects.contains(model.selectedChamberObject) ? model.selectedChamberObject : "" },
            set: { if !$0.isEmpty { model.selectedChamberObject = $0 } }
        )
        return TrainerLabeledControlRow(
            title: text("hades.chamberObject"),
            icon: HadesWorkbenchIcon.chamberObject,
            tint: model.canSelectChamberObject ? theme.accent : theme.inactive,
            emphasized: false,
            layout: .pickerAction
        ) {
            Picker(text("hades.chamberObject"), selection: selection) {
                if objects.isEmpty {
                    Text(text("hades.chamberObject.empty")).tag("")
                }
                ForEach(objects, id: \.self) { item in Text(termName(item)).tag(item) }
            }
            .labelsHidden()
            .trainerPicker(.rowAction, state: model.canSelectChamberObject ? .interactive : .unavailable)
            .accessibilityIdentifier("hades.chamberObject.selection")
            TrainerShortcutBadgeSlot(text: model.shortcutText(.generateChamberObject))
            TrainerSecondaryActionButton(
                title: text("hades.generate"),
                enabled: model.chamberObjectActionAvailable,
                helpText: text("hades.chamberObject.help"),
                accessibilityLabel: text("hades.chamberObject")
            ) {
                _ = model.generateSelectedChamberObject()
            }
        }
    }

    private var chaosGateHelp: String {
        guard let world = model.world else { return text("hades.chaosGate.unavailable.scene") }
        if world.canChaos { return text("hades.chaosGateHelp") }
        let known: Set<String> = [
            "scene", "native", "existing", "route", "placement", "occupied", "room", "spacing", "progression",
        ]
        if let reason = world.chaosReason, known.contains(reason) {
            return text("hades.chaosGate.unavailable.\(reason)")
        }
        return text("hades.chaosGate.unavailable.progression")
    }

    private var chaosGateRow: some View {
        HadesOccurrenceSetting(
            title: text("hades.chaosGate.title"),
            icon: HadesWorkbenchIcon.portal,
            input: $chaosGateInput,
            hasOverride: model.chaosGateChance != nil,
            enabled: model.canEditIntent,
            probabilityLabel: text("hades.chaosGate.probability"),
            nativeLabel: text("hades.occurrence.native"),
            resetLabel: text("hades.occurrence.resetToNative"),
            probabilityHelp: text("hades.chaosGate.probabilityHelp"),
            onEditingChanged: { chaosGateEditing = $0 },
            onCommit: { completion in
                model.completeTextEdit(
                    .chaosGateChance,
                    text: completion.text,
                    changed: completion.changed,
                    target: nil
                ) { key in
                    _ = completion.rejected(message: text(key))
                }
            },
            onReset: {
                chaosGateEditing = false
                model.setChaosGateChance(nil)
            },
            generateLabel: text("hades.generate"),
            generateShortcutText: model.shortcutText(.generateChaosGate),
            generateHelp: chaosGateHelp,
            canGenerate: model.canMutate && model.canAcceptRuntimeAction && model.world?.canChaos == true,
            generateAccessibilityLabel: text("hades.generateChaosGate"),
            onGenerate: { _ = model.generateChaosGate() }
        )
        .onChange(of: model.chaosGateChance, initial: true) { _, value in
            if !chaosGateEditing {
                chaosGateInput = value.map(HadesTrainerModel.displayText) ?? ""
            }
        }
        .onChange(of: model.busy) { _, busy in
            if !busy && !chaosGateEditing {
                chaosGateInput = model.chaosGateChance.map(HadesTrainerModel.displayText) ?? ""
            }
        }
    }

    var body: some View {
        TrainerSection(title: text(HadesWorkbenchSection.rooms.titleKey), icon: HadesWorkbenchSection.rooms.icon) {
            worldExitRow
                .trainerGroupedRows()

            worldOccurrenceRow
                .trainerGroupedRows()

            chamberObjectRow
                .trainerGroupedRows()

            chaosGateRow
                .trainerGroupedRows()

            VStack(spacing: 1) {
                spawnRow(.olympian, title: "hades.spawn.olympianBoons", icon: TrainerSemanticIcon.Section.effects)
                spawnRow(.pickup, title: "hades.spawn.pickupRewards", icon: TrainerSemanticIcon.Section.inventory)
                spawnRow(.special, title: "hades.spawn.characterRewards", icon: HadesWorkbenchIcon.characterReward)
            }
            .trainerGroupedRows()
        }
        .onChange(of: doors, initial: true) { _, _ in
            model.repairWorldActionSelection()
        }
    }
}
