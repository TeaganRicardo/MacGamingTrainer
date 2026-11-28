import Combine
import Foundation
import AppKit
import SwiftUI
import TrainerCore

final class HadesTrainerModel: ObservableObject, TrainerHostModel {
    @Published private(set) var connected = false
    @Published private(set) var pid: Int32?
    @Published private(set) var version = ""
    @Published private(set) var status = "disconnected"
    @Published private(set) var scene = "unknown"
    @Published private(set) var roomName: String?
    @Published private(set) var exiting = false
    @Published private(set) var recoveryText: TrainerTextToken?
    private var recoveryTargetPID: Int?
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
    @Published private var pendingBoonRarityIntent: PendingBoonRarityIntent?
    @Published private var pendingBlockingRequests = 0
    @Published private var pendingRepeatableSpawns = 0
    @Published private(set) var boonRarityTarget = "Heroic"
    @Published private(set) var boonForceLegendary = false
    @Published private(set) var boonForceDuo = false
    @Published private(set) var fishingChance: Double?
    @Published private(set) var chaosGateChance: Double?
    @Published private(set) var resources: [String: Double] = [:]
    @Published private(set) var resourceLocks: [String: Int] = [:]
    @Published private(set) var traits: [HadesCurrentTrait] = []
    @Published private(set) var canOpenSellTraits = false
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
    private let runLogDirectoryURL: URL?
    private let runLogSettleInterval: TimeInterval
    private let playHotkeyFeedback: (TrainerHotkeyFeedback) -> Void
    private var subscriptions: Set<AnyCancellable> = []
    private var session: TrainerBackendSession { services.session }
    private var logSink: TrainerLogSink { services.logSink }
    private var launchAttachGate = HadesLaunchAttachGate()
    private var runLogTargetPID: pid_t?
    private var pendingRunReadySignal = false
    private var runLogSettleWorkItem: DispatchWorkItem?
    private var terminationRequestedFromHost = false
    private var terminationTargetObservation: TrainerTargetObservation?
    private var backendRestartGeneration: UInt64 = 0
    private lazy var runLogWatcher = HadesRunLogWatcher(directoryURL: runLogDirectoryURL) { [weak self] event in
        self?.handleRunLogEvent(event)
    }
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
    var hostActionsEnabled: Bool { canUseBackend && !busy && pendingBlockingRequests == 0 }
    /// A new request for the current target lifetime: none is in flight and
    /// the session still trusts that target.
    var canAcceptRuntimeAction: Bool {
        !busy && pendingBlockingRequests == 0 && !backendStatus.requiresTargetRestart
    }
    private var canQueueAnotherSpawn: Bool {
        !backendStatus.requiresTargetRestart && (
            canAcceptRuntimeAction || (
                pendingRepeatableSpawns > 0 && pendingRepeatableSpawns == pendingBlockingRequests
            )
        )
    }
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
    var selectedWorldExitChoice: HadesWorldExitChoice? { HadesWorldExitChoice(id: selectedWorldExitTarget) }
    var canSelectWorldExit: Bool {
        canMutate && world?.doors.isEmpty == false
    }
    var canSelectWorldExitTarget: Bool {
        guard canSelectWorldExit, !selectedWorldExitTargetLocked,
              let exit = selectedWorldExit else { return false }
        return exit.defaultChoice != nil
    }
    var selectedWorldExitActionAvailable: Bool {
        guard canMutate && canAcceptRuntimeAction, let exit = selectedWorldExit else { return false }
        if exit.activeLease != nil { return true }
        return selectedWorldExitChoice.map(exit.isEnabled) ?? false
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
    var canOpenSellTraitsAction: Bool {
        canMutate && canAcceptRuntimeAction && canOpenSellTraits
    }
    func showWorkbenchSection(_ section: HadesWorkbenchSection) {
        if section == .values { numericControlsExpanded = true }
        workbenchSearch = ""
    }
    var statusTitle: TrainerTextToken {
        if exiting { return TrainerTextToken(key: "hades.manage.exiting") }
        if backendStatus.isStartFailure || !backendAvailable {
            return TrainerTextToken(key: "hades.status.backendStopped")
        }
        if backendStatus.requiresTargetRestart || recoveryText != nil || status == "restart_required" {
            return TrainerTextToken(key: "hades.status.restartRequired")
        }
        switch status {
        case "ready":
            switch scene {
            case "house": return TrainerTextToken(key: "hades.status.house")
            case "courtyard": return TrainerTextToken(key: "hades.status.courtyard")
            case "run": return TrainerTextToken(key: "hades.status.run")
            default: return TrainerTextToken(key: "hades.status.operable")
            }
        case "waiting":
            switch scene {
            case "loading": return TrainerTextToken(key: "hades.status.loading")
            case "main_menu": return TrainerTextToken(key: "hades.status.mainMenu")
            default: return TrainerTextToken(key: "hades.status.awaitingScene")
            }
        case "not_running": return TrainerTextToken(key: "hades.status.notRunning")
        case "not_installed": return TrainerTextToken(key: "hades.status.notInstalled")
        case "incompatible": return TrainerTextToken(key: "hades.status.incompatible")
        case "backend_stopped": return TrainerTextToken(key: "hades.status.backendStopped")
        case "disconnected": return TrainerTextToken(key: "hades.status.disconnected")
        default: return TrainerTextToken(key: status)
        }
    }
    var connectionDetailText: TrainerTextToken {
        guard !version.isEmpty else {
            return TrainerTextToken(key: "hades.status.awaitingDetect")
        }
        guard let pid else {
            return TrainerTextToken(key: "hades.status.versionDetail", arguments: [version])
        }
        return TrainerTextToken(key: "hades.status.detailWithPID", arguments: [version, String(pid)])
    }
    var launchActionFromHost: (@MainActor () -> Void)? { { [weak self] in self?.send(.launch, operation: "host.launchGame") } }

    init(
        services: TrainerModuleServices,
        defaults: UserDefaults = .standard,
        runLogDirectoryURL: URL? = nil,
        runLogSettleInterval: TimeInterval = 0.2,
        hotkeyFeedback: @escaping (TrainerHotkeyFeedback) -> Void = TrainerHotkeyFeedbackPlayer.play
    ) {
        self.services = services
        self.runLogDirectoryURL = runLogDirectoryURL
        self.runLogSettleInterval = runLogSettleInterval
        self.playHotkeyFeedback = hotkeyFeedback
        self.shortcuts = HadesShortcutStore(defaults: defaults)
        services.feedback.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &subscriptions)
        services.backendStatusTransitions
            .sink { [weak self] previous, current in
                guard let self else { return }
                self.receiveStatus(current, previous: previous)
                if !current.busy && !self.exiting && !self.terminationRequestedFromHost {
                    DispatchQueue.main.async { [weak self] in
                        guard let self else { return }
                        self.consumeDeferredLaunchAttachIfPossible()
                        self.consumeRunLogReadySignalIfPossible()
                    }
                }
            }
            .store(in: &subscriptions)
        DispatchQueue.main.async { [weak self] in
            self?.installShortcuts()
        }
    }

    func backendWillRestart() {
        backendRestartGeneration &+= 1
        pendingFeatureIntents.removeAll()
        pendingBoonRarityIntent = nil
        pendingBlockingRequests = 0
        pendingRepeatableSpawns = 0
        pendingRunReadySignal = false
        cancelPendingRunLogSettle()
        launchAttachGate.cancel()
        services.feedback.clearNotice()
    }

    func backendDidStart() {
        runLogWatcher.start()
        refreshFromHost()
        send(.catalog, operation: "hades.catalog", announceSuccess: false)
    }

    func backendDidStop() { resetObservation() }

    func connectFromHost(reason: TrainerHostConnectReason) {
        guard !connected, hostActionsEnabled else { return }
        switch reason {
        case .manual:
            launchAttachGate.cancel()
            connect()
        case .automatic(let targetJustLaunched):
            if launchAttachGate.deferUntilReady(
                targetJustLaunched: targetJustLaunched,
                canObserveLifecycle: runLogWatcher.canObserveLifecycle
            ) {
                runLogWatcher.start()
                status = "waiting"
                scene = "loading"
                consumeDeferredLaunchAttachIfPossible()
                return
            }
            connect()
        }
    }

    private func connect() {
        pendingRunReadySignal = false
        cancelPendingRunLogSettle()
        runLogWatcher.start()
        send(.connect, operation: "host.connectGame") { [weak self] _ in
            guard let self else { return }
            self.runLogWatcher.start()
            self.consumeRunLogReadySignalIfPossible()
        }
    }

    func disconnectFromHost() {
        guard connected, hostActionsEnabled else { return }
        launchAttachGate.cancel()
        pendingRunReadySignal = false
        cancelPendingRunLogSettle()
        send(.disconnect, operation: "host.disconnectGame")
    }
    func refreshFromHost() { send(.status, operation: "host.refreshStatus", announceSuccess: false) }
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {
        // The definitive launch notification can follow discovery of this PID.
        if observation.isRunning, let pid = observation.processIdentifier, pid == runLogTargetPID { return }
        runLogTargetPID = observation.processIdentifier
        if connected || pid != nil || recoveryText != nil {
            resetObservation()
            status = observation.isRunning ? "disconnected" : "not_running"
        }
        pid = observation.processIdentifier
        recoveryText = nil
        recoveryTargetPID = nil
        launchAttachGate.targetLifetimeChanged()
        pendingRunReadySignal = false
        cancelPendingRunLogSettle()
        runLogWatcher.targetLifetimeChanged(running: observation.isRunning)
    }
    func beginTerminationFromHost() {
        guard !terminationRequestedFromHost else { return }
        terminationRequestedFromHost = true
        terminationTargetObservation = services.targetObservation
        launchAttachGate.cancel()
        pendingRunReadySignal = false
        cancelPendingRunLogSettle()
        runLogWatcher.stop()
    }
    func hostDidBecomeActive() { if connected && !busy { refreshFromHost() } }

    private func cancelPendingRunLogSettle() {
        runLogSettleWorkItem?.cancel()
        runLogSettleWorkItem = nil
    }

    private func handleRunLogEvent(_ event: HadesRunLogEvent) {
        guard !exiting, !terminationRequestedFromHost else { return }
        switch event {
        case .bootReady:
            recordLaunchReadiness()
        case .mainMenu:
            cancelPendingRunLogSettle()
            pendingRunReadySignal = false
            recordLaunchReadiness()
            guard connected else { return }
            status = "waiting"
            scene = "main_menu"
            roomName = nil
            activeFeatures = [:]
        case .runtimeReset:
            cancelPendingRunLogSettle()
            pendingRunReadySignal = false
            launchAttachGate.observeRuntimeReset()
            guard connected else { return }
            status = "waiting"
            scene = "loading"
            roomName = nil
            activeFeatures = [:]
        case .roomTransitionStarted:
            cancelPendingRunLogSettle()
            pendingRunReadySignal = false
            launchAttachGate.observeRuntimeReset()
            guard connected else { return }
            status = "waiting"
            scene = "loading"
        case .roomLoaded:
            recordLaunchReadiness()
            guard connected else { return }
            scheduleRunLogSettleRefresh()
        }
    }

    private func recordLaunchReadiness() {
        launchAttachGate.observeRuntimeReady()
        guard launchAttachGate.isPending else { return }
        // Let all events in this log batch settle before crossing into LLDB.
        DispatchQueue.main.async { [weak self] in
            self?.consumeDeferredLaunchAttachIfPossible()
        }
    }

    private func scheduleRunLogSettleRefresh() {
        cancelPendingRunLogSettle()
        if runLogSettleInterval <= 0 {
            pendingRunReadySignal = true
            consumeRunLogReadySignalIfPossible()
            return
        }
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.runLogSettleWorkItem = nil
            self.pendingRunReadySignal = true
            self.consumeRunLogReadySignalIfPossible()
        }
        runLogSettleWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + runLogSettleInterval, execute: work)
    }

    private func consumeDeferredLaunchAttachIfPossible() {
        guard !exiting, !terminationRequestedFromHost, !backendStatus.requiresTargetRestart else { return }
        guard launchAttachGate.consumeIfEligible(
            backendAvailable: backendAvailable,
            busy: busy,
            connected: connected,
            exiting: exiting,
            requiresTargetRestart: backendStatus.requiresTargetRestart
        ) else { return }
        connect()
    }

    private func consumeRunLogReadySignalIfPossible() {
        guard !exiting, !terminationRequestedFromHost else { return }
        guard HadesRunLogRefreshGate.shouldConsume(
            pending: pendingRunReadySignal,
            connected: connected,
            backendAvailable: backendAvailable,
            busy: busy,
            exiting: exiting,
            requiresTargetRestart: backendStatus.requiresTargetRestart
        ) else { return }
        pendingRunReadySignal = false
        send(.status, operation: "host.refreshStatus", announceSuccess: false) { [weak self] _ in
            self?.consumeRunLogReadySignalIfPossible()
        }
    }

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
    var effectiveBoonRarityTarget: String { pendingBoonRarityIntent?.target ?? boonRarityTarget }
    var effectiveBoonForceLegendary: Bool { pendingBoonRarityIntent?.forceLegendary ?? boonForceLegendary }
    var effectiveBoonForceDuo: Bool { pendingBoonRarityIntent?.forceDuo ?? boonForceDuo }
    func setBoonRarityTarget(_ target: String) {
        setBoonRarity(
            target: target,
            forceLegendary: effectiveBoonForceLegendary,
            forceDuo: effectiveBoonForceDuo
        )
    }
    func setBoonForceLegendary(_ enabled: Bool) {
        setBoonRarity(
            target: effectiveBoonRarityTarget,
            forceLegendary: enabled,
            forceDuo: effectiveBoonForceDuo
        )
    }
    func setBoonForceDuo(_ enabled: Bool) {
        setBoonRarity(
            target: effectiveBoonRarityTarget,
            forceLegendary: effectiveBoonForceLegendary,
            forceDuo: enabled
        )
    }
    func setBoonRarity(target: String, forceLegendary: Bool, forceDuo: Bool, completion: ((Bool) -> Void)? = nil) {
        guard canEditIntent, ["Common", "Rare", "Epic", "Heroic"].contains(target) else {
            completion?(false)
            return
        }
        let requestID = UUID()
        pendingBoonRarityIntent = PendingBoonRarityIntent(
            requestID: requestID,
            target: target,
            forceLegendary: forceLegendary,
            forceDuo: forceDuo
        )
        send(
            .setBoonRarity(target: target, forceLegendary: forceLegendary, forceDuo: forceDuo),
            operation: "hades.boonRarityEnabled"
        ) { [weak self] ok in
            if let self, self.pendingBoonRarityIntent?.requestID == requestID {
                self.pendingBoonRarityIntent = nil
            }
            completion?(ok)
        }
    }
    func setFishingChance(_ chance: Double?, completion: ((Bool) -> Void)? = nil) {
        guard canEditIntent, chance.map({ $0.isFinite && (0...100).contains($0) }) ?? true else {
            completion?(false)
            return
        }
        guard pendingBlockingRequests > 0 || chance != fishingChance else {
            completion?(true)
            return
        }
        send(.setFishingChance(chance), operation: "hades.fishing.probability", completion: completion)
    }
    func setChaosGateChance(_ chance: Double?, completion: ((Bool) -> Void)? = nil) {
        guard canEditIntent, chance.map({ $0.isFinite && (0...100).contains($0) }) ?? true else {
            completion?(false)
            return
        }
        guard pendingBlockingRequests > 0 || chance != chaosGateChance else {
            completion?(true)
            return
        }
        send(.setChaosGateChance(chance), operation: "hades.chaosGate.probability", completion: completion)
    }
    func setFeature(_ feature: HadesFeature, value: Any, completion: ((Bool) -> Void)? = nil) {
        guard canEditIntent else {
            completion?(false)
            return
        }
        var requestID: UUID?
        if feature.isToggle, let enabled = value as? Bool {
            let intent = PendingFeatureIntent(requestID: UUID(), enabled: enabled)
            pendingFeatureIntents[feature] = intent
            requestID = intent.requestID
        }
        send(.setFeature(feature: feature.rawValue, value: value), operation: feature.key) { [weak self] ok in
            // The reply has been projected; only this request's intent retires.
            if let self, let requestID, self.pendingFeatureIntents[feature]?.requestID == requestID {
                self.pendingFeatureIntents[feature] = nil
            }
            completion?(ok)
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
        var optionalCurrent = false
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
            if feature == .dashBonus {
                range = 0...20
            } else if feature == .moneyMultiplier || feature == .resourceMultiplier {
                range = 1...100
            } else {
                range = 0.1...100
            }
            integer = feature == .dashBonus
            available = canEditIntent
            heroOwned = false
            apply = { self.setFeature(feature, value: $0) }
        case .fishingChance:
            current = fishingChance
            range = 0...100
            integer = false
            optionalCurrent = true
            available = canEditIntent
            heroOwned = false
            apply = { self.setFishingChance($0) }
        case .chaosGateChance:
            current = chaosGateChance
            range = 0...100
            integer = false
            optionalCurrent = true
            available = canEditIntent
            heroOwned = false
            apply = { self.setChaosGateChance($0) }
        }
        let restored = current.map(Self.displayText) ?? ""
        guard changed else { return restored }
        if heroOwned && captured != target {
            onRejection("hades.error.staleHero")
            presentFeedback(TrainerTextToken(key: "hades.error.staleHero"), tone: .warning)
            return restored
        }
        guard available && (optionalCurrent || current != nil) && !busy else {
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
    func lockResource(_ resource: String, locked: Bool) {
        sendToHero(
            .lockResource(resource: resource, locked: locked),
            target: target,
            operation: "hades.resources"
        )
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
                     repeatableSpawn: Bool = false, completion: ((Bool) -> Void)? = nil) -> Bool {
        guard let roomID, roomID == world?.roomId else {
            presentFeedback(TrainerTextToken(key: "hades.error.staleRoom"), tone: .warning)
            return false
        }
        return sendToHero(request, extraParams: ["roomId": roomID], target: target,
                          operation: operation, repeatableSpawn: repeatableSpawn, completion: completion)
    }

    func repairWorldActionSelection() {
        let doors = world?.doors ?? []
        if !doors.contains(where: { $0.effectiveDoorToken == selectedWorldExitToken }) {
            selectedWorldExitToken = doors.first?.effectiveDoorToken ?? ""
        }
        if let exit = selectedWorldExit {
            if let lease = exit.activeLease {
                selectedWorldExitTarget = lease.choice.id
            } else if !(selectedWorldExitChoice.map(exit.isEnabled) ?? false) {
                selectedWorldExitTarget = exit.defaultChoice?.id ?? ""
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
        guard let choice = selectedWorldExitChoice, exit.isEnabled(choice) else {
            return false
        }
        return worldAction(
            .applyWorldExit(doorToken: exit.effectiveDoorToken, room: choice.room, reward: choice.reward),
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

    @discardableResult
    func generateFishing(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction && world?.canFish == true else { return false }
        return worldAction(.generateFishing, roomID: world?.roomId, operation: "hades.generateFishing", completion: completion)
    }
    @discardableResult
    func generateChaosGate(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate && canAcceptRuntimeAction && world?.canChaos == true else { return false }
        return worldAction(.generateChaosGate, roomID: world?.roomId, operation: "hades.generateChaosGate", completion: completion)
    }
    /// A Generate row acts for a ready hero in an observed room.
    var canSpawnReward: Bool { canMutate && world != nil && canQueueAnotherSpawn }
    var canAcquireExactTrait: Bool { canMutate && canQueueAnotherSpawn }
    /// One Generate row's rewards, in world-catalog order.
    func rewards(in group: HadesRewardGroup) -> [HadesWorldReward] { worldRewards.filter { $0.group == group } }
    /// Generates one reward of a row in the current room; false when the row cannot act on it.
    @discardableResult
    func spawnReward(_ reward: String, in group: HadesRewardGroup, completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canSpawnReward, rewards(in: group).contains(where: { $0.id == reward }) else { return false }
        return worldAction(.spawnReward(reward), roomID: world?.roomId,
                           operation: "hades.spawnReward", repeatableSpawn: true, completion: completion)
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
        guard canAcquireExactTrait,
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
            target: target, operation: "hades.acquire", repeatableSpawn: true, completion: completion
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

    @discardableResult
    func openSellTraits(completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canOpenSellTraitsAction else { return false }
        return sendToHero(.openSellTraits, target: target, operation: "hades.purgingPool", completion: completion)
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
    func disableAll(completion: ((Bool) -> Void)? = nil) {
        guard hostActionsEnabled else {
            completion?(false)
            return
        }
        send(.disableAll, operation: "host.disableAll", completion: completion)
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
                            operation: String, repeatableSpawn: Bool = false, completion: ((Bool) -> Void)? = nil) -> Bool {
        guard canMutate else { return false }
        guard let captured, captured == target else {
            presentFeedback(TrainerTextToken(key: "hades.error.staleHero"), tone: .warning)
            return false
        }
        var payload = extraParams
        payload["target"] = captured.payload
        send(request, extraParams: payload, operation: operation, repeatableSpawn: repeatableSpawn, completion: completion)
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
            return canMutate && canAcceptRuntimeAction && world?.canFish == true
        case .applyWorldExit:
            return selectedWorldExitActionAvailable
        case .applyWorldOccurrence:
            return worldOccurrenceActionAvailable
        case .generateChamberObject:
            return chamberObjectActionAvailable
        case .generateChaosGate:
            return canMutate && canAcceptRuntimeAction && world?.canChaos == true
        case .acquireChaosPair:
            return canMutate && canAcceptRuntimeAction
        case .acquireExactBoon:
            return canAcquireExactTrait
        case .openSellTraits:
            return canOpenSellTraitsAction
        default:
            return canEditIntent
        }
    }

    /// Hades II's refusal feedback: a log line, a warning notice and the rejected sound.
    private func rejectShortcut(_ actionID: String) {
        logSink.append("shortcut.rejected action=\(actionID) reason=unavailable")
        presentFeedback(TrainerTextToken(key: "hades.shortcut.unavailable"), tone: .warning)
        playHotkeyFeedback(.rejected)
    }

    private func makeOneShotShortcutResult() -> (Bool) -> Void {
        { [weak self] success in
            self?.playHotkeyFeedback(success ? .completed : .rejected)
        }
    }

    private func makeDeferredShortcutResult() -> (Bool) -> Void {
        { [weak self] success in
            self?.playHotkeyFeedback(success ? .deferred : .rejected)
        }
    }

    func featureHotkeyFeedback(_ feature: HadesFeature, targetEnabled: Bool) -> TrainerHotkeyFeedback {
        guard targetEnabled else { return .disabled }
        if activeFeatures[feature.rawValue] == true { return .enabled }
        if dormantFeatures[feature.rawValue] == true || !connected || !heroReady { return .deferred }
        return .unconfirmed
    }

    private func performFeatureShortcut(_ feature: HadesFeature) {
        let targetEnabled = !isEnabled(feature)
        setFeature(feature, value: targetEnabled) { [weak self] success in
            guard let self else { return }
            guard success else {
                self.playHotkeyFeedback(.rejected)
                return
            }
            let feedback = self.featureHotkeyFeedback(feature, targetEnabled: targetEnabled)
            if case .unconfirmed = feedback {
                self.presentFeedback(TrainerTextToken(key: "hades.shortcut.unconfirmed"), tone: .information)
            }
            self.playHotkeyFeedback(feedback)
        }
    }

    func performShortcut(_ rawValue: String) {
        guard !shortcutSettingsPresented, let action = HadesShortcutAction(rawValue: rawValue) else {
            rejectShortcut(rawValue); return
        }
        // A Generate row's shortcut acts on the selection the row shows, under
        // the same gate as its button.
        if let group = action.rewardGroup {
            if !spawnReward(selectedRewards[group] ?? "", in: group, completion: makeOneShotShortcutResult()) {
                rejectShortcut(rawValue)
            }
            return
        }
        guard canPerformShortcut(action) else { rejectShortcut(rawValue); return }
        if action == .applyWorldExit {
            if !toggleSelectedWorldExit(completion: makeDeferredShortcutResult()) { rejectShortcut(rawValue) }
            return
        }
        if action == .applyWorldOccurrence {
            if !toggleWorldOccurrence(completion: makeDeferredShortcutResult()) { rejectShortcut(rawValue) }
            return
        }
        if action == .generateChamberObject {
            if !generateSelectedChamberObject(completion: makeOneShotShortcutResult()) { rejectShortcut(rawValue) }
            return
        }
        if action == .acquireExactBoon {
            if !acquireSelectedTrait(completion: makeOneShotShortcutResult()),
               acquisitionRarityAdjustment == .none { rejectShortcut(rawValue) }
            return
        }
        if action == .acquireChaosPair {
            if !acquireSelectedChaosPair(completion: makeOneShotShortcutResult()),
               acquisitionRarityAdjustment == .none { rejectShortcut(rawValue) }
            return
        }
        if action == .openSellTraits {
            if !openSellTraits(completion: makeOneShotShortcutResult()) { rejectShortcut(rawValue) }
            return
        }
        if action == .generateFishing {
            if !generateFishing(completion: makeOneShotShortcutResult()) { rejectShortcut(rawValue) }
        } else if action == .generateChaosGate {
            if !generateChaosGate(completion: makeOneShotShortcutResult()) { rejectShortcut(rawValue) }
        } else if action == .decreaseGameSpeed || action == .increaseGameSpeed {
            let delta = action == .decreaseGameSpeed ? -0.1 : 0.1
            let current = number(.gameSpeed)
            let next = min(10.0, max(0.0, (current + delta) * 10.0).rounded() / 10.0)
            guard abs(next - current) >= 0.0001 else {
                rejectShortcut(rawValue)
                return
            }
            setFeature(.gameSpeed, value: next, completion: makeOneShotShortcutResult())
        } else if action == .disableAll {
            let wasConnected = connected
            disableAll { [weak self] success in
                guard let self else { return }
                let confirmed = wasConnected && self.connected
                self.playHotkeyFeedback(success ? (confirmed ? .disabled : .deferred) : .rejected)
            }
        } else if let feature = HadesFeature(rawValue: rawValue) {
            performFeatureShortcut(feature)
        }
    }

    func prepareForTermination(completion: @escaping () -> Void) {
        guard !exiting else { completion(); return }
        exiting = true
        terminationRequestedFromHost = true
        let targetAtQuit = terminationTargetObservation ?? services.targetObservation
        cancelPendingRunLogSettle()
        launchAttachGate.cancel()
        runLogWatcher.stop()
        guard backendAvailable else {
            completion()
            return
        }
        if connected && services.targetObservation != targetAtQuit {
            send(.disconnect, operation: "host.disconnectGame", announceSuccess: false) { _ in
                completion()
            }
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
                      announceSuccess: Bool = true, repeatableSpawn: Bool = false,
                      completion: ((Bool) -> Void)? = nil) {
        var payload = request.params
        for (key, value) in extraParams { payload[key] = value }
        let expectedPending = (request.command == .disableAll || request.command == .loadProfile) && !connected
        let restartGeneration = backendRestartGeneration
        pendingBlockingRequests += 1
        if repeatableSpawn { pendingRepeatableSpawns += 1 }
        session.send(request.command.rawValue, params: payload, operation: operation,
                     announceSuccess: announceSuccess && !expectedPending,
                     timeout: request.command.timeout,
                     requiresTrustedTarget: request.command.requiresTrustedTarget(connected: connected),
                     completion: { [weak self] ok in
            if let self, self.backendRestartGeneration == restartGeneration {
                self.pendingBlockingRequests = max(0, self.pendingBlockingRequests - 1)
                if repeatableSpawn { self.pendingRepeatableSpawns = max(0, self.pendingRepeatableSpawns - 1) }
            }
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
        case "outcome_unknown", "restart_required":
            resetObservation()
            self.status = "restart_required"
        case "debugger_protocol", "debugger_lost":
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
        if acceptsTargetObservation && payload.keys.contains("recovery") {
            applyRecoveryPatch(payload["recovery"])
        }
        guard payload["connected"] != nil else { return }
        let state = try JSONDecoder().decode(HadesObservation.self, from: data)
        guard acceptsTargetObservation else {
            applyDurableIntent(state, payload: payload)
            return
        }
        logSink.updateCurrentSessionRuntimeIdentity(
            gameVersion: state.version.flatMap { $0.isEmpty ? nil : $0 },
            runtimeRevision: state.runtimeRevision
        )
        if let observedPID = state.pid, let recPID = recoveryTargetPID, Int(observedPID) != recPID {
            recoveryText = nil
            recoveryTargetPID = nil
        }
        if payload.keys.contains("pid") { pid = state.pid }
        if payload.keys.contains("version") { version = state.version ?? "" }
        if payload.keys.contains("recovery") { applyRecoveryPatch(payload["recovery"]) }
        connected = state.connected
        heroReady = state.heroReady
        if recoveryText != nil && !state.connected {
            status = "restart_required"
        } else if let decodedStatus = state.status, !decodedStatus.isEmpty {
            status = decodedStatus
        } else {
            status = state.connected
                ? (state.heroReady ? "ready" : "waiting")
                : (backendStatus.requiresTargetRestart ? "restart_required" : "disconnected")
        }
        scene = (state.scene?.isEmpty == false ? state.scene : nil) ?? "unknown"
        roomName = state.roomName
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
        boonForceLegendary = state.boonForceLegendary ?? boonForceLegendary
        boonForceDuo = state.boonForceDuo ?? boonForceDuo
        if payload.keys.contains("fishingChance") { fishingChance = state.fishingChance }
        if payload.keys.contains("chaosGateChance") { chaosGateChance = state.chaosGateChance }
        resources = heroObserved ? (state.resources ?? [:]) : [:]
        resourceLocks = state.resourceLocks ?? [:]
        traits = state.traits ?? []
        canOpenSellTraits = heroObserved && (state.canOpenSellTraits ?? false)
        world = state.world
        repairWorldActionSelection()
    }

    private func applyDurableIntent(_ state: HadesObservation, payload: [String: Any]) {
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
            resourceLocks = state.resourceLocks ?? resourceLocks
            boonRarityTarget = state.boonRarityTarget ?? boonRarityTarget
            boonForceLegendary = state.boonForceLegendary ?? boonForceLegendary
            boonForceDuo = state.boonForceDuo ?? boonForceDuo
            if payload.keys.contains("fishingChance") { fishingChance = state.fishingChance }
            if payload.keys.contains("chaosGateChance") { chaosGateChance = state.chaosGateChance }
        } else if let speed {
            features[speedKey] = speed
        }
    }

    private func applyRecoveryPatch(_ value: Any?) {
        guard let recovery = value as? [String: Any] else {
            recoveryText = nil
            recoveryTargetPID = nil
            return
        }
        let recoveryPID = recovery["pid"] as? Int
        let observedPID = services.targetObservation.processIdentifier.map(Int.init) ?? pid.map(Int.init)
        if let observedPID, let recoveryPID, observedPID != recoveryPID { return }
        let key: String
        switch recovery["outcome"] as? String {
        case "unknown": key = "hades.error.restartRequired"
        case "confirmed": key = "hades.error.commandResultConnectionLost"
        default: key = "hades.error.recoveryFailed"
        }
        recoveryTargetPID = recoveryPID ?? observedPID
        recoveryText = TrainerTextToken(key: key)
    }

    private func resetObservation() {
        connected = false; heroReady = false; invincible = false
        status = recoveryText != nil || backendStatus.requiresTargetRestart ? "restart_required" : "disconnected"
        scene = "unknown"; roomName = nil
        health = nil; maxHealth = nil; money = nil; rerolls = nil
        // Fixed locks are durable desired state. A target/process observation
        // reset clears live values but keeps their desired lock indicators until
        // the backend reprojects the preference document.
        godGauge = nil; maxGodGauge = nil
        target = nil
        let speedKey = HadesFeature.gameSpeed.rawValue
        if let speed = features[speedKey]?.gameSpeedIntent() { features[speedKey] = speed }
        activeFeatures = [:]; dormantFeatures = [:]; resources = [:]; traits = []; canOpenSellTraits = false; world = nil
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

private struct PendingBoonRarityIntent {
    let requestID: UUID
    let target: String
    let forceLegendary: Bool
    let forceDuo: Bool
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
            ) {
                model.showWorkbenchSection(section)
            }
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
                            if entry.requiresExpandedMetrics || entry.section == .values {
                                model.numericControlsExpanded = true
                            }
                            model.workbenchSearch = ""
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
