import Combine
import Foundation
import AppKit
import SwiftUI
import TrainerCore

final class HadesTrainerModel: ObservableObject, TrainerHostModel {
    @Published private(set) var connected = false
    @Published private(set) var heroReady = false
    @Published private(set) var invincible = false
    /// Hero and save values are observations of a ready hero; nil means none.
    @Published private(set) var health: Double?
    @Published private(set) var maxHealth: Double?
    @Published private(set) var money: Double?
    @Published private(set) var rerolls: Double?
    @Published private(set) var healthLocked = false
    @Published private(set) var moneyLocked = false
    @Published private(set) var rerollsLocked = false
    @Published private(set) var godGauge: Double?
    @Published private(set) var maxGodGauge: Double?
    @Published private(set) var features: [String: HadesFeatureValue] = [:]
    @Published private(set) var activeFeatures: [String: Bool] = [:]
    @Published private(set) var dormantFeatures: [String: Bool] = [:]
    /// Optimistic toggle intent while its request is in flight. The reply's
    /// observation replaces it; a newer intent is never rolled back by an older reply.
    @Published private var pendingFeatureIntents: [HadesFeature: PendingFeatureIntent] = [:]
    @Published private(set) var boonRarityTarget = "Heroic"
    @Published private(set) var resources: [String: Double] = [:]
    @Published private(set) var traits: [HadesCurrentTrait] = []
    @Published private(set) var world: HadesWorldObservation?
    @Published var selectedWorldExitToken = ""
    @Published var selectedWorldExitTarget = ""
    @Published var selectedWorldOccurrenceTarget = ""
    @Published var selectedChamberObject = "trove"
    @Published private(set) var worldRewards: [HadesWorldReward] = []
    /// The shown selection of each Generate row; its shortcut generates it.
    @Published var selectedRewards: [HadesRewardGroup: String] = [:]
    @Published private(set) var worldTerms: [String: [String: String]] = [:]
    @Published private(set) var catalog: [HadesCatalogEntry] = []
    @Published private(set) var resourceCatalog: [HadesResourceDefinition] = []
    /// Exactly one session-scoped row controls acquisition rarity/level.
    @Published var selectedExactTrait = ""
    @Published var selectedChaosBlessing = ""
    @Published var selectedChaosCurse = ""
    @Published var acquisitionRarity = "Heroic"
    @Published var acquisitionLevel = "1"
    @Published var acquisitionEncounters = "3"
    @Published private(set) var acquisitionTarget: HadesAcquisitionTarget = .exact
    @Published private(set) var acquisitionRarityAdjustment: TrainerOrderedOptionResolution.Adjustment = .none
    private var resolvedAcquisitionSignature: String?
    private var acquisitionLevelIdentity: String?
    @Published private(set) var traitNames: [String: [String: String]] = [:]
    @Published private(set) var target: HadesHeroTarget?
    @Published private(set) var shortcutRegistrationFailure: TrainerHotkeyRegistrationFailure?
    @Published private(set) var shortcutRevision = 0
    /// Host-owned feedback and diagnostics state forwarded from `TrainerModuleServices`.
    var feedbackCenter: TrainerFeedbackCenter { services.feedback }
    var diagnosticsService: TrainerDiagnosticsService { services.diagnostics }
    var feedback: TrainerFeedbackNotice? { services.feedback.notice }
    var feedbackDetailsPresented: Bool { services.feedback.detailsPresented }
    var feedbackDetailsNoticeID: UUID? { services.feedback.detailsNoticeID }
    var currentIssues: [TrainerCurrentIssue] { services.feedback.currentIssues }
    /// Owner-state failures. Each one remains current until the same kind of
    /// payload decodes again; a one-shot rejection is only feedback.
    @Published private(set) var catalogIssue: TrainerTextToken?
    @Published private(set) var observationIssue: TrainerTextToken?
    @Published var shortcutSettingsPresented = false
    @Published var workbenchSearch = ""
    @Published var numericControlsExpanded = false
    @Published var profilesPresented = false
    @Published var diagnosticsPresented = false
    @Published private(set) var profiles: [HadesSettingsProfile] = []
    @Published private(set) var diagnostics: [TrainerDiagnosticCheck] = []
    @Published private(set) var profileShortcutWarning: TrainerTextToken?
    private var diagnosticsReport: [String: Any]?

    private let services: TrainerModuleServices
    private var subscriptions: Set<AnyCancellable> = []
    private var session: TrainerBackendSession { services.session }
    private var logSink: TrainerLogSink { services.logSink }
    private var shortcuts: HadesShortcutStore
    private lazy var hotkeys = services.makeHotkeys(registrationChanged: { [weak self] failure in
        self?.shortcutRegistrationFailure = failure
    }) { [weak self] action in self?.performShortcut(action) }

    var backendStatus: TrainerBackendStatus { services.backendStatus }
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var operation: TrainerTextToken { backendStatus.operation }
    /// Backend-owned tools, such as Save documents, stay usable while a request runs.
    var canUseBackend: Bool { backendAvailable && backendStatus.protocolCompatible }
    var hostActionsEnabled: Bool { canUseBackend && !busy }
    /// A new request for the current target lifetime: none is in flight and
    /// the session still trusts that target.
    var canAcceptRuntimeAction: Bool { !busy && !backendStatus.requiresTargetRestart }
    private var requiresExplicitReconnect: Bool {
        ["outcome_unknown", "restart_required", "debugger_protocol", "debugger_lost"]
            .contains(backendStatus.errorCode)
    }
    var canEditIntent: Bool {
        backendAvailable && backendStatus.protocolCompatible &&
            (!requiresExplicitReconnect || (!connected && backendStatus.requiresTargetRestart))
    }
    var canMutate: Bool { canEditIntent && connected && heroReady }
    var selectedWorldExit: HadesWorldDoor? {
        world?.doors.first { $0.effectiveDoorToken == selectedWorldExitToken }
    }
    var selectedWorldExitLease: HadesWorldActionLease? { selectedWorldExit?.activeLease }
    var selectedWorldExitTargetLocked: Bool { selectedWorldExitLease != nil }
    var canSelectWorldExit: Bool {
        canMutate && world?.doors.isEmpty == false
    }
    var selectedWorldExitActionAvailable: Bool {
        guard canMutate && canAcceptRuntimeAction, let exit = selectedWorldExit else { return false }
        if exit.activeLease != nil { return true }
        return exit.worldActionTargets.contains { $0.stableID == selectedWorldExitTarget }
    }
    var worldOccurrenceTargets: [HadesWorldOccurrenceTarget] {
        world?.worldOccurrenceTargets ?? []
    }
    var worldOccurrenceLease: HadesWorldOccurrenceLease? { world?.occurrence }
    var canSelectWorldOccurrence: Bool {
        canMutate && (!worldOccurrenceTargets.isEmpty || worldOccurrenceLease != nil)
    }
    var worldOccurrenceActionAvailable: Bool {
        guard canMutate && canAcceptRuntimeAction else { return false }
        if worldOccurrenceLease != nil { return true }
        return worldOccurrenceTargets.contains { $0.id == selectedWorldOccurrenceTarget }
    }
    var canSelectChamberObject: Bool {
        canMutate && world?.objects.isEmpty == false
    }
    var chamberObjectActionAvailable: Bool {
        guard canMutate && canAcceptRuntimeAction else { return false }
        return world?.objects.contains(selectedChamberObject) == true
    }
    var statusTitle: TrainerTextToken { TrainerTextToken(key: connected ? "host.connected" : "host.disconnected") }
    var connectionDetailText: TrainerTextToken {
        TrainerTextToken(key: connected ? (heroReady ? "hades.ready" : "hades.waitingForHero") : "hades.connectionHelp")
    }
    var launchActionFromHost: (@MainActor () -> Void)? { { [weak self] in self?.send(.launch, operation: "host.launchGame") } }

    init(services: TrainerModuleServices, defaults: UserDefaults = .standard) {
        self.services = services
        self.shortcuts = HadesShortcutStore(defaults: defaults)
        services.feedback.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &subscriptions)
        services.backendStatusTransitions
            .sink { [weak self] previous, current in
                self?.receiveStatus(current, previous: previous)
            }
            .store(in: &subscriptions)
        DispatchQueue.main.async { [weak self] in
            self?.installShortcuts()
        }
    }

    func backendDidStart() {
        refreshFromHost()
        send(.catalog, operation: "hades.catalog", announceSuccess: false)
    }

    func backendDidStop() { resetObservation() }

    func connectFromHost(reason: TrainerHostConnectReason) {
        guard !connected, hostActionsEnabled else { return }
        send(.connect, operation: "host.connectGame")
    }

    func disconnectFromHost() {
        guard connected, hostActionsEnabled else { return }
        send(.disconnect, operation: "host.disconnectGame")
    }
    func refreshFromHost() { send(.status, operation: "host.refreshStatus", announceSuccess: false) }
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {
        resetObservation()
    }
    func hostDidBecomeActive() { if connected && !busy { refreshFromHost() } }

    func isEnabled(_ feature: HadesFeature) -> Bool {
        pendingFeatureIntents[feature]?.enabled ?? features[feature.rawValue]?.bool ?? false
    }
    func isActive(_ feature: HadesFeature) -> Bool { activeFeatures[feature.rawValue] ?? false }
    func number(_ feature: HadesFeature) -> Double { features[feature.rawValue]?.number ?? feature.neutralValue }
    func observed(_ value: HadesHeroValue) -> Double? {
        switch value {
        case .health: health
        case .maxHealth: maxHealth
        case .money: money
        case .rerolls: rerolls
        case .godGauge: godGauge
        }
    }
    /// Hades I observations of one feature intent in the shared Core phase model.
    /// Every feature is supported on the verified image (the adapter refuses
    /// any other), and the runtime applies an intent only to a ready hero.
    func featurePresentation(_ feature: HadesFeature) -> TrainerFeaturePresentation {
        TrainerFeaturePresentation(
            enabled: isEnabled(feature),
            supported: true,
            connected: connected,
            active: isActive(feature),
            dormant: dormantFeatures[feature.rawValue] ?? false,
            activationPending: pendingFeatureIntents[feature] != nil,
            canActivate: heroReady,
            canEditDesired: canEditIntent
        )
    }
    func setBoonRarityTarget(_ target: String) {
        guard canEditIntent, ["Common", "Rare", "Epic", "Heroic"].contains(target) else { return }
        send(.setBoonRarity(target: target), operation: "hades.boonRarityEnabled")
    }
    func setFeature(_ feature: HadesFeature, value: Any) {
        guard canEditIntent else { return }
        var requestID: UUID?
        if feature.isToggle, let enabled = value as? Bool {
            let intent = PendingFeatureIntent(requestID: UUID(), enabled: enabled)
            pendingFeatureIntents[feature] = intent
            requestID = intent.requestID
        }
        send(.setFeature(feature: feature.rawValue, value: value), operation: feature.key) { [weak self] _ in
            // The reply has been projected; only this request's intent retires.
            guard let self, let requestID, self.pendingFeatureIntents[feature]?.requestID == requestID else { return }
            self.pendingFeatureIntents[feature] = nil
        }
    }
    static func displayText(_ value: Double) -> String {
        value.rounded() == value ? String(format: "%.0f", value) : String(value)
    }
    /// Validation and game meaning stay with Hades; Core only owns completion.
    /// A live edit applies to the hero captured when editing began. Invalid,
    /// unavailable or stale edits restore the observed value and emit one notice.
    func completeTextEdit(_ edit: HadesTextEdit, text: String, changed: Bool, target captured: HadesHeroTarget?,
                          onRejection: (String) -> Void) -> String {
        let current: Double?
        var range = 0.0...1_000_000_000.0
        var integer = true
        let available: Bool
        var heroOwned = true
        let apply: (Double) -> Void
        switch edit {
        case let .value(value):
            current = observed(value)
            if value == .health || value == .maxHealth { range = 1...1_000_000_000 }
            available = canMutate
            apply = { self.setValue(value.rawValue, value: $0, target: captured) }
        case let .resource(id):
            current = resources[id]
            available = canMutate
            apply = { self.setResource(id, value: $0, target: captured) }
        case let .feature(feature):
            current = number(feature)
            range = feature == .dashBonus ? 0...20 : 0.1...100
            integer = feature == .dashBonus
            available = canEditIntent
            heroOwned = false
            apply = { self.setFeature(feature, value: $0) }
        }
        let restored = current.map(Self.displayText) ?? ""
        guard changed else { return restored }
        if heroOwned && captured != target {
            onRejection("hades.error.staleHero")
            presentFeedback(TrainerTextToken(key: "hades.error.staleHero"), tone: .warning)
            return restored
        }
        guard available && current != nil && !busy else {
            onRejection("hades.input.unavailable")
            presentFeedback(TrainerTextToken(key: "hades.input.unavailable"), tone: .warning)
            return restored
        }
        let raw = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let value = Double(raw), value.isFinite, range.contains(value),
              !integer || (Int(raw) != nil && value.rounded() == value) else {
            onRejection("hades.input.invalid")
            presentFeedback(TrainerTextToken(key: "hades.input.invalid"), tone: .warning)
            return restored
        }
        if current != value { apply(value) }
        return Self.displayText(value)
    }
    func setValue(_ field: String, value: Double, target: HadesHeroTarget?) {
        sendToHero(.setValue(field: field, value: value), target: target, operation: "hades.values")
    }
    func setResource(_ resource: String, value: Double, target: HadesHeroTarget?) {
        sendToHero(.setResource(resource: resource, value: value), target: target, operation: "hades.resources")
    }
    func lockHealth(_ locked: Bool) {
        sendToHero(
            .lockVital(vital: "health", locked: locked),
            target: target,
            operation: "hades.values"
        )
    }
    func lockMoney(_ locked: Bool) {
        guard !(locked && isEnabled(.infiniteMoney)) else { return }
        sendToHero(
            .lockResource(resource: "Money", locked: locked),
            target: target,
            operation: "hades.values"
        )
    }
    func lockRerolls(_ locked: Bool) {
        guard !(locked && isEnabled(.infiniteRerolls)) else { return }
        sendToHero(
            .lockRerolls(locked: locked),
            target: target,
            operation: "hades.values"
        )
    }
    func gainResource(_ resource: String, amount: Double, target: HadesHeroTarget?) {
        sendToHero(.gainResource(resource: resource, amount: amount), target: target, operation: "hades.gainResource")
    }
    @discardableResult
    func worldAction(_ request: HadesRequest, roomID: String?, operation: String,
                     completion: ((Bool) -> Void)? = nil) -> Bool {
        guard let roomID, roomID == world?.roomId else {
            presentFeedback(TrainerTextToken(key: "hades.error.staleRoom"), tone: .warning)
            return false
        }
        return sendToHero(request, extraParams: ["roomId": roomID], target: target, operation: operation, completion: completion)
    }

    func repairWorldActionSelection() {
        let doors = world?.doors ?? []
        if !doors.contains(where: { $0.effectiveDoorToken == selectedWorldExitToken }) {
            selectedWorldExitToken = doors.first?.effectiveDoorToken ?? ""
        }
        if let exit = selectedWorldExit {
            if let lease = exit.activeLease {
                selectedWorldExitTarget = lease.kind + ":" + lease.target
            } else if !exit.worldActionTargets.contains(where: { $0.stableID == selectedWorldExitTarget }) {
                selectedWorldExitTarget = exit.worldActionTargets.first?.stableID ?? ""
            }
        } else {
            selectedWorldExitTarget = ""
        }

        if let occurrence = worldOccurrenceLease {
            selectedWorldOccurrenceTarget = occurrence.target
        } else if !worldOccurrenceTargets.contains(where: { $0.id == selectedWorldOccurrenceTarget }) {
            selectedWorldOccurrenceTarget = worldOccurrenceTargets.first?.id ?? ""
        }

        let objects = world?.objects ?? []
        if !objects.contains(selectedChamberObject) {
            selectedChamberObject = objects.first ?? "trove"
        }
    }

    @discardableResult
    func toggleSelectedWorldExit(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction, let exit = selectedWorldExit else { return false }
        if let lease = exit.activeLease {
            return worldAction(
                .cancelWorldExit(doorToken: exit.effectiveDoorToken, leaseToken: lease.leaseToken),
                roomID: world?.roomId,
                operation: "hades.worldActions.modifyExit", completion: completion
            )
        }
        guard let selected = exit.worldActionTargets.first(where: { $0.stableID == selectedWorldExitTarget }) else {
            return false
        }
        return worldAction(
            .applyWorldExit(doorToken: exit.effectiveDoorToken, kind: selected.kind, targetID: selected.id),
            roomID: world?.roomId,
            operation: "hades.worldActions.modifyExit", completion: completion
        )
    }

    @discardableResult
    func toggleWorldOccurrence(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction else { return false }
        if let lease = worldOccurrenceLease {
            return worldAction(
                .cancelWorldOccurrence(leaseToken: lease.leaseToken),
                roomID: world?.roomId,
                operation: "hades.occurrence.title", completion: completion
            )
        }
        guard worldOccurrenceTargets.contains(where: { $0.id == selectedWorldOccurrenceTarget }) else {
            return false
        }
        return worldAction(
            .applyWorldOccurrence(targetID: selectedWorldOccurrenceTarget),
            roomID: world?.roomId,
            operation: "hades.occurrence.title", completion: completion
        )
    }

    @discardableResult
    func generateSelectedChamberObject(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard chamberObjectActionAvailable else { return false }
        return worldAction(
            .generateChamberObject(object: selectedChamberObject),
            roomID: world?.roomId,
            operation: "hades.chamberObject", completion: completion
        )
    }

    func generateFishing(completion: ((Bool) -> Void)? = nil) {
        worldAction(.generateFishing, roomID: world?.roomId, operation: "hades.generateFishing", completion: completion)
    }
    func generateChaosGate(completion: ((Bool) -> Void)? = nil) {
        worldAction(.generateChaosGate, roomID: world?.roomId, operation: "hades.generateChaosGate", completion: completion)
    }
    /// A Generate row acts for a ready hero in an observed room.
    var canSpawnReward: Bool { canMutate && world != nil }
    /// One Generate row's rewards, in world-catalog order.
    func rewards(in group: HadesRewardGroup) -> [HadesWorldReward] { worldRewards.filter { $0.group == group } }
    /// Generates one reward of a row in the current room; false when the row cannot act on it.
    @discardableResult
    func spawnReward(_ reward: String, in group: HadesRewardGroup, completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canSpawnReward, rewards(in: group).contains(where: { $0.id == reward }) else { return false }
        return worldAction(.spawnReward(reward), roomID: world?.roomId,
                           operation: "hades.spawnReward", completion: completion)
    }
    private func acquisitionOption(_ target: HadesAcquisitionTarget) -> HadesCatalogEntry? {
        switch target {
        case .exact:
            return catalog.first { $0.id == selectedExactTrait && $0.kind != "curse" && $0.kind != "chaos" }
        case .chaos:
            return catalog.first { $0.id == selectedChaosBlessing && $0.kind == "chaos" }
        }
    }

    var acquisitionRarityOptions: [String] { acquisitionOption(acquisitionTarget)?.rarities ?? [] }
    var acquisitionSupportsLevel: Bool {
        acquisitionTarget == .exact && acquisitionOption(.exact)?.supportsLevel == true
    }
    var acquisitionAllowsCallerRarity: Bool { !acquisitionRarityOptions.isEmpty }

    func selectAcquisitionRarity(_ rarity: String) {
        guard acquisitionRarityOptions.contains(rarity) else { return }
        acquisitionRarity = rarity
        acquisitionRarityAdjustment = .none
    }

    /// Revalidate before applying, including a hotkey invoked from the other
    /// action. An adjusted value must be visible before the next one-shot.
    @discardableResult
    func activateAcquisition(_ target: HadesAcquisitionTarget, confirmationRequired: Bool = false) -> Bool {
        let previousTarget = acquisitionTarget
        acquisitionTarget = target
        guard let option = acquisitionOption(target) else {
            acquisitionRarityAdjustment = .none
            resolvedAcquisitionSignature = nil
            return false
        }
        let signature = [
            target.rawValue, option.id, option.rarities.joined(separator: ","),
            target == .chaos ? selectedChaosCurse : ""
        ].joined(separator: "|")
        // A number draft belongs to a particular acquisition target. A new
        // catalog observation for the same target must not clear a focused
        // edit; switching target identity must reset its level before Apply.
        let levelIdentity = target.rawValue + "|" + option.id
        if acquisitionLevelIdentity != levelIdentity {
            if acquisitionLevelIdentity != nil { acquisitionLevel = "1" }
            acquisitionLevelIdentity = levelIdentity
        }
        let changed = previousTarget != target || resolvedAcquisitionSignature != signature
        let resolved = TrainerOrderedOptionReconciler.resolve(
            previous: acquisitionRarity.isEmpty ? nil : acquisitionRarity,
            supported: option.rarities,
            preferredOrder: ["Common", "Rare", "Epic", "Heroic", "Duo", "Legendary"]
        )
        if let rarity = resolved.option { acquisitionRarity = rarity }
        if changed { acquisitionRarityAdjustment = resolved.adjustment }
        resolvedAcquisitionSignature = signature
        return !(confirmationRequired && changed && resolved.requiresVisibleConfirmation)
    }

    private var selectedAcquisitionRarity: String? {
        let options = acquisitionRarityOptions
        return options.contains(acquisitionRarity) ? acquisitionRarity : nil
    }

    @discardableResult
    func acquireSelectedTrait(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction,
              let trait = acquisitionOption(.exact), trait.acquirable != false,
              activateAcquisition(.exact, confirmationRequired: true),
              let rarity = selectedAcquisitionRarity else { return false }
        let level: Int
        if trait.supportsLevel {
            guard let amount = Int(acquisitionLevel), (1...100).contains(amount) else { return false }
            level = amount
        } else {
            level = 1
        }
        return sendToHero(
            .addTrait(trait: trait.id, rarity: rarity, level: level),
            target: target, operation: "hades.acquire", completion: completion
        )
    }

    @discardableResult
    func acquireSelectedChaosPair(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction,
              let blessing = acquisitionOption(.chaos), blessing.acquirable != false,
              catalog.contains(where: { $0.id == selectedChaosCurse && $0.kind == "curse" }),
              activateAcquisition(.chaos, confirmationRequired: true),
              let rarity = selectedAcquisitionRarity,
              let encounters = Int(acquisitionEncounters), (1...100).contains(encounters) else { return false }
        return sendToHero(
            .addChaosPair(blessing: blessing.id, curse: selectedChaosCurse, rarity: rarity, encounters: encounters),
            target: target, operation: "hades.chaosPair", completion: completion
        )
    }

    func updateTrait(_ trait: HadesCurrentTrait, rarity: String, level: Int, target: HadesHeroTarget?) {
        sendToHero(.updateTrait(instanceID: trait.instanceId, rarity: rarity, level: level), target: target, operation: "hades.apply")
    }
    func removeTrait(_ trait: HadesCurrentTrait) {
        sendToHero(.removeTrait(instanceID: trait.instanceId), target: target, operation: "hades.remove")
    }

    func setTraitUses(_ trait: HadesCurrentTrait, uses: Int, target: HadesHeroTarget?) {
        sendToHero(.setTraitUses(instanceID: trait.instanceId, uses: uses),
                   target: target, operation: "hades.remainingUses")
    }
    func expireTrait(_ trait: HadesCurrentTrait) {
        sendToHero(.expireTrait(instanceID: trait.instanceId), target: target,
                   operation: trait.blessing == nil ? "hades.expireEffect" : "hades.activateBlessing")
    }
    func refreshTrait(_ trait: HadesCurrentTrait) {
        sendToHero(.refreshTrait(instanceID: trait.instanceId), target: target,
                   operation: "hades.refreshEffect")
    }
    func disableAll() {
        guard hostActionsEnabled else { return }
        send(.disableAll, operation: "host.disableAll")
    }
    func makeSaveEditorModel(snapshotID: String? = nil) -> HadesSaveEditorModel {
        HadesSaveEditorModel(session: session, snapshotID: snapshotID)
    }
    func listProfiles() { send(.listProfiles, operation: "hades.manage.profiles", announceSuccess: false) }
    func saveProfile(_ name: String, completion: ((Bool) -> Void)? = nil) {
        send(.saveProfile(name: name, shortcuts: shortcuts.payload()), operation: "hades.profile.save", completion: completion)
    }
    func clearProfileShortcutWarning() { profileShortcutWarning = nil }
    func loadProfile(_ name: String) {
        profileShortcutWarning = nil
        send(.loadProfile(name: name), operation: "hades.profile.load")
    }
    func deleteProfile(_ name: String) { send(.deleteProfile(name: name), operation: "host.delete") }
    func runDiagnostics() { send(.diagnostics, operation: "hades.manage.diagnostics", announceSuccess: false) }
    func exportDiagnostics() {
        session.flushDiagnostics()
        logSink.flush()
        send(.diagnostics, operation: "hades.diagnostics.export", announceSuccess: false) { [weak self] ok in
            guard ok, let self, let report = self.diagnosticsReport else { return }
            self.services.diagnostics.exportReport(report)
        }
    }
    /// The originating field shows the same rejection inline; this is only the
    /// transient page notice, never retained as a current issue.
    func rejectInvalidValue() { presentFeedback(TrainerTextToken(key: "hades.error.invalidValue"), tone: .warning) }

    private func presentFeedback(_ text: TrainerTextToken, tone: TrainerFeedbackTone) {
        services.feedback.present(text, tone: tone)
    }

    /// Consume only the transient presentation event; current issues keep
    /// their owner state.
    func dismissFeedback(_ id: UUID) { services.feedback.dismiss(id) }

    func showFeedbackDetails(for noticeID: UUID? = nil) {
        services.feedback.showDetails(for: noticeID)
    }

    func closeFeedbackDetails() {
        services.feedback.closeDetails()
    }
    func traitName(_ trait: HadesCurrentTrait, language: TrainerPresentationLanguage) -> String {
        catalog.first { $0.id == trait.name }?.name(language: language.rawValue)
            ?? traitNames[trait.name]?[language.rawValue]
            ?? traitNames[trait.name]?["en"]
            ?? HadesPresentation.text("hades.unknownTrait", language: language)
    }

    @discardableResult
    private func sendToHero(_ request: HadesRequest, extraParams: [String: Any] = [:], target captured: HadesHeroTarget?,
                            operation: String, completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate else { return false }
        guard let captured, captured == target else {
            presentFeedback(TrainerTextToken(key: "hades.error.staleHero"), tone: .warning)
            return false
        }
        var payload = extraParams
        payload["target"] = captured.payload
        send(request, extraParams: payload, operation: operation, completion: completion)
        return true
    }

    func shortcutText(_ action: HadesShortcutAction) -> String { shortcuts.chord(action).displayText }
    @discardableResult
    func setShortcut(_ action: HadesShortcutAction, chord: HotkeyChord) -> TrainerShortcutAssignmentResult {
        if let conflict = shortcuts.set(action, chord: chord) {
            return .conflict(actionID: conflict.rawValue)
        }
        shortcutRevision += 1
        installShortcuts()
        return .applied
    }
    func resetShortcuts() { shortcuts.reset(); shortcutRevision += 1; installShortcuts() }
    private func installShortcuts() {
        hotkeys.register(HadesWorkbenchCatalog.orderedShortcutActions.map { HotkeyBinding(actionID: $0.rawValue, chord: shortcuts.chord($0)) })
    }
    private func canPerformShortcut(_ action: HadesShortcutAction) -> Bool {
        switch action {
        case .disableAll:
            return hostActionsEnabled
        case .generateFishing:
            return canMutate && world?.canFish == true
        case .applyWorldExit:
            return selectedWorldExitActionAvailable
        case .applyWorldOccurrence:
            return worldOccurrenceActionAvailable
        case .generateChamberObject:
            return chamberObjectActionAvailable
        case .generateChaosGate:
            return canMutate && world?.canChaos == true
        case .acquireChaosPair, .acquireExactBoon:
            return canMutate && canAcceptRuntimeAction
        default:
            return canEditIntent
        }
    }

    /// Hades II's refusal feedback: a log line, a warning notice and the rejected sound.
    private func rejectShortcut(_ actionID: String) {
        logSink.append("shortcut.rejected action=\(actionID) reason=unavailable")
        presentFeedback(TrainerTextToken(key: "hades.shortcut.unavailable"), tone: .warning)
        TrainerHotkeyFeedbackPlayer.play(.rejected)
    }

    private static func playOneShotShortcutResult(_ success: Bool) {
        TrainerHotkeyFeedbackPlayer.play(success ? .completed : .rejected)
    }

    private static func playDeferredShortcutResult(_ success: Bool) {
        TrainerHotkeyFeedbackPlayer.play(success ? .deferred : .rejected)
    }

    func performShortcut(_ rawValue: String) {
        guard !shortcutSettingsPresented, let action = HadesShortcutAction(rawValue: rawValue) else {
            rejectShortcut(rawValue); return
        }
        // A Generate row's shortcut acts on the selection the row shows, under
        // the same gate as its button.
        if let group = action.rewardGroup {
            if !spawnReward(selectedRewards[group] ?? "", in: group, completion: Self.playOneShotShortcutResult) {
                rejectShortcut(rawValue)
            }
            return
        }
        guard canPerformShortcut(action) else { rejectShortcut(rawValue); return }
        if action == .applyWorldExit {
            if !toggleSelectedWorldExit(completion: Self.playDeferredShortcutResult) { rejectShortcut(rawValue) }
            return
        }
        if action == .applyWorldOccurrence {
            if !toggleWorldOccurrence(completion: Self.playDeferredShortcutResult) { rejectShortcut(rawValue) }
            return
        }
        if action == .generateChamberObject {
            if !generateSelectedChamberObject(completion: Self.playOneShotShortcutResult) { rejectShortcut(rawValue) }
            return
        }
        if action == .acquireExactBoon {
            if !acquireSelectedTrait(completion: Self.playOneShotShortcutResult),
               acquisitionRarityAdjustment == .none { rejectShortcut(rawValue) }
            return
        }
        if action == .acquireChaosPair {
            if !acquireSelectedChaosPair(completion: Self.playOneShotShortcutResult),
               acquisitionRarityAdjustment == .none { rejectShortcut(rawValue) }
            return
        }
        if action == .generateFishing { generateFishing(completion: Self.playOneShotShortcutResult) }
        else if action == .generateChaosGate { generateChaosGate(completion: Self.playOneShotShortcutResult) }
        else if action == .decreaseGameSpeed || action == .increaseGameSpeed {
            let delta = action == .decreaseGameSpeed ? -0.1 : 0.1
            let current = number(.gameSpeed)
            let next = min(10.0, max(0.0, (current + delta) * 10.0).rounded() / 10.0)
            guard abs(next - current) >= 0.0001 else {
                rejectShortcut(rawValue)
                return
            }
            setFeature(.gameSpeed, value: next)
        }
        else if action == .disableAll { disableAll() }
        else if let feature = HadesFeature(rawValue: rawValue) { setFeature(feature, value: !isEnabled(feature)) }
    }

    func prepareForTermination(completion: @escaping () -> Void) {
        guard backendAvailable else {
            completion()
            return
        }
        send(.disableAll, operation: "host.disableAll", announceSuccess: false) { [weak self] _ in
            guard let self else { completion(); return }
            self.send(.disconnect, operation: "host.disconnectGame", announceSuccess: false) { _ in
                completion()
            }
        }
    }

    private func send(_ request: HadesRequest, extraParams: [String: Any] = [:], operation: String,
                      announceSuccess: Bool = true, completion: ((Bool) -> Void)? = nil) {
        var payload = request.params
        for (key, value) in extraParams { payload[key] = value }
        let expectedPending = (request.command == .disableAll || request.command == .loadProfile) && !connected
        session.send(request.command.rawValue, params: payload, operation: operation,
                     announceSuccess: announceSuccess && !expectedPending,
                     timeout: request.command.timeout,
                     requiresTrustedTarget: request.command.requiresTrustedTarget(connected: connected),
                     completion: { [weak self] ok in
            if announceSuccess, ok, let self, !self.connected,
               request.command == .disableAll || request.command == .loadProfile {
                let noticeKey = request.command == .disableAll ? "hades.disableAllPending" : "hades.profile.pending"
                self.presentFeedback(TrainerTextToken(key: noticeKey), tone: .warning)
            }
            completion?(ok)
        })
    }

    private func receiveStatus(_ status: TrainerBackendStatus, previous: TrainerBackendStatus) {
        objectWillChange.send()
        switch status.errorCode {
        case "outcome_unknown", "restart_required", "debugger_protocol", "debugger_lost":
            resetObservation()
        default: break
        }
    }

    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget {
        guard let connected = payload["connected"] as? Bool else { return .independent }
        return connected ? .process(identifier: payload["pid"] as? Int) : .lifetime
    }

    func applyStaleBackendPayload(_ payload: [String: Any]) {
        applyBackendPayload(payload, acceptsTargetObservation: false)
    }

    func applyBackendPayload(_ payload: [String: Any]) {
        applyBackendPayload(payload, acceptsTargetObservation: true)
    }

    private func applyBackendPayload(_ payload: [String: Any], acceptsTargetObservation: Bool) {
        let catalogPayload = payload["catalog"] != nil
        do {
            try decode(payload, acceptsTargetObservation: acceptsTargetObservation)
            // Only the same kind of payload proves its failure resolved.
            if catalogPayload { catalogIssue = nil }
            else if acceptsTargetObservation && payload["connected"] != nil { observationIssue = nil }
        } catch {
            guard acceptsTargetObservation else { return }
            let issue = TrainerTextToken(key: catalogPayload ? "hades.error.catalog" : "hades.error.protocol")
            let previous = catalogPayload ? catalogIssue : observationIssue
            if catalogPayload { catalogIssue = issue } else {
                resetObservation()
                observationIssue = issue
            }
            if previous != issue { presentFeedback(issue, tone: .warning) }
        }
    }

    private func decode(_ payload: [String: Any], acceptsTargetObservation: Bool) throws {
        let data = try JSONSerialization.data(withJSONObject: payload)
        if let rows = payload["profiles"] {
            profiles = try JSONDecoder().decode([HadesSettingsProfile].self,
                from: JSONSerialization.data(withJSONObject: rows))
        }
        if let profileShortcuts = payload["shortcuts"] as? [String: Any] {
            switch shortcuts.applyProfile(profileShortcuts) {
            case .applied:
                profileShortcutWarning = nil
                shortcutRevision += 1
                installShortcuts()
            case .unsupportedLayoutVersion(let version):
                profileShortcutWarning = TrainerTextToken(
                    key: "hades.error.profileShortcutLayoutUnsupported",
                    arguments: [String(version)]
                )
            }
        }
        if let report = payload["diagnostics"] as? [String: Any],
           let checks = report["checks"] as? [[String: Any]] {
            diagnostics = checks.compactMap(TrainerDiagnosticCheck.decode)
            diagnosticsReport = report
        }
        if payload["catalog"] != nil {
            let decoded = try JSONDecoder().decode(HadesCatalogPayload.self, from: data)
            catalog = decoded.catalog
            resourceCatalog = decoded.resourceCatalog
            resolvedAcquisitionSignature = nil
            if !catalog.contains(where: { $0.id == selectedChaosBlessing && $0.kind == "chaos" }) {
                selectedChaosBlessing = catalog.first { $0.kind == "chaos" }?.id ?? ""
            }
            if !catalog.contains(where: { $0.id == selectedChaosCurse && $0.kind == "curse" }) {
                selectedChaosCurse = catalog.first { $0.kind == "curse" }?.id ?? ""
            }
            traitNames = decoded.traitNames ?? [:]
            worldRewards = decoded.worldRewards ?? []
            worldTerms = decoded.worldTerms ?? [:]
            // Each Generate row shows a reward the catalog still offers it.
            for group in HadesRewardGroup.allCases {
                let offered = rewards(in: group)
                if !offered.contains(where: { $0.id == selectedRewards[group] }) {
                    selectedRewards[group] = offered.first?.id
                }
            }
        }
        guard payload["connected"] != nil else { return }
        let state = try JSONDecoder().decode(HadesObservation.self, from: data)
        guard acceptsTargetObservation else {
            applyDurableIntent(state)
            return
        }
        connected = state.connected
        heroReady = state.heroReady
        invincible = state.invincible ?? false
        // Without a ready hero the runtime and detached projections report
        // placeholder zeros; they are not observations.
        let heroObserved = state.connected && state.heroReady
        health = heroObserved ? state.health : nil
        maxHealth = heroObserved ? state.maxHealth : nil
        money = heroObserved ? state.money : nil
        rerolls = heroObserved ? state.rerolls : nil
        healthLocked = state.healthLocked ?? false
        moneyLocked = state.moneyLocked ?? false
        rerollsLocked = state.rerollsLocked ?? false
        godGauge = heroObserved ? state.godGauge : nil
        maxGodGauge = heroObserved ? state.maxGodGauge : nil
        target = state.target
        features = state.features ?? [:]
        activeFeatures = state.activeFeatures ?? [:]
        dormantFeatures = state.dormantFeatures ?? [:]
        boonRarityTarget = state.boonRarityTarget ?? boonRarityTarget
        resources = heroObserved ? (state.resources ?? [:]) : [:]
        traits = state.traits ?? []
        world = state.world
        repairWorldActionSelection()
    }

    private func applyDurableIntent(_ state: HadesObservation) {
        let speedKey = HadesFeature.gameSpeed.rawValue
        // The adapter always reports desired speed from preferences, even in a live snapshot.
        let speed = state.features?[speedKey]?.gameSpeedIntent(preservingRuntimeFrom: features[speedKey])
        if !connected && !state.connected {
            // A detached reply can omit preferences. Retain existing values for those fields.
            var desired = state.features ?? [:]
            desired[speedKey] = speed
            features.merge(desired) { _, value in value }
            healthLocked = state.healthLocked ?? healthLocked
            moneyLocked = state.moneyLocked ?? moneyLocked
            rerollsLocked = state.rerollsLocked ?? rerollsLocked
            boonRarityTarget = state.boonRarityTarget ?? boonRarityTarget
        } else if let speed {
            features[speedKey] = speed
        }
    }

    private func resetObservation() {
        connected = false; heroReady = false; invincible = false
        health = nil; maxHealth = nil; money = nil; rerolls = nil
        // Fixed locks are durable desired state. A target/process observation
        // reset clears live values but keeps their desired lock indicators until
        // the backend reprojects the preference document.
        godGauge = nil; maxGodGauge = nil
        target = nil
        let speedKey = HadesFeature.gameSpeed.rawValue
        if let speed = features[speedKey]?.gameSpeedIntent() { features[speedKey] = speed }
        activeFeatures = [:]; dormantFeatures = [:]; resources = [:]; traits = []; world = nil
        selectedWorldExitToken = ""
        selectedWorldExitTarget = ""
        selectedWorldOccurrenceTarget = ""
        selectedChamberObject = "trove"
    }
}

private struct PendingFeatureIntent {
    let requestID: UUID
    let enabled: Bool
}

struct HadesGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(sidebarIconSystemName: "flame.fill")
    static let presentationKeyPrefix = "hades."

    static func makeModel(services: TrainerModuleServices) -> HadesTrainerModel { HadesTrainerModel(services: services) }
    static func makeContent(model: HadesTrainerModel) -> HadesTrainerView { HadesTrainerView(model: model) }
    static func workbenchSections(model: HadesTrainerModel) -> [TrainerWorkbenchSectionItem] {
        HadesWorkbenchSection.visible.map { section in
            TrainerWorkbenchSectionItem(
                id: section.id,
                titleKey: section.titleKey,
                icon: section.icon,
                separatedFromPrevious: section == .management
            )
        }
    }
    static func workbenchSearch(model: HadesTrainerModel) -> TrainerWorkbenchSearchCatalog? {
        TrainerWorkbenchSearchCatalog(
            query: Binding(
                get: { model.workbenchSearch },
                set: { model.workbenchSearch = $0 }
            ),
            placeholderKey: "hades.workbench.search",
            emptyLabelKey: "hades.workbench.searchEmpty",
            search: { query, localization in
                HadesWorkbenchCatalog.matches(query, resources: model.resourceCatalog, worldTerms: model.worldTerms) { key in
                    TrainerPresentationLanguage.allCases.map {
                        localization.string(key, language: $0)
                    }
                }.map { entry in
                    let title: String
                    if let names = entry.worldNames {
                        title = names[localization.language.rawValue] ?? names["en"] ?? ""
                    } else if let resource = entry.resource {
                        title = resource.name(language: localization.language.rawValue)
                    } else {
                        title = localization.string(entry.titleKey)
                    }
                    return TrainerWorkbenchSearchCatalog.Result(
                        id: entry.id,
                        title: title,
                        detail: localization.string(entry.section.titleKey),
                        icon: entry.icon,
                        sectionID: entry.section.id,
                        onNavigate: {
                            if entry.requiresExpandedMetrics { model.numericControlsExpanded = true }
                        }
                    )
                }
            }
        )
    }
    static func makeManagementCatalog(
        model: HadesTrainerModel,
        localization: TrainerLocalizationStore,
        toolWindows: TrainerToolWindowActions
    ) -> TrainerManagementCatalog? {
        HadesManagementCatalog.make(
            model: model,
            localization: localization,
            openSaveEditor: {
                toolWindows.open("hades-save-editor", localization.string("hades.saveEditor.title")) {
                    makeSaveEditorWindow(model: model)
                }
            }
        )
    }
    static var managedBackupEditor: (@MainActor (HadesTrainerModel, TrainerSaveSnapshot) -> TrainerToolWindowContent)? {
        { model, snapshot in makeSaveEditorWindow(model: model, snapshotID: snapshot.id) }
    }
    @MainActor
    static func makeSaveEditorWindow(model: HadesTrainerModel, snapshotID: String? = nil) -> TrainerToolWindowContent {
        let editor = model.makeSaveEditorModel(snapshotID: snapshotID)
        return TrainerToolWindowContent(canClose: { !editor.busy }, onClose: editor.close) {
            HadesSaveEditorView(model: editor)
        }
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        HadesPresentation.text(key, language: language, arguments: arguments)
    }
}
