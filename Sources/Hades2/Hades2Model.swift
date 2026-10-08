import Foundation
import AppKit

enum Hades2ShortcutIssue: Equatable {
    case unrecognized
    case conflict(chordText: String, action: ShortcutAction)
    case registration(TrainerHotkeyRegistrationFailure)
}

struct Hades2RuntimeIssuePresentation: Hashable {
    let featureID: String
    let token: TrainerTextToken
}

final class Hades2TrainerModel: ObservableObject, TrainerHostModel {
    private static let expectedHostProtocolVersion = Hades2GameModule.descriptor.expectedHostProtocolVersion
    private static let expectedModuleProtocolVersion = Hades2GameModule.descriptor.expectedModuleProtocolVersion
    private struct StatRule {
        let min: Double
        let max: Double
        let integer: Bool
    }
    static let gameSpeedInputRange = 0.0...10.0
    private static let statRules: [String: StatRule] = [
        "grasp": .init(min: 0, max: 999, integer: true),
        "dodge": .init(min: 0, max: 100, integer: false),
        "crit": .init(min: 0, max: 100, integer: false),
        "chargeSpeed": .init(min: 10, max: 1000, integer: false),
        "moveSpeed": .init(min: 10, max: 1000, integer: false),
        "sprintSpeed": .init(min: 10, max: 1000, integer: false),
        "dashSpeed": .init(min: 10, max: 1000, integer: false),
        "attackSpeed": .init(min: 10, max: 1000, integer: false),
        "manaRegen": .init(min: 0, max: 1000, integer: false),
        "enemyDamage": .init(min: 0, max: 1000, integer: false),
        "enemyHealth": .init(min: 10, max: 1000, integer: false),
    ]
    @Published var connected = false
    @Published private(set) var editGeneration: UInt64 = 0
    @Published private(set) var backendStatus = TrainerBackendStatus()
    private let backendSession: TrainerBackendSession
    private let logSink: TrainerLogSink
    private let backendScriptURL: URL?
    private let runLogDirectoryURL: URL?
    private lazy var api = Hades2API(session: backendSession)
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var backendProtocolVersion: Int? { backendStatus.backendProtocolVersion }
    var backendModuleProtocolVersion: Int? { backendStatus.backendModuleProtocolVersion }
    var protocolCompatible: Bool { backendStatus.protocolCompatible }
    var busy: Bool { backendStatus.busy }
    var operation: TrainerTextToken { backendStatus.operation }
    /// Version plus PID as one token. An undetected version is its own key so
    /// the awaiting-detection state survives a language switch.
    var connectionDetailText: Hades2Presentation.Text {
        guard !version.isEmpty else {
            return Hades2Presentation.token("hades2.status.awaitingDetect")
        }
        guard let pid else {
            return Hades2Presentation.token("hades2.status.versionDetail", arguments: [version])
        }
        return Hades2Presentation.token("hades2.status.detailWithPID", arguments: [version, String(pid)])
    }
    var hostActionsEnabled: Bool { !busy && !exiting && protocolCompatible }
    // Hades-owned notice/error are language-neutral tokens. Core-owned failures
    // still arrive as backendStatus strings, which the Host resolves; anything
    // Hades produces itself is a token so it can be re-resolved live.
    @Published private var noticeToken: TrainerTextToken? {
        didSet { if let noticeToken { presentFeedback(noticeToken, tone: .success) } }
    }
    @Published private var errorToken: TrainerTextToken? {
        didSet { if let errorToken { presentFeedback(errorToken, tone: .warning) } }
    }
    @Published private(set) var feedbackNotice: TrainerFeedbackNotice?
    private var receiptPresentedDuringReply = false
    @Published private var runtimeIssueToken: TrainerTextToken?
    @Published private(set) var runtimeIssuePresentations: [Hades2RuntimeIssuePresentation] = []
    private var runtimeFeatureErrors: [String: String] = [:]
    private var runtimeFeaturePresentationTokens: [String: TrainerTextToken] = [:]

    /// Core-owned error text (for example a protocol failure raised by the Host).
    var error: String {
        get { backendStatus.error }
        set {
            // A Core-owned error is newer than anything the model has presented,
            // so a stale Hades-owned token must not keep winning the banner.
            if !newValue.isEmpty {
                errorToken = nil
                if newValue != backendStatus.error {
                    presentFeedback(TrainerTextToken(key: newValue), tone: .warning)
                }
            }
            backendStatus.error = newValue
        }
    }

    /// Core-owned notice text.
    var notice: String {
        get { backendStatus.notice }
        set {
            if !newValue.isEmpty {
                noticeToken = nil
                if newValue != backendStatus.notice {
                    presentFeedback(TrainerTextToken(key: newValue), tone: .success)
                }
            }
            backendStatus.notice = newValue
        }
    }

    /// Latest backend-reported error as a token, with the arguments the backend
    /// sent for it. Empty when the current error is Core-owned plain text.
    var backendErrorText: TrainerTextToken {
        TrainerTextToken(key: backendStatus.error, arguments: backendStatus.errorArguments)
    }
    /// Latest user-facing notice, resolved by the module's presentation layer.
    var noticeText: TrainerTextToken { noticeToken ?? TrainerTextToken(key: "") }
    /// Latest user-facing error, resolved by the module's presentation layer.
    var errorText: TrainerTextToken { errorToken ?? TrainerTextToken(key: "") }
    /// Runtime activation issues, when the backend reported any.
    var runtimeIssueText: TrainerTextToken { runtimeIssueToken ?? TrainerTextToken(key: "") }
    @Published var pid: Int?
    @Published var version = ""
    @Published var status = "disconnected"
    @Published var scene = "unknown"
    @Published var capabilities: [String: Bool] = [:]
    @Published var activeFeatures: [String: Bool] = [:]
    @Published var dormantFeatures: [String: Bool] = [:]
    @Published var featureSupport: [String: Bool] = [:]
    @Published var invincibility = false
    @Published var infiniteHealth = false
    @Published var infiniteMana = false
    @Published var instantCastCooldown = false
    @Published var hexAlwaysReady = false
    @Published var infiniteAmmo = false
    @Published var autoMiniGames = false
    @Published var gardenQoL = false
    @Published var boonRarityEnabled = false
    @Published var forceEnableRerolls = false
    @Published var damageEnabled = false
    @Published var damageMultiplier = 2.0
    @Published var gameSpeed = 1.0
    @Published var boonRarityTarget = "Epic"
    @Published var boonRarityMultiplier = 100.0
    // These wire keys now mean force one currently eligible special boon
    // into the native three-choice pool.
    @Published var boonForceLegendary = false
    @Published var boonForceDuo = false
    @Published var nextRoomReward: String?
    @Published var health: Double?
    @Published var maxHealth: Double?
    @Published var healthLocked = false
    @Published var mana: Double?
    @Published var maxMana: Double?
    @Published var manaLocked = false
    @Published var armor: Double?
    @Published var armorLocked = false
    @Published var spellCharge: Double?
    @Published var spellChargeCost: Double?
    @Published var money: Double?
    @Published var runCount: Int?
    @Published var warning = ""
    @Published var runtimeIssue = ""
    @Published var moneyLocked = false
    @Published var moneyMultiplier = 2.0
    @Published var moneyMultiplierEnabled = false
    @Published var resourceMultiplier = 2.0
    @Published var resourceMultiplierEnabled = false
    @Published var rerolls: Double?
    @Published var rerollsLocked = false
    @Published private(set) var chaosGateProbability: Double?
    @Published private(set) var gatheringProbabilities: [Hades2GatheringFamily: Double] = [:]
    @Published private(set) var gatheringTargets: [Hades2GatheringFamily: Hades2GatheringTarget] = [:]
    @Published var boons: [BoonOption] = []
    @Published var selectedOlympianReward = ""
    @Published var selectedPickupReward = ""
    @Published var selectedSpecialReward = ""
    @Published var selectedExactBoon = ""
    @Published var selectedNextRoomReward = ""
    @Published var statSupport: [String: Bool] = [:]
    @Published var statAvailable: [String: Bool] = [:]
    @Published var graspValue: Double?
    @Published var dodgeValue: Double?
    @Published var critValue: Double?
    @Published var chargeSpeedValue: Double?
    @Published var moveSpeedValue: Double?
    @Published var sprintSpeedValue: Double?
    @Published var dashSpeedValue: Double?
    @Published var attackSpeedValue: Double?
    @Published var manaRegenValue: Double?
    @Published var enemyDamageValue: Double?
    @Published var enemyHealthValue: Double?
    @Published var graspLocked = false
    @Published var dodgeLocked = false
    @Published var critLocked = false
    @Published var chargeSpeedLocked = false
    @Published var moveSpeedLocked = false
    @Published var sprintSpeedLocked = false
    @Published var dashSpeedLocked = false
    @Published var attackSpeedLocked = false
    @Published var manaRegenLocked = false
    @Published var enemyDamageLocked = false
    @Published var enemyHealthLocked = false
    /// Current-run trait/buff inventory, projected from live runtime state.
    @Published var currentRunTraits: [CurrentRunTrait] = []
    /// The identity scope the runtime reported, so the UI never implies a
    /// durable identifier the runtime has not proven.
    @Published var currentRunTraitScope: CurrentRunTraitScope = .currentRun
    @Published var elements: [ElementCount] = []
    @Published var profiles: [TrainerProfile] = []
    @Published var diagnostics: [DiagnosticCheck] = []
    @Published var diagnosticsPassed = 0
    @Published var diagnosticsTotal = 0
    @Published var resources: [MaterialResource] = []
    @Published private var shortcutStore = Hades2ShortcutStore()
    @Published var shortcutIssue: Hades2ShortcutIssue?
    @Published var exiting = false
    @Published var shortcutSettingsPresented = false

    private let mutationScheduler = Hades2MutationScheduler()
    private lazy var runLogWatcher = Hades2RunLogWatcher(directoryURL: runLogDirectoryURL) { [weak self] event in
        self?.handleRunLogEvent(event)
    }
    private var pendingRunReadySignal = false
    private var activationGraceWorkItems: [Hades2FeatureKey: DispatchWorkItem] = [:]
    @Published private var activationGraceFeatures: Set<Hades2FeatureKey> = []
    private var hotkeys: GlobalHotkeys?
    private var shuttingDown = false
    private var presentedActionReceipt: Hades2ActionReceipt?
    var canSetFeature: Bool { connected && capabilities["setFeature"] == true && !exiting }
    var canEditDesired: Bool { backendAvailable && !exiting }
    var canSetVitals: Bool { connected && capabilities["setVitals"] == true && !exiting }
    var canSetResource: Bool { connected && capabilities["setResource"] == true && !exiting }
    var canSpawnReward: Bool { connected && capabilities["spawnReward"] == true && !exiting }
    var canOpenNativeBoonScreen: Bool { connected && status == "ready" && scene == "run" && !busy && !exiting }
    var exactBoonOptions: [BoonOption] {
        boons.filter {
            $0.group == "exact" && $0.acquisitionMode != "echoLastRunExact"
        }
    }

    var specialRewardOptions: [BoonOption] {
        let specials = boons.filter { $0.group == "special" }
        var seenSources = Set<String>()
        var nativeActions: [BoonOption] = []
        // Individual exact traits have moved out of Character Rewards, but the
        // same source rows still carry the authoritative native-choice support
        // bit. Synthesize each source entry once without reintroducing the
        // individual exact targets into the mixed list.
        for option in boons where option.nativeChoice && !option.sourceId.isEmpty {
            guard seenSources.insert(option.sourceId).inserted else { continue }
            nativeActions.append(BoonOption(
                id: "native-choice:\(option.sourceId)",
                name: option.nativeChoiceTitle.isEmpty ? option.sectionTitle : option.nativeChoiceTitle,
                englishName: option.nativeChoiceEnglishTitle.isEmpty ? option.englishSectionTitle : option.nativeChoiceEnglishTitle,
                category: option.category,
                englishCategory: option.englishCategory,
                kind: "native_choice",
                group: "special",
                targetID: "",
                officialName: true,
                sectionTitle: option.sectionTitle,
                englishSectionTitle: option.englishSectionTitle,
                sourceId: option.sourceId,
                sourceName: option.sourceName,
                sourceEnglishName: option.sourceEnglishName,
                nativeChoice: true,
                nativeChoiceTitle: option.nativeChoiceTitle,
                nativeChoiceEnglishTitle: option.nativeChoiceEnglishTitle,
                acquisitionMode: "",
                sortSection: option.sortSection,
                sortGroup: option.sortGroup,
                sortOrder: Int.min
            ))
        }
        return specials + nativeActions
    }
    private var selectedSpecialBoon: BoonOption? {
        specialRewardOptions.first { $0.id == selectedSpecialReward }
    }
    var canPerformSelectedSpecialReward: Bool {
        guard let option = selectedSpecialBoon else { return false }
        return option.kind == "native_choice" ? canOpenNativeBoonScreen : canSpawnReward
    }
    var canSetStats: Bool { connected && capabilities["setStats"] == true && !exiting }
    var canSetElements: Bool { connected && capabilities["setElements"] == true && !exiting }
    func supportsFeature(_ key: Hades2FeatureKey) -> Bool { featureSupport[key.rawValue] ?? true }
    func isFeatureActivationPending(_ key: Hades2FeatureKey) -> Bool { activationGraceFeatures.contains(key) }
    var ready: Bool { canSetFeature }
    /// Language-neutral status key. The Host renders it, so switching language
    /// updates the connection card without a backend round trip.
    var statusTitle: Hades2Presentation.Text {
        if exiting { return Hades2Presentation.token("hades2.manage.exiting") }
        switch status {
        case "ready":
            if scene == "crossroads" { return Hades2Presentation.token("hades2.status.crossroads") }
            if scene == "run" { return Hades2Presentation.token("hades2.status.run") }
            return Hades2Presentation.token("hades2.status.operable")
        case "waiting":
            if scene == "loading" { return Hades2Presentation.token("hades2.status.loading") }
            if scene == "main_menu" { return Hades2Presentation.token("hades2.status.mainMenu") }
            return Hades2Presentation.token("hades2.status.awaitingScene")
        case "not_running": return Hades2Presentation.token("hades2.status.notRunning")
        case "incompatible": return Hades2Presentation.token("hades2.status.incompatible")
        case "restart_required": return Hades2Presentation.token("hades2.status.restartRequired")
        case "backend_stopped": return Hades2Presentation.token("hades2.status.backendStopped")
        case "disconnected": return Hades2Presentation.token("hades2.status.disconnected")
        // An unknown status is backend-owned machine identity, not copy, so it
        // is reported as-is instead of being looked up as a presentation key.
        default: return TrainerTextToken(key: status)
        }
    }

    init(session: TrainerBackendSession, logSink: TrainerLogSink,
         backendScriptURL: URL? = nil, runLogDirectoryURL: URL? = nil) {
        backendSession = session
        self.logSink = logSink
        self.backendScriptURL = backendScriptURL
        self.runLogDirectoryURL = runLogDirectoryURL
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.runLogWatcher.start()
            self.installHotkeys()
            self.startBackend()
        }
    }

    func makeSaveEditorModel() -> Hades2SaveEditorModel {
        Hades2SaveEditorModel(session: backendSession)
    }

    func toggleConnectionFromHost() { toggleConnection(probeRuntime: true) }

    func connectAutomaticallyFromHost(targetJustLaunched: Bool) {
        let canDeferRuntimeProbe = targetJustLaunched && runLogWatcher.canObserveLifecycle
        toggleConnection(probeRuntime: !canDeferRuntimeProbe)
    }

    func refreshFromHost() {
        send(connected ? .status : .scan, title: "host.refreshStatus")
    }

    func hostDidBecomeActive() {
        guard connected,
              status == "waiting",
              backendAvailable,
              !busy,
              !exiting else { return }
        send(.status, title: "hades2.op.probeScene", announceSuccess: false)
    }

    private func handleRunLogEvent(_ event: Hades2RunLogEvent) {
        guard !exiting else { return }
        switch event {
        case .mainMenu, .runtimeReset:
            guard connected else { return }
            pendingRunReadySignal = false
            invalidatePendingMutations()
            status = "waiting"
            scene = event == .mainMenu ? "main_menu" : "loading"
            activeFeatures = [:]
            dormantFeatures = Dictionary(uniqueKeysWithValues:
                Hades2FeatureKey.allCases.filter { desiredFeatureEnabled($0) }.map { ($0.rawValue, true) }
            )
            capabilities = capabilities.mapValues { _ in false }
            capabilities["diagnostics"] = true
            statAvailable = statAvailable.mapValues { _ in false }
            activationGraceWorkItems.values.forEach { $0.cancel() }
            activationGraceWorkItems = [:]
            activationGraceFeatures = []
            if event == .runtimeReset {
                send(.runtimeReset, title: "hades2.op.recordRuntimeReset", announceSuccess: false)
            }
        case .runtimeReady:
            pendingRunReadySignal = true
            guard connected else { return }
            consumeRunLogReadySignalIfPossible()
        }
    }

    private func consumeRunLogReadySignalIfPossible() {
        guard Hades2RunLogRefreshGate.shouldConsume(
            pending: pendingRunReadySignal,
            connected: connected,
            backendAvailable: backendAvailable,
            busy: busy,
            exiting: exiting
        ) else { return }
        pendingRunReadySignal = false
        send(.status, title: "hades2.op.probeScene", announceSuccess: false) { [weak self] _ in
            self?.consumeRunLogReadySignalIfPossible()
        }
    }

    private func toggleConnection(probeRuntime: Bool) {
        if connected {
            sendBarrier(.disconnect, title: "host.disconnectGame")
        } else {
            if probeRuntime {
                pendingRunReadySignal = false
            }
            runLogWatcher.start()
            send(.connect(probeRuntime: probeRuntime), title: "host.connectGame") { [weak self] _ in
                guard let self else { return }
                self.runLogWatcher.start()
                self.consumeRunLogReadySignalIfPossible()
            }
        }
    }

    func restartBackendFromHost() { restartBackend() }

    func launchGame() { send(.launch, title: "host.launchGame") }
    func prepareDebugging() { send(.prepare, title: "hades2.manage.prepareSigning") }
    func restoreOriginalSignature() { send(.restore, title: "hades2.manage.restoreSigning") }
    func disableAll() { sendBarrier(.disableAll, title: "host.disableAll") }

    private func restartBackend() {
        guard !exiting else { return }
        invalidatePendingMutations()
        error = ""
        errorToken = nil
        notice = ""
        noticeToken = nil
        backendSession.restart()
    }

    private func startBackend() {
        guard !backendSession.isStarted else { return }
        do {
            try backendSession.start(
                descriptor: Hades2GameModule.descriptor,
                backendScriptURL: backendScriptURL,
                applyPayload: { [weak self] payload in self?.apply(payload) },
                resetGameState: { [weak self] in self?.resetAfterBackendTermination() },
                log: { [weak self] line in self?.appendLog(line) },
                onStatusChange: { [weak self] status in
                    self?.applyBackendStatus(status)
                    if !status.busy {
                        self?.consumeRunLogReadySignalIfPossible()
                    }
                }
            )
            send(.scan, title: "hades2.op.detectGame")
        } catch {
            // TrainerBackendSession owns startup failure identity, presentation,
            // diagnostics, and status projection.
            status = "backend_stopped"
        }
    }

    private func resetAfterBackendTermination() {
        feedbackNotice = nil
        connected = false
        scene = "unknown"
        capabilities = [:]
        activeFeatures = [:]
        dormantFeatures = [:]
        featureSupport = [:]
        statSupport = [:]
        statAvailable = [:]
        // Observable state, so it cannot outlive the backend that produced it.
        // The next payload repopulates it; until then an empty list means
        // "not observed yet" rather than the previous run's traits.
        currentRunTraits = []
        activationGraceWorkItems.values.forEach { $0.cancel() }
        activationGraceWorkItems = [:]
        activationGraceFeatures = []
        invalidatePendingMutations()
        pendingRunReadySignal = false
        pid = nil
        // Empty means "not detected yet"; the connection detail resolves that as
        // its own key, so a restart returns to the awaiting-detection state.
        version = ""
        warning = ""
        // Both the Core-owned strings and the Hades-owned tokens must be
        // cleared: the banner prefers the token, so a stale token would
        // outlive this reset.
        runtimeIssue = ""
        runtimeIssueToken = nil
        runtimeIssuePresentations = []
        runtimeFeatureErrors = [:]
        runtimeFeaturePresentationTokens = [:]
        noticeToken = nil
        errorToken = nil
        presentedActionReceipt = nil
        // Lock flags and locked values mirror durable desired targets from the
        // backend preference store; retain those projections across a worker
        // restart. Unlocked values are observations and are cleared below.
        // Catalog-backed element/resource rows are runtime snapshots and reset.
        if !healthLocked {
            health = nil
            maxHealth = nil
        }
        if !manaLocked {
            mana = nil
            maxMana = nil
        }
        if !armorLocked { armor = nil }
        if !moneyLocked { money = nil }
        if !rerollsLocked { rerolls = nil }
        gatheringTargets = [:]
        if !graspLocked { graspValue = nil }
        if !dodgeLocked { dodgeValue = nil }
        if !critLocked { critValue = nil }
        if !chargeSpeedLocked { chargeSpeedValue = nil }
        if !moveSpeedLocked { moveSpeedValue = nil }
        if !sprintSpeedLocked { sprintSpeedValue = nil }
        if !dashSpeedLocked { dashSpeedValue = nil }
        if !attackSpeedLocked { attackSpeedValue = nil }
        if !manaRegenLocked { manaRegenValue = nil }
        if !enemyDamageLocked { enemyDamageValue = nil }
        if !enemyHealthLocked { enemyHealthValue = nil }
        spellCharge = nil
        spellChargeCost = nil
        runCount = nil
        elements = []
        resources = []
        boons = []
        diagnostics = []
        diagnosticsPassed = 0
        diagnosticsTotal = 0
        notice = ""
        noticeToken = nil
        status = "backend_stopped"
    }

    private func apply(_ payload: [String: Any]) {
        let patch = Hades2StatePatch(payload)
        let wasConnected = connected
        let oldPID = pid
        let desiredBeforeApply = Dictionary(uniqueKeysWithValues: Hades2FeatureKey.allCases.map { ($0, desiredFeatureEnabled($0)) })

        if let value = patch.connected, wasConnected && !value { invalidatePendingMutations() }
        if patch.pid.isPresent, oldPID != patch.pid.value { invalidatePendingMutations() }
        if let value = patch.connected { connected = value }
        if patch.pid.isPresent { pid = patch.pid.value }
        if let value = patch.version { version = value }
        if let value = patch.currentRunTraits { currentRunTraits = value }
        if let value = patch.currentRunTraitIdentityScope {
            // The runtime states its own identity scope. Carry it verbatim so a
            // future build that proves a stronger scope is not downgraded, and
            // so the UI can only claim what the runtime claimed.
            currentRunTraitScope = CurrentRunTraitScope(
                identityScope: value,
                isPersistent: patch.currentRunTraitIdentityPersistent ?? false
            )
        }
        if let value = patch.status { status = value }
        if let value = patch.scene { scene = value }
        if let value = patch.capabilities { capabilities = value }
        if let value = patch.activeFeatures { activeFeatures = value }
        if let value = patch.dormantFeatures { dormantFeatures = value }
        if let value = patch.featureSupport { featureSupport = value }
        if patch.featureErrors.isPresent {
            runtimeFeatureErrors = patch.featureErrors.value ?? [:]
        }
        if patch.featureErrorPresentations.isPresent {
            runtimeFeaturePresentationTokens = (patch.featureErrorPresentations.value ?? [:]).reduce(
                into: [String: TrainerTextToken]()
            ) { result, entry in
                result[entry.key] = TrainerTextToken(
                    key: entry.value.key,
                    arguments: entry.value.arguments
                )
            }
        }
        if patch.featureErrors.isPresent || patch.featureErrorPresentations.isPresent {
            rebuildRuntimeIssuePresentations()
        }

        if let desired = patch.desiredFeatures {
            for (key, value) in desired { self[keyPath: key.modelKeyPath] = value }
        }
        if let value = patch.gameSpeed { gameSpeed = value }
        if let value = patch.damageMultiplier { damageMultiplier = value }
        if let value = patch.moneyLocked { moneyLocked = value }
        if let value = patch.moneyMultiplier { moneyMultiplier = value }
        if let value = patch.resourceMultiplier { resourceMultiplier = value }
        if let rarity = patch.boonRarity {
            if let value = rarity.target { boonRarityTarget = value }
            if let value = rarity.multiplier { boonRarityMultiplier = value }
            if let value = rarity.forceLegendary { boonForceLegendary = value }
            if let value = rarity.forceDuo { boonForceDuo = value }
        }
        if patch.nextRoomReward.isPresent { nextRoomReward = patch.nextRoomReward.value }
        if patch.rerolls.isPresent { rerolls = patch.rerolls.value }
        if let value = patch.rerollsLocked { rerollsLocked = value }
        if patch.chaosGateProbability.isPresent { chaosGateProbability = patch.chaosGateProbability.value }
        if patch.gatheringProbabilities.isPresent { gatheringProbabilities = patch.gatheringProbabilities.value ?? [:] }
        if patch.gatheringTargets.isPresent { gatheringTargets = patch.gatheringTargets.value ?? [:] }
        if patch.warningText.isPresent { warning = patch.warningText.value ?? "" }
        if let receipt = patch.lastAction { presentActionReceipt(receipt) }
        if let value = patch.boons { boons = value }
        if let value = patch.statSupport { statSupport = value }
        if let value = patch.statAvailable { statAvailable = value }

        if let stats = patch.stats {
            applyStat(stats["grasp"], value: &graspValue, locked: &graspLocked)
            applyStat(stats["dodge"], value: &dodgeValue, locked: &dodgeLocked)
            applyStat(stats["crit"], value: &critValue, locked: &critLocked)
            applyStat(stats["chargeSpeed"], value: &chargeSpeedValue, locked: &chargeSpeedLocked)
            applyStat(stats["moveSpeed"], value: &moveSpeedValue, locked: &moveSpeedLocked)
            applyStat(stats["sprintSpeed"], value: &sprintSpeedValue, locked: &sprintSpeedLocked)
            applyStat(stats["dashSpeed"], value: &dashSpeedValue, locked: &dashSpeedLocked)
            applyStat(stats["attackSpeed"], value: &attackSpeedValue, locked: &attackSpeedLocked)
            applyStat(stats["manaRegen"], value: &manaRegenValue, locked: &manaRegenLocked)
            applyStat(stats["enemyDamage"], value: &enemyDamageValue, locked: &enemyDamageLocked)
            applyStat(stats["enemyHealth"], value: &enemyHealthValue, locked: &enemyHealthLocked)
        }
        if let value = patch.profiles { profiles = value }
        if let value = patch.diagnostics {
            diagnostics = value
            diagnosticsPassed = patch.diagnosticsPassed ?? value.filter(\.ok).count
            diagnosticsTotal = patch.diagnosticsTotal ?? value.count
        }

        for (rawKey, active) in activeFeatures where active {
            if let key = Hades2FeatureKey(rawValue: rawKey) { clearFeatureActivationGrace(key) }
        }
        for key in Hades2FeatureKey.allCases where desiredFeatureEnabled(key)
            && desiredBeforeApply[key] != true
            && activeFeatures[key.rawValue] != true
            && dormantFeatures[key.rawValue] != true {
            beginFeatureActivationGrace(key)
        }
        if !wasConnected && connected {
            for key in Hades2FeatureKey.allCases where desiredFeatureEnabled(key)
                && activeFeatures[key.rawValue] != true
                && dormantFeatures[key.rawValue] != true {
                beginFeatureActivationGrace(key)
            }
        }

        if let shortcuts = patch.shortcuts { applyProfileShortcuts(shortcuts) }
        if patch.health.isPresent { health = patch.health.value }
        if patch.maxHealth.isPresent { maxHealth = patch.maxHealth.value }
        if let value = patch.healthLocked { healthLocked = value }
        if patch.mana.isPresent { mana = patch.mana.value }
        if patch.maxMana.isPresent { maxMana = patch.maxMana.value }
        if let value = patch.manaLocked { manaLocked = value }
        if patch.armor.isPresent { armor = patch.armor.value }
        if let value = patch.armorLocked { armorLocked = value }
        if patch.spellCharge.isPresent { spellCharge = patch.spellCharge.value }
        if patch.spellChargeCost.isPresent { spellChargeCost = patch.spellChargeCost.value }
        if patch.money.isPresent { money = patch.money.value }
        if patch.runCount.isPresent { runCount = patch.runCount.value }
        if let value = patch.elements { elements = value }
        if let value = patch.resources { resources = value }
        if let issue = patch.error, !issue.isEmpty { error = issue }


    }

    private func rebuildRuntimeIssuePresentations() {
        // Keep legacy runtime-owned text working, but let structured
        // presentations override the same feature so a Core-owned Host key
        // never becomes an opaque argument inside a Hades sentence.
        var entries = runtimeFeatureErrors.compactMap { featureID, message -> Hades2RuntimeIssuePresentation? in
            guard !message.isEmpty else { return nil }
            return Hades2RuntimeIssuePresentation(
                featureID: featureID,
                token: TrainerTextToken(key: message)
            )
        }
        for (featureID, token) in runtimeFeaturePresentationTokens where !token.key.isEmpty {
            entries.removeAll { $0.featureID == featureID }
            entries.append(Hades2RuntimeIssuePresentation(featureID: featureID, token: token))
        }
        runtimeIssuePresentations = entries.sorted { $0.featureID < $1.featureID }

        // Preserve the old single-token seam for callers that only know about
        // legacy string featureErrors. The view uses the owner-aware entries
        // above so Host presentation arguments are never flattened into text.
        let legacy = runtimeFeatureErrors.compactMap { featureID, message in
            message.isEmpty ? nil : "\(featureID): \(message)"
        }.sorted()
        runtimeIssueToken = legacy.isEmpty
            ? nil
            : presentation("hades2.status.runtimeInactive", arguments: [legacy.joined(separator: "; ")])
    }

    private func presentActionReceipt(_ receipt: Hades2ActionReceipt) {
        guard receipt != presentedActionReceipt else { return }
        presentedActionReceipt = receipt

        guard let command = Hades2Command(rawValue: receipt.command) else { return }
        // The receipt title stays a token so the notice/error text below is
        // resolved once, by the Host, against the live language.
        let title: TrainerTextToken
        switch command {
        case .openSellTraits: title = presentation("hades2.spawn.purgingPool")
        case .openSpecialChoice: title = presentation("hades2.spawn.rewardChoice")
        case .generateGathering: title = presentation("hades2.gathering.generate")
        case .setTraitLevel: title = presentation("hades2.receipt.traitLevelAction")
        case .setTraitRarity: title = presentation("hades2.receipt.traitRarityAction")
        case .setTraitRemainingUses: title = presentation("hades2.receipt.traitDurationAction")
        case .expireTrait: title = presentation("hades2.receipt.traitExpiryAction")
        case .removeTrait: title = presentation("hades2.receipt.traitRemoveAction")
        default: return
        }

        // The session may next publish a generic success/error envelope for the
        // same reply. This specific receipt owns the feedback meaning once.
        receiptPresentedDuringReply = true

        switch receipt.outcome {
        case .accepted:
            noticeToken = presentation("hades2.receipt.accepted", arguments: [title.key])
        case .opened:
            noticeToken = presentation("hades2.receipt.opened", arguments: [title.key])
        case .failed:
            noticeToken = nil
            if command == .generateGathering, let error = receipt.error, error.hasPrefix("hades2.gathering.unavailable.") {
                errorToken = presentation(error)
            } else { errorToken = presentation("hades2.receipt.failed", arguments: [title.key]) }
        case .outcomeUnknown:
            noticeToken = nil
            errorToken = presentation(command == .generateGathering ? "hades2.receipt.rerollOutcomeUnknown" : "hades2.receipt.outcomeUnknown", arguments: [title.key])
        case .completed:
            noticeToken = presentation("hades2.receipt.completed", arguments: [title.key])
        }
    }

    private func applyBackendStatus(_ status: TrainerBackendStatus) {
        let previous = backendStatus
        if status.busy { receiptPresentedDuringReply = false }
        let hasReceiptFeedback = receiptPresentedDuringReply
        if !status.busy { receiptPresentedDuringReply = false }
        backendStatus = status
        if !hasReceiptFeedback {
            if !status.error.isEmpty,
               status.error != previous.error || status.errorArguments != previous.errorArguments {
                errorToken = nil
                presentFeedback(backendErrorText, tone: .warning)
            } else if !status.notice.isEmpty, status.notice != previous.notice {
                noticeToken = nil
                presentFeedback(TrainerTextToken(key: status.notice), tone: .information)
            }
        }
    }

    private func presentFeedback(_ text: TrainerTextToken, tone: TrainerFeedbackTone) {
        guard !text.key.isEmpty else { return }
        feedbackNotice = TrainerFeedbackNotice(text: text, tone: tone)
    }

    /// Consume only the transient presentation event. Errors, receipts and
    /// recovery instructions retain their existing model/session ownership.
    func dismissFeedback(_ id: UUID) {
        guard feedbackNotice?.id == id else { return }
        feedbackNotice = nil
    }

    private func applyStat(_ snapshot: Hades2StatSnapshot?, value: inout Double?, locked: inout Bool) {
        guard let snapshot else { return }
        value = snapshot.value
        locked = snapshot.locked
    }

    private func send(
        _ request: Hades2Request,
        title: String,
        titleArguments: [String] = [],
        coalesceKey: String? = nil,
        announceSuccess: Bool = true,
        completion: ((Bool) -> Void)? = nil
    ) {
        api.request(
            request,
            operation: title,
            operationArguments: titleArguments,
            coalesceKey: coalesceKey,
            announceSuccess: announceSuccess,
            // Session has now applied the payload and any generic envelope.
            // Even a receipt with no generic publication ends its suppression
            // here, so a later transport/recovery failure is a new event.
            reply: { [weak self] _ in self?.receiptPresentedDuringReply = false },
            completion: completion
        )
    }

    /// The model never embeds localized copy. Notices and errors carry a token
    /// that the Host resolves against the live language, so switching language
    /// re-renders them without re-issuing any work.
    private func presentation(_ key: String, arguments: [String] = []) -> TrainerTextToken {
        TrainerTextToken(key: key, arguments: arguments)
    }

    private func invalidatePendingMutations() {
        mutationScheduler.invalidateAll()
        editGeneration &+= 1
    }

    private func flushPendingMutations() {
        mutationScheduler.flushAll()
    }

    private func sendBarrier(
        _ request: Hades2Request,
        title: String,
        titleArguments: [String] = [],
        announceSuccess: Bool = true,
        completion: ((Bool) -> Void)? = nil
    ) {
        invalidatePendingMutations()
        send(request, title: title, titleArguments: titleArguments, announceSuccess: announceSuccess, completion: completion)
    }

    private func desiredFeatureEnabled(_ key: Hades2FeatureKey) -> Bool {
        self[keyPath: key.modelKeyPath]
    }

    private func beginFeatureActivationGrace(_ key: Hades2FeatureKey, duration: TimeInterval = 0.9) {
        activationGraceWorkItems[key]?.cancel()
        activationGraceFeatures.insert(key)
        let work = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            self.activationGraceWorkItems[key] = nil
            self.activationGraceFeatures.remove(key)
        }
        activationGraceWorkItems[key] = work
        DispatchQueue.main.asyncAfter(deadline: .now() + duration, execute: work)
    }

    private func clearFeatureActivationGrace(_ key: Hades2FeatureKey) {
        activationGraceWorkItems[key]?.cancel()
        activationGraceWorkItems[key] = nil
        activationGraceFeatures.remove(key)
    }

    // Do not poll in-process Lua state automatically. Every status request crosses
    // the LLDB/Lua boundary and briefly stops the game; periodic polling therefore
    // creates visible frame-time spikes. Runtime state is refreshed by user-driven
    // requests (and the explicit Refresh action) instead.

    func enqueueMutation(
        key: String,
        request: Hades2Request,
        title: String,
        titleArguments: [String] = [],
        delay: TimeInterval = 0.35,
        completion: ((Bool) -> Void)? = nil
    ) {
        mutationScheduler.schedule(key: key, delay: delay) { [weak self] in
            self?.send(
                request,
                title: title,
                titleArguments: titleArguments,
                coalesceKey: key,
                announceSuccess: false,
                completion: completion
            )
        }
    }

    func feature(_ key: Hades2FeatureKey, value: Bool, completion: ((Bool) -> Void)? = nil) {
        guard canEditDesired else { return }
        if value { beginFeatureActivationGrace(key) }
        else { clearFeatureActivationGrace(key) }
        // Desired state belongs to the trainer profile, not to the debugger
        // connection. Keep the UI intent editable while detached and let the
        // backend apply/replay it whenever a valid Lua scene becomes available.
        self[keyPath: key.modelKeyPath] = value
        send(.setDesired(feature: key.rawValue, value: value), title: "hades2.op.updateFeature", completion: completion)
    }

    func setGameSpeed(_ text: String) {
        guard let value = Double(text), value.isFinite else { return }
        setGameSpeedValue(value)
    }

    private func setGameSpeedValue(_ rawValue: Double, completion: ((Bool) -> Void)? = nil) {
        guard canEditDesired else { return }
        let value = (rawValue * 10).rounded() / 10
        guard Self.gameSpeedInputRange.contains(value), abs(gameSpeed - value) >= 0.0001 else { return }
        gameSpeed = value
        send(
            .setDesired(feature: "gameSpeed", value: value),
            title: "hades2.op.updateGameSpeed",
            coalesceKey: "feature.gameSpeed",
            announceSuccess: false,
            completion: completion
        )
    }

    private func amountValue(_ text: String) -> Int? {
        guard let value = Int(text), (0...999_999).contains(value) else { return nil }
        return value
    }

    func setVital(_ vital: String, field: String, text: String) {
        guard canSetVitals, let value = Double(text), value.isFinite, (0...999_999).contains(value) else { return }
        if vital == "health" && value < 1 { return }
        let current: Double?
        switch (vital, field) {
        case ("health", "current"): current = health
        case ("health", "max"): current = maxHealth
        case ("mana", "current"): current = mana
        case ("mana", "max"): current = maxMana
        case ("armor", "current"): current = armor
        default: return
        }
        if let current = current, abs(current - value) < 0.0001 { return }
        let titleKey = vital == "health" ? "hades2.vital.health" : (vital == "mana" ? "hades2.vital.mana" : "hades2.vital.armor")
        enqueueMutation(
            key: "vital.\(vital).\(field)",
            request: .setVital(vital: vital, field: field, value: value),
            title: "hades2.op.updateVital",
            titleArguments: [titleKey]
        )
    }

    func lockVital(_ vital: String, locked: Bool) {
        guard canSetVitals, ["health", "mana", "armor"].contains(vital) else { return }
        send(.lockVital(vital: vital, locked: locked), title: locked ? "hades2.op.lockVital" : "hades2.op.unlockVital")
    }

    func setResource(_ resource: String, amount: String) {
        guard canSetResource, let count = amountValue(amount) else { return }
        let current: Double?
        if resource == "Money" { current = money }
        else { current = resources.first(where: { $0.id == resource })?.count }
        guard resource == "Money" || resources.contains(where: { $0.id == resource }) else { return }
        if let current = current, Int(current.rounded()) == count { return }
        enqueueMutation(key: "resource.\(resource)", request: .setResource(resource: resource, amount: count), title: "hades2.op.updateResource")
    }

    func lockResource(_ resource: String, locked: Bool) {
        guard canSetResource else { return }
        guard resource == "Money" || resources.contains(where: { $0.id == resource }) else { return }
        send(.lockResource(resource: resource, locked: locked), title: locked ? "hades2.op.lockResource" : "hades2.op.unlockResource")
    }

    func setRerolls(_ amount: String) {
        guard canSetResource, let count = amountValue(amount) else { return }
        if let current = rerolls, Int(current.rounded()) == count { return }
        enqueueMutation(key: "rerolls", request: .setRerolls(amount: count), title: "hades2.op.updateRerolls")
    }

    func lockRerolls(_ locked: Bool) {
        guard canSetResource else { return }
        send(.lockRerolls(locked: locked), title: locked ? "hades2.op.lockRerolls" : "hades2.op.unlockRerolls")
    }

    func validProbabilityPercentage(_ text: String) -> Bool {
        guard let value = Double(text), value.isFinite else { return false }
        return (0...100).contains(value)
    }

    func setGatheringProbability(_ family: Hades2GatheringFamily, custom: Bool, text: String) {
        guard canEditDesired, !custom || validProbabilityPercentage(text) else { return }
        let value = custom ? Double(text) : nil
        guard gatheringProbabilities[family] != value else { return }
        enqueueMutation(key: "gathering.\(family.rawValue)", request: .setGathering(family: family, probability: value), title: "hades2.gathering.apply")
    }

    func setChaosGateProbability(custom: Bool, text: String) {
        guard canEditDesired, !custom || validProbabilityPercentage(text) else { return }
        let value = custom ? Double(text) : nil
        guard chaosGateProbability != value else { return }
        enqueueMutation(key: "chaosGateProbability", request: .setChaosGate(probability: value), title: "hades2.chaosGate.apply")
    }

    func canGenerateGathering(_ family: Hades2GatheringFamily) -> Bool {
        canOpenNativeBoonScreen && protocolCompatible && gatheringTargets[family]?.available == true
    }

    func generateGathering(_ family: Hades2GatheringFamily) {
        guard canGenerateGathering(family), let token = gatheringTargets[family]?.scopeToken else { return }
        send(.generateGathering(family: family, scopeToken: token), title: "hades2.gathering.generate", announceSuccess: false)
    }

    func setStat(_ stat: String, text: String, locked: Bool) {
        guard canSetStats, let rule = Self.statRules[stat], statSupport[stat] != false, statAvailable[stat] != false else { return }
        if !locked {
            mutationScheduler.cancel(key: "stat.\(stat)")
            send(.setStat(stat: stat, locked: false, value: nil), title: "hades2.op.unlockStat")
            return
        }
        guard let value = Double(text), value.isFinite, (rule.min...rule.max).contains(value) else { return }
        if rule.integer && value.rounded() != value { return }
        let encodedValue: Any = rule.integer ? Int(value) : value
        enqueueMutation(key: "stat.\(stat)", request: .setStat(stat: stat, locked: true, value: encodedValue), title: "hades2.op.updateStatLock")
    }

    func setElement(_ element: String, text: String) {
        guard canSetElements, let amount = amountValue(text), elements.contains(where: { $0.id == element }) else { return }
        if let current = elements.first(where: { $0.id == element })?.count, Int(current.rounded()) == amount { return }
        enqueueMutation(key: "element.\(element)", request: .setElement(element: element, amount: amount), title: "hades2.op.updateElement")
    }

    func lockElement(_ element: String, locked: Bool) {
        guard canSetElements, elements.contains(where: { $0.id == element }) else { return }
        send(.lockElement(element: element, locked: locked), title: locked ? "hades2.op.lockElement" : "hades2.op.unlockElement")
    }

    func setBoonRarity(target: String, multiplier: String, forceLegendary: Bool, forceDuo: Bool, completion: ((Bool) -> Void)? = nil) {
        guard canEditDesired, ["Common", "Rare", "Epic", "Heroic"].contains(target),
              let value = Double(multiplier), value.isFinite, (0...1000).contains(value) else { return }
        boonRarityTarget = target; boonRarityMultiplier = value; boonForceLegendary = forceLegendary; boonForceDuo = forceDuo
        enqueueMutation(
            key: "boon.rarity",
            request: .setBoonRarity(target: target, multiplier: value, forceLegendary: forceLegendary, forceDuo: forceDuo),
            title: "hades2.op.updateBoonRarity",
            completion: completion
        )
    }


    func setNextRoomReward(_ reward: String?) {
        guard canEditDesired else { return }
        nextRoomReward = reward
        send(.setNextRoomReward(reward), title: reward == nil ? "hades2.op.clearNextRoom" : "hades2.op.setNextRoom")
    }

    private func shortcutPayload() -> [String: Any] { shortcutStore.payload() }

    func saveProfile(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        flushPendingMutations()
        send(.saveProfile(name: trimmed, shortcuts: shortcutPayload()), title: "hades2.op.saveProfile")
    }

    func loadProfile(_ name: String) {
        guard !name.isEmpty else { return }
        sendBarrier(.loadProfile(name), title: "hades2.op.loadProfile")
    }

    func deleteProfile(_ name: String) {
        guard !name.isEmpty else { return }
        send(.deleteProfile(name), title: "hades2.op.deleteProfile")
    }

    func listProfiles() { send(.listProfiles, title: "hades2.op.listProfiles") }
    func runDiagnostics() { send(.diagnostics, title: "hades2.op.runDiagnostics") }
    func exportDiagnostics() { send(.exportDiagnostics, title: "hades2.op.exportDiagnostics") }

    func spawnBoon(_ loot: String) {
        guard canSpawnReward, boons.contains(where: { $0.id == loot }) else { return }
        send(.spawnReward(loot), title: "hades2.op.spawnReward")
    }

    func acquireExactBoon(_ reward: String) {
        guard canSpawnReward, exactBoonOptions.contains(where: { $0.id == reward }) else { return }
        send(.spawnReward(reward), title: "hades2.op.acquireExactBoon")
    }

    func acquireChaosPair(blessingReward: String, curseReward: String) {
        guard canSpawnReward,
              let blessing = exactBoonOptions.first(where: {
                  $0.id == blessingReward && $0.acquisitionMode == "chaosBlessing"
              }),
              let curse = exactBoonOptions.first(where: {
                  $0.id == curseReward && $0.acquisitionMode == "chaosCurse"
              }),
              !blessing.targetID.isEmpty,
              !curse.targetID.isEmpty else { return }
        send(
            .acquireChaosPair(blessing: blessing.targetID, curse: curse.targetID),
            title: "hades2.op.acquireExactBoon"
        )
    }

    func openSellTraits() {
        guard canOpenNativeBoonScreen else { return }
        send(.openSellTraits, title: "hades2.receipt.openPurgingPool", announceSuccess: false)
    }

    func setTraitLevel(_ trait: CurrentRunTrait, targetLevel: String) {
        guard canOpenNativeBoonScreen, trait.canIncreaseLevel else { return }
        let trimmed = targetLevel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let level = Int(trimmed), level > trait.level, level <= 999_999 else { return }
        send(
            .setTraitLevel(trait, targetLevel: level),
            title: "hades2.receipt.traitLevelAction",
            titleArguments: [trait.displayName],
            announceSuccess: false
        )
    }

    func setTraitRarity(_ trait: CurrentRunTrait, rarity: String) {
        guard canOpenNativeBoonScreen, trait.canSetRarity,
              trait.availableRarities.contains(rarity), rarity != trait.rarity else { return }
        send(
            .setTraitRarity(trait, rarity: rarity),
            title: "hades2.receipt.traitRarityAction",
            titleArguments: [trait.displayName],
            announceSuccess: false
        )
    }

    func setTraitRemainingUses(_ trait: CurrentRunTrait, targetRemainingUses: String) {
        guard canOpenNativeBoonScreen, trait.canSetRemainingUses else { return }
        let trimmed = targetRemainingUses.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let uses = Int(trimmed), (1...999_999).contains(uses),
              trait.remainingUses != Double(uses) else { return }
        send(
            .setTraitRemainingUses(trait, targetRemainingUses: uses),
            title: "hades2.receipt.traitDurationAction",
            titleArguments: [trait.displayName],
            announceSuccess: false
        )
    }

    func expireTrait(_ trait: CurrentRunTrait) {
        guard canOpenNativeBoonScreen, trait.canExpire else { return }
        send(
            .expireTrait(trait),
            title: "hades2.receipt.traitExpiryAction",
            titleArguments: [trait.displayName],
            announceSuccess: false
        )
    }

    /// Remove the observed live target through the capability selected by the
    /// Hades runtime. Native sell removal remains name-level/all-matching;
    /// bounded force removal is single-instance and only exists for an audited
    /// direct strategy.
    func removeTrait(_ trait: CurrentRunTrait) {
        guard canOpenNativeBoonScreen, trait.canRemove else { return }
        send(
            .removeTrait(trait),
            title: "hades2.receipt.traitRemoveAction",
            announceSuccess: false
        )
    }

    func advanceTraitLifecycle(_ trait: CurrentRunTrait) {
        guard canOpenNativeBoonScreen, trait.canAdvanceLifecycle else { return }
        send(
            .advanceTraitLifecycle(trait),
            title: "hades2.receipt.traitLifecycleAction",
            titleArguments: [trait.displayName],
            announceSuccess: false
        )
    }

    func performSpecialReward(_ reward: String) {
        guard let option = specialRewardOptions.first(where: { $0.id == reward }) else { return }
        if option.kind == "native_choice" {
            guard canOpenNativeBoonScreen, !option.sourceId.isEmpty else { return }
            send(
                .openSpecialChoice(source: option.sourceId),
                title: "hades2.receipt.openChoice",
                titleArguments: [option.nativeChoiceTitle.isEmpty
                    // A backend-supplied native title is already text; an
                    // unknown source falls back to the module's own key.
                    ? "hades2.spawn.rewardChoice"
                    : option.nativeChoiceTitle],
                announceSuccess: false
            )
        } else {
            spawnBoon(option.id)
        }
    }

    func setMultiplier(_ key: String, text: String) {
        guard canEditDesired, let value = Double(text), value.isFinite, (1...100).contains(value) else { return }
        let current: Double
        switch key {
        case "damageMultiplier": current = damageMultiplier
        case "moneyMultiplier": current = moneyMultiplier
        case "resourceMultiplier": current = resourceMultiplier
        default: return
        }
        if abs(current - value) < 0.0001 { return }
        switch key {
        case "damageMultiplier": damageMultiplier = value
        case "moneyMultiplier": moneyMultiplier = value
        case "resourceMultiplier": resourceMultiplier = value
        default: break
        }
        enqueueMutation(key: "feature.\(key)", request: .setDesired(feature: key, value: value), title: "hades2.op.updateMultiplier")
    }

    func setCounter(_ counter: String, text: String) {
        guard canSetVitals, let value = Double(text), value.isFinite, (0...999_999).contains(value) else { return }
        if counter == "spellCharge", let current = spellCharge, abs(current - value) < 0.0001 { return }
        enqueueMutation(key: "counter.\(counter)", request: .setCounter(counter: counter, value: value), title: "hades2.op.updateCounter")
    }

    private func applyProfileShortcuts(_ values: [String: Any]) {
        shortcutStore.applyProfile(values)
        installHotkeys()
    }

    func shortcutChord(_ action: ShortcutAction) -> HotkeyChord { shortcutStore.chord(action) }
    func shortcutText(_ action: ShortcutAction) -> String { shortcutStore.chord(action).displayText }

    func setShortcut(action: ShortcutAction, chord: HotkeyChord) {
        if let conflict = shortcutStore.set(action, chord: chord) {
            shortcutIssue = .conflict(chordText: chord.displayText, action: conflict)
        } else {
            clearShortcutIssue()
            installHotkeys()
        }
    }

    func clearShortcutIssue() {
        shortcutIssue = nil
    }

    func setUnrecognizedShortcutIssue() {
        shortcutIssue = .unrecognized
    }

    private func featureHotkeyFeedback(_ key: Hades2FeatureKey, targetEnabled: Bool) -> TrainerHotkeyFeedback? {
        guard targetEnabled else { return .disabled }
        if activeFeatures[key.rawValue] == true { return .enabled }
        if dormantFeatures[key.rawValue] == true || !connected || status != "ready" { return .deferred }
        return nil
    }

    private func performFeatureShortcut(_ key: Hades2FeatureKey) {
        let targetEnabled = !desiredFeatureEnabled(key)
        feature(key, value: targetEnabled) { [weak self] success in
            guard let self, success else { return }
            if let feedback = self.featureHotkeyFeedback(key, targetEnabled: targetEnabled) {
                TrainerHotkeyFeedbackPlayer.play(feedback)
            }
        }
    }

    private func performBoonForceShortcutFeedback(targetEnabled: Bool, success: Bool) {
        guard success else { return }
        let feedback: TrainerHotkeyFeedback
        if !targetEnabled {
            feedback = .disabled
        } else if activeFeatures[Hades2FeatureKey.boonRarityEnabled.rawValue] == true {
            feedback = .enabled
        } else {
            feedback = .deferred
        }
        TrainerHotkeyFeedbackPlayer.play(feedback)
    }

    private func performShortcut(_ action: ShortcutAction) {
        if action == .disableAll {
            guard connected && !busy && !exiting else { return }
            sendBarrier(.disableAll, title: "host.disableAll") { success in
                if success { TrainerHotkeyFeedbackPlayer.play(.disabled) }
            }
            return
        }
        guard !busy && !exiting else { return }
        switch action {
        case .invincibility, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
             .infiniteAmmo, .damageEnabled, .autoMiniGames, .gardenQoL, .boonRarityEnabled,
             .forceEnableRerolls, .moneyMultiplierEnabled, .resourceMultiplierEnabled:
            guard canEditDesired, let key = action.featureKey else { return }
            performFeatureShortcut(key)
        case .forceLegendary:
            guard canEditDesired else { return }
            let targetEnabled = !boonForceLegendary
            setBoonRarity(
                target: boonRarityTarget,
                multiplier: String(boonRarityMultiplier),
                forceLegendary: targetEnabled,
                forceDuo: boonForceDuo
            ) { [weak self] success in
                self?.performBoonForceShortcutFeedback(targetEnabled: targetEnabled, success: success)
            }
        case .forceDuo:
            guard canEditDesired else { return }
            let targetEnabled = !boonForceDuo
            setBoonRarity(
                target: boonRarityTarget,
                multiplier: String(boonRarityMultiplier),
                forceLegendary: boonForceLegendary,
                forceDuo: targetEnabled
            ) { [weak self] success in
                self?.performBoonForceShortcutFeedback(targetEnabled: targetEnabled, success: success)
            }
        case .applyNextRoomReward:
            guard canEditDesired else { return }; setNextRoomReward(selectedNextRoomReward.isEmpty ? nil : selectedNextRoomReward)
        case .spawnOlympian:
            guard canSpawnReward, !selectedOlympianReward.isEmpty else { return }; spawnBoon(selectedOlympianReward)
        case .spawnPickup:
            guard canSpawnReward, !selectedPickupReward.isEmpty else { return }; spawnBoon(selectedPickupReward)
        case .spawnSpecial:
            guard !selectedSpecialReward.isEmpty else { return }; performSpecialReward(selectedSpecialReward)
        case .disableAll: break
        }
    }

    private func installHotkeys() {
        hotkeys = nil
        let instance = GlobalHotkeys { [weak self] actionID in
            guard let self, let action = ShortcutAction(rawValue: actionID) else { return }
            self.performShortcut(action)
        }
        let bindings = ShortcutAction.uiOrder.map { action in
            HotkeyBinding(actionID: action.rawValue, chord: shortcutChord(action))
        }
        if let failure = instance.register(bindings) {
            shortcutIssue = .registration(failure)
        } else {
            clearShortcutIssue()
        }
        hotkeys = instance
    }

    func openLog() {
        // The log is a diagnostic surface and stays language-neutral, so it
        // records the stable operation key rather than resolved wording.
        appendLog(presentation("hades2.op.logCreated").key)
        logSink.flush()
        NSWorkspace.shared.open(logSink.url)
    }

    private func appendLog(_ line: String) {
        logSink.append(line)
    }

    private func detachForTermination(completion: @escaping (Bool) -> Void) {
        guard connected else {
            finishExit(completion: completion)
            return
        }
        sendBarrier(.disconnect, title: "hades2.op.exitDetach", announceSuccess: false) { [weak self] _ in
            guard let self else { completion(true); return }
            self.finishExit(completion: completion)
        }
    }

    func prepareForTermination(completion: @escaping (Bool) -> Void) {
        guard !exiting else { completion(true); return }
        exiting = true
        invalidatePendingMutations()
        guard backendSession.isRunning else {
            finishExit(completion: completion)
            return
        }

        // Every verified connection receives best-effort resident teardown.
        // The resident owns its hooks; a Host feature mirror cannot determine
        // whether cleanup is needed. Durable reset remains persistence-only.
        sendBarrier(.resetDesired, title: "hades2.op.exitReset", announceSuccess: false) { [weak self] _ in
            guard let self else { completion(true); return }
            guard self.connected else {
                self.detachForTermination(completion: completion)
                return
            }
            self.sendBarrier(.disableAll, title: "hades2.op.exitCleanup", announceSuccess: false) { [weak self] _ in
                guard let self else { completion(true); return }
                self.detachForTermination(completion: completion)
            }
        }
    }

    private func finishExit(completion: @escaping (Bool) -> Void) {
        invalidatePendingMutations()
        shuttingDown = true
        backendSession.stop(suppressTerminationError: true)
        completion(true)
    }
}

private extension Hades2FeatureKey {
    var modelKeyPath: ReferenceWritableKeyPath<Hades2TrainerModel, Bool> {
        switch self {
        case .invincibility: return \.invincibility
        case .infiniteHealth: return \.infiniteHealth
        case .infiniteMana: return \.infiniteMana
        case .damageEnabled: return \.damageEnabled
        case .instantCastCooldown: return \.instantCastCooldown
        case .hexAlwaysReady: return \.hexAlwaysReady
        case .infiniteAmmo: return \.infiniteAmmo
        case .autoMiniGames: return \.autoMiniGames
        case .gardenQoL: return \.gardenQoL
        case .boonRarityEnabled: return \.boonRarityEnabled
        case .forceEnableRerolls: return \.forceEnableRerolls
        case .moneyMultiplierEnabled: return \.moneyMultiplierEnabled
        case .resourceMultiplierEnabled: return \.resourceMultiplierEnabled
        }
    }
}
