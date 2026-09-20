import Foundation
import AppKit

final class Hades2TrainerModel: ObservableObject, TrainerHostModel {
    private static let expectedHostProtocolVersion = Hades2GameModule.descriptor.expectedHostProtocolVersion
    private static let expectedModuleProtocolVersion = Hades2GameModule.descriptor.expectedModuleProtocolVersion
    private struct StatRule {
        let min: Double
        let max: Double
        let integer: Bool
    }
    static let gameSpeedInputRange = 0.1...20.0
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
    @Published private(set) var backendStatus = TrainerBackendStatus()
    private let backendSession = TrainerBackendSession()
    private let logSink = TrainerLogSink()
    private lazy var api = Hades2API(session: backendSession)
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var backendProtocolVersion: Int? { backendStatus.backendProtocolVersion }
    var backendModuleProtocolVersion: Int? { backendStatus.backendModuleProtocolVersion }
    var protocolCompatible: Bool { backendStatus.protocolCompatible }
    var busy: Bool { backendStatus.busy }
    var operation: String { backendStatus.operation }
    var connectionDetailText: String { "版本 \(version)" + (pid.map { " · PID \($0)" } ?? "") }
    var hostActionsEnabled: Bool { !busy && !exiting && protocolCompatible }
    /// Save-management UI should remain usable while the staged-restore watcher
    /// performs its passive process scan. All actual save operations still own
    /// the normal busy state.
    var saveManagerBusy: Bool {
        busy && operation != "等待游戏退出并恢复存档"
    }
    var error: String {
        get { backendStatus.error }
        set { backendStatus.error = newValue }
    }
    var notice: String {
        get { backendStatus.notice }
        set { backendStatus.notice = newValue }
    }
    @Published var pid: Int?
    @Published var version = "等待检测"
    @Published var status = "disconnected"
    @Published var scene = "unknown"
    @Published var capabilities: [String: Bool] = [:]
    @Published var activeFeatures: [String: Bool] = [:]
    @Published var dormantFeatures: [String: Bool] = [:]
    @Published var featureSupport: [String: Bool] = [:]
    @Published var godMode = false
    @Published var infiniteHealth = false
    @Published var infiniteMana = false
    @Published var instantCastCooldown = false
    @Published var hexAlwaysReady = false
    @Published var infiniteAmmo = false
    @Published var autoMiniGames = false
    @Published var gardenQoL = false
    @Published var boonRarityEnabled = false
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
    @Published var boons: [BoonOption] = []
    @Published var selectedOlympianReward = ""
    @Published var selectedPickupReward = ""
    @Published var selectedSpecialReward = ""
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
    @Published var elements: [ElementCount] = []
    @Published var backups: [SaveBackup] = []
    @Published var profiles: [TrainerProfile] = []
    @Published var diagnostics: [DiagnosticCheck] = []
    @Published var diagnosticsPassed = 0
    @Published var diagnosticsTotal = 0
    @Published var pendingRestoreID: String?
    @Published var resources: [MaterialResource] = []
    @Published private var shortcutStore = Hades2ShortcutStore()
    @Published var shortcutError = ""
    @Published var exiting = false
    @Published var shortcutSettingsPresented = false
    @Published var saveManagerPresented = false

    private let mutationScheduler = Hades2MutationScheduler()
    private lazy var runLogWatcher = Hades2RunLogWatcher { [weak self] event in
        self?.handleRunLogEvent(event)
    }
    private var pendingRunReadySignal = false
    private var activationGraceWorkItems: [String: DispatchWorkItem] = [:]
    @Published private var activationGraceFeatures: Set<String> = []
    private var hotkeys: GlobalHotkeys?
    private var pendingRestoreTimer: Timer?
    private var shuttingDown = false
    var canSetFeature: Bool { connected && capabilities["setFeature"] == true && !exiting }
    var canEditDesired: Bool { backendAvailable && !exiting }
    var canSetVitals: Bool { connected && capabilities["setVitals"] == true && !exiting }
    var canSetResource: Bool { connected && capabilities["setResource"] == true && !exiting }
    var canSpawnReward: Bool { connected && capabilities["spawnReward"] == true && !exiting }
    var canOpenNativeBoonScreen: Bool { connected && status == "ready" && scene == "run" && !busy && !exiting }
    var specialRewardOptions: [BoonOption] {
        let specials = boons.filter { $0.group == "special" }
        var seenSources = Set<String>()
        var nativeActions: [BoonOption] = []
        for option in specials where option.nativeChoice && !option.sourceId.isEmpty {
            guard seenSources.insert(option.sourceId).inserted else { continue }
            nativeActions.append(BoonOption(
                id: "native-choice:\(option.sourceId)",
                name: "\(option.sectionTitle)的祝福",
                englishName: "\(option.sourceId) Boon",
                category: option.category,
                kind: "native_choice",
                group: "special",
                sectionTitle: option.sectionTitle,
                sourceId: option.sourceId,
                nativeChoice: true,
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
    func supportsFeature(_ key: String) -> Bool { featureSupport[key] ?? true }
    func isFeatureActivationPending(_ key: String) -> Bool { activationGraceFeatures.contains(key) }
    var ready: Bool { canSetFeature }
    var statusTitle: String {
        if exiting { return "正在清理并退出" }
        switch status {
        case "ready":
            if scene == "crossroads" { return "已连接 · 三岔路口" }
            if scene == "run" { return "已连接 · 局内可用" }
            return "已连接 · 可操作"
        case "waiting":
            if scene == "loading" { return "已连接 · 场景切换中" }
            if scene == "main_menu" { return "已连接 · 主菜单" }
            return "已连接 · 等待可操作场景"
        case "not_running": return "游戏尚未运行"
        case "incompatible": return "版本未验证 · 可尝试连接"
        case "restart_required": return "需要重启游戏"
        case "backend_stopped": return "后端已停止"
        case "disconnected": return "尚未连接"
        default: return status
        }
    }

    init() {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.runLogWatcher.start()
            self.installHotkeys()
            self.startBackend()
        }
    }

    func toggleConnectionFromHost() { toggleConnection() }

    func refreshFromHost() {
        send(connected ? .status : .scan, title: "刷新状态")
    }

    func hostDidBecomeActive() {
        guard connected,
              status == "waiting",
              backendAvailable,
              !busy,
              !exiting else { return }
        send(.status, title: "检测可操作场景", announceSuccess: false)
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
                desiredFeatureKeys.filter { desiredFeatureEnabled($0) }.map { ($0, true) }
            )
            capabilities = capabilities.mapValues { _ in false }
            capabilities["hotBackup"] = true
            capabilities["diagnostics"] = true
            statAvailable = statAvailable.mapValues { _ in false }
            activationGraceWorkItems.values.forEach { $0.cancel() }
            activationGraceWorkItems = [:]
            activationGraceFeatures = []
        case .runtimeReady:
            guard connected else { return }
            pendingRunReadySignal = true
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
        send(.status, title: "检测可操作场景", announceSuccess: false) { [weak self] _ in
            self?.consumeRunLogReadySignalIfPossible()
        }
    }

    func toggleConnection() {
        if connected {
            sendBarrier(.disconnect, title: "断开调试连接（保留修改）")
        } else {
            runLogWatcher.start()
            send(.connect, title: "连接游戏") { [weak self] _ in
                guard let self else { return }
                self.runLogWatcher.start()
                self.consumeRunLogReadySignalIfPossible()
            }
        }
    }

    func disableAllFromHost() { disableAll() }
    func restartBackendFromHost() { restartBackend() }

    func launchGame() { send(.launch, title: "启动游戏") }
    func refreshBackups() { send(.listBackups, title: "读取备份列表") }
    func prepareDebugging() { send(.prepare, title: "准备调试签名") }
    func restoreOriginalSignature() { send(.restore, title: "恢复原始签名") }
    func disableAll() { sendBarrier(.disableAll, title: "全部关闭") }

    func restartBackend() {
        guard !exiting else { return }
        invalidatePendingMutations()
        error = ""
        notice = ""
        backendSession.restart()
    }

    private func startBackend() {
        guard !backendSession.isStarted else { return }
        do {
            try backendSession.start(
                descriptor: Hades2GameModule.descriptor,
                applyPayload: { [weak self] payload in self?.apply(payload) },
                resetGameState: { [weak self] in self?.resetAfterBackendTermination() },
                log: { [weak self] line in self?.appendLog(line) },
                onStatusChange: { [weak self] status in
                    self?.backendStatus = status
                    if !status.busy {
                        self?.consumeRunLogReadySignalIfPossible()
                    }
                }
            )
            send(.scan, title: "检测游戏")
        } catch {
            status = "backend_stopped"
            backendSession.markUnavailable("无法启动后端：\(error.localizedDescription)")
        }
    }

    private func resetAfterBackendTermination() {
        connected = false
        scene = "unknown"
        capabilities = [:]
        activeFeatures = [:]
        dormantFeatures = [:]
        featureSupport = [:]
        statAvailable = [:]
        activationGraceWorkItems.values.forEach { $0.cancel() }
        activationGraceWorkItems = [:]
        activationGraceFeatures = []
        invalidatePendingMutations()
        pendingRestoreTimer?.invalidate()
        pendingRestoreTimer = nil
        pendingRestoreID = nil
        pendingRunReadySignal = false
        pid = nil
        runtimeIssue = ""
        health = nil
        maxHealth = nil
        mana = nil
        maxMana = nil
        armor = nil
        spellCharge = nil
        spellChargeCost = nil
        money = nil
        rerolls = nil
        resources = []
        boons = []
        status = "backend_stopped"
    }

    private func apply(_ payload: [String: Any]) {
        let patch = Hades2StatePatch(payload)
        let wasConnected = connected
        let oldPID = pid
        let desiredBeforeApply = Dictionary(uniqueKeysWithValues: desiredFeatureKeys.map { ($0, desiredFeatureEnabled($0)) })

        if let value = patch.connected, wasConnected && !value { invalidatePendingMutations() }
        if patch.pid.isPresent, oldPID != patch.pid.value { invalidatePendingMutations() }
        if let value = patch.connected { connected = value }
        if patch.pid.isPresent { pid = patch.pid.value }
        if let value = patch.version { version = value }
        if let value = patch.status { status = value }
        if let value = patch.scene { scene = value }
        if let value = patch.capabilities { capabilities = value }
        if let value = patch.activeFeatures { activeFeatures = value }
        if let value = patch.dormantFeatures { dormantFeatures = value }
        if let value = patch.featureSupport { featureSupport = value }
        if let values = patch.featureErrors {
            let issues = values.compactMap { key, message in message.isEmpty ? nil : "\(key): \(message)" }.sorted()
            runtimeIssue = issues.isEmpty ? "" : "运行时未激活：" + issues.joined(separator: "；")
        } else {
            runtimeIssue = ""
        }

        if let value = patch.godMode { godMode = value }
        if let value = patch.infiniteHealth { infiniteHealth = value }
        if let value = patch.infiniteMana { infiniteMana = value }
        if let value = patch.instantCastCooldown { instantCastCooldown = value }
        if let value = patch.hexAlwaysReady { hexAlwaysReady = value }
        if let value = patch.infiniteAmmo { infiniteAmmo = value }
        if let value = patch.autoMiniGames { autoMiniGames = value }
        if let value = patch.gardenQoL { gardenQoL = value }
        if let value = patch.boonRarityEnabled { boonRarityEnabled = value }
        if let value = patch.damageEnabled { damageEnabled = value }
        if let value = patch.gameSpeed { gameSpeed = value }
        if let value = patch.damageMultiplier { damageMultiplier = value }
        if let value = patch.moneyLocked { moneyLocked = value }
        if let value = patch.moneyMultiplier { moneyMultiplier = value }
        if let value = patch.moneyMultiplierEnabled { moneyMultiplierEnabled = value }
        if let value = patch.resourceMultiplier { resourceMultiplier = value }
        if let value = patch.resourceMultiplierEnabled { resourceMultiplierEnabled = value }
        if let rarity = patch.boonRarity {
            if let value = rarity.target { boonRarityTarget = value }
            if let value = rarity.multiplier { boonRarityMultiplier = value }
            if let value = rarity.forceLegendary { boonForceLegendary = value }
            if let value = rarity.forceDuo { boonForceDuo = value }
        }
        if patch.nextRoomReward.isPresent { nextRoomReward = patch.nextRoomReward.value }
        if patch.rerolls.isPresent { rerolls = patch.rerolls.value }
        if let value = patch.rerollsLocked { rerollsLocked = value }
        if let value = patch.warningText { warning = value }
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
        if let value = patch.backups { backups = value }
        if let value = patch.profiles { profiles = value }
        if let value = patch.diagnostics {
            diagnostics = value
            diagnosticsPassed = patch.diagnosticsPassed ?? value.filter(\.ok).count
            diagnosticsTotal = patch.diagnosticsTotal ?? value.count
        }

        for key in activeFeatures.keys where activeFeatures[key] == true { clearFeatureActivationGrace(key) }
        for key in desiredFeatureKeys where desiredFeatureEnabled(key)
            && desiredBeforeApply[key] != true && activeFeatures[key] != true && dormantFeatures[key] != true {
            beginFeatureActivationGrace(key)
        }
        if !wasConnected && connected {
            for key in desiredFeatureKeys where desiredFeatureEnabled(key)
                && activeFeatures[key] != true && dormantFeatures[key] != true {
                beginFeatureActivationGrace(key)
            }
        }

        if patch.pendingRestoreID.isPresent {
            pendingRestoreID = patch.pendingRestoreID.value
            updatePendingRestorePolling()
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

    private func applyStat(_ snapshot: Hades2StatSnapshot?, value: inout Double?, locked: inout Bool) {
        guard let snapshot else { return }
        value = snapshot.value
        locked = snapshot.locked
    }

    private func send(_ request: Hades2Request, title: String, coalesceKey: String? = nil, announceSuccess: Bool = true, completion: ((Bool) -> Void)? = nil) {
        api.request(request, operation: title, coalesceKey: coalesceKey, announceSuccess: announceSuccess, completion: completion)
    }

    private func invalidatePendingMutations() {
        mutationScheduler.invalidateAll()
    }

    private func flushPendingMutations() {
        mutationScheduler.flushAll()
    }

    private func sendBarrier(_ request: Hades2Request, title: String, announceSuccess: Bool = true, completion: ((Bool) -> Void)? = nil) {
        invalidatePendingMutations()
        send(request, title: title, announceSuccess: announceSuccess, completion: completion)
    }

    private let desiredFeatureKeys: [String] = [
        "godMode", "infiniteHealth", "infiniteMana", "damageEnabled", "instantCastCooldown",
        "hexAlwaysReady", "infiniteAmmo", "autoMiniGames", "gardenQoL", "boonRarityEnabled",
        "moneyMultiplierEnabled", "resourceMultiplierEnabled"
    ]

    private func desiredFeatureEnabled(_ key: String) -> Bool {
        switch key {
        case "godMode": return godMode
        case "infiniteHealth": return infiniteHealth
        case "infiniteMana": return infiniteMana
        case "damageEnabled": return damageEnabled
        case "instantCastCooldown": return instantCastCooldown
        case "hexAlwaysReady": return hexAlwaysReady
        case "infiniteAmmo": return infiniteAmmo
        case "autoMiniGames": return autoMiniGames
        case "gardenQoL": return gardenQoL
        case "boonRarityEnabled": return boonRarityEnabled
        case "moneyMultiplierEnabled": return moneyMultiplierEnabled
        case "resourceMultiplierEnabled": return resourceMultiplierEnabled
        default: return false
        }
    }

    private func beginFeatureActivationGrace(_ key: String, duration: TimeInterval = 0.9) {
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

    private func clearFeatureActivationGrace(_ key: String) {
        activationGraceWorkItems[key]?.cancel()
        activationGraceWorkItems[key] = nil
        activationGraceFeatures.remove(key)
    }

    // Do not poll in-process Lua state automatically. Every status request crosses
    // the LLDB/Lua boundary and briefly stops the game; periodic polling therefore
    // creates visible frame-time spikes. Runtime state is refreshed by user-driven
    // requests (and the explicit Refresh action) instead.

    func enqueueMutation(key: String, request: Hades2Request, title: String, delay: TimeInterval = 0.35, completion: ((Bool) -> Void)? = nil) {
        mutationScheduler.schedule(key: key, delay: delay) { [weak self] in
            self?.send(request, title: title, coalesceKey: key, announceSuccess: false, completion: completion)
        }
    }

    func feature(_ key: String, value: Any, completion: ((Bool) -> Void)? = nil) {
        guard canEditDesired else { return }
        if let enabled = value as? Bool {
            if enabled { beginFeatureActivationGrace(key) }
            else { clearFeatureActivationGrace(key) }
        }
        // Desired state belongs to the trainer profile, not to the debugger
        // connection. Keep the UI intent editable while detached and let the
        // backend apply/replay it whenever a valid Lua scene becomes available.
        switch key {
        case "godMode": if let value = value as? Bool { godMode = value }
        case "infiniteHealth": if let value = value as? Bool { infiniteHealth = value }
        case "infiniteMana": if let value = value as? Bool { infiniteMana = value }
        case "instantCastCooldown": if let value = value as? Bool { instantCastCooldown = value }
        case "hexAlwaysReady": if let value = value as? Bool { hexAlwaysReady = value }
        case "infiniteAmmo": if let value = value as? Bool { infiniteAmmo = value }
        case "autoMiniGames": if let value = value as? Bool { autoMiniGames = value }
        case "gardenQoL": if let value = value as? Bool { gardenQoL = value }
        case "boonRarityEnabled": if let value = value as? Bool { boonRarityEnabled = value }
        case "damageEnabled": if let value = value as? Bool { damageEnabled = value }
        case "moneyMultiplierEnabled": if let value = value as? Bool { moneyMultiplierEnabled = value }
        case "resourceMultiplierEnabled": if let value = value as? Bool { resourceMultiplierEnabled = value }
        case "gameSpeed":
            let speed: Double?
            if let value = value as? Double { speed = value }
            else if let value = value as? Int { speed = Double(value) }
            else { speed = nil }
            guard let speed else { return }
            setGameSpeedValue(speed, completion: completion)
            return
        default: break
        }
        send(.setDesired(feature: key, value: value), title: "更新功能", completion: completion)
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
            title: "更新游戏速度",
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
        let title = vital == "health" ? "生命" : (vital == "mana" ? "魔力" : "护甲")
        enqueueMutation(key: "vital.\(vital).\(field)", request: .setVital(vital: vital, field: field, value: value), title: "更新\(title)")
    }

    func lockVital(_ vital: String, locked: Bool) {
        guard canSetVitals, ["health", "mana", "armor"].contains(vital) else { return }
        send(.lockVital(vital: vital, locked: locked), title: locked ? "锁定局内数值" : "解除局内数值锁定")
    }

    func setResource(_ resource: String, amount: String) {
        guard canSetResource, let count = amountValue(amount) else { return }
        let current: Double?
        if resource == "Money" { current = money }
        else { current = resources.first(where: { $0.id == resource })?.count }
        guard resource == "Money" || resources.contains(where: { $0.id == resource }) else { return }
        if let current = current, Int(current.rounded()) == count { return }
        enqueueMutation(key: "resource.\(resource)", request: .setResource(resource: resource, amount: count), title: "更新资源")
    }

    func lockResource(_ resource: String, locked: Bool) {
        guard canSetResource else { return }
        guard resource == "Money" || resources.contains(where: { $0.id == resource }) else { return }
        send(.lockResource(resource: resource, locked: locked), title: locked ? "锁定当前资源数量" : "解除资源锁定")
    }

    func setRerolls(_ amount: String) {
        guard canSetResource, let count = amountValue(amount) else { return }
        if let current = rerolls, Int(current.rounded()) == count { return }
        enqueueMutation(key: "rerolls", request: .setRerolls(amount: count), title: "更新重骰次数")
    }

    func lockRerolls(_ locked: Bool) {
        guard canSetResource else { return }
        send(.lockRerolls(locked: locked), title: locked ? "锁定重骰次数" : "解除重骰锁定")
    }

    func setStat(_ stat: String, text: String, locked: Bool) {
        guard canSetStats, let rule = Self.statRules[stat], statSupport[stat] != false, statAvailable[stat] != false else { return }
        if !locked {
            send(.setStat(stat: stat, locked: false, value: nil), title: "解除属性锁定")
            return
        }
        guard let value = Double(text), value.isFinite, (rule.min...rule.max).contains(value) else { return }
        if rule.integer && value.rounded() != value { return }
        let encodedValue: Any = rule.integer ? Int(value) : value
        enqueueMutation(key: "stat.\(stat)", request: .setStat(stat: stat, locked: true, value: encodedValue), title: "更新属性锁定")
    }

    func setElement(_ element: String, text: String) {
        guard canSetElements, let amount = amountValue(text), elements.contains(where: { $0.id == element }) else { return }
        if let current = elements.first(where: { $0.id == element })?.count, Int(current.rounded()) == amount { return }
        enqueueMutation(key: "element.\(element)", request: .setElement(element: element, amount: amount), title: "更新元素数量")
    }

    func lockElement(_ element: String, locked: Bool) {
        guard canSetElements, elements.contains(where: { $0.id == element }) else { return }
        send(.lockElement(element: element, locked: locked), title: locked ? "锁定元素数量" : "解除元素锁定")
    }

    func setBoonRarity(target: String, multiplier: String, forceLegendary: Bool, forceDuo: Bool, completion: ((Bool) -> Void)? = nil) {
        guard canEditDesired, ["Common", "Rare", "Epic", "Heroic"].contains(target),
              let value = Double(multiplier), value.isFinite, (0...1000).contains(value) else { return }
        boonRarityTarget = target; boonRarityMultiplier = value; boonForceLegendary = forceLegendary; boonForceDuo = forceDuo
        enqueueMutation(
            key: "boon.rarity",
            request: .setBoonRarity(target: target, multiplier: value, forceLegendary: forceLegendary, forceDuo: forceDuo),
            title: "更新祝福稀有度",
            completion: completion
        )
    }


    func setNextRoomReward(_ reward: String?) {
        guard canEditDesired else { return }
        nextRoomReward = reward
        send(.setNextRoomReward(reward), title: reward == nil ? "清除下一房奖励" : "设置下一房奖励")
    }

    private func shortcutPayload() -> [String: Any] { shortcutStore.payload() }

    func saveProfile(_ name: String) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        flushPendingMutations()
        send(.saveProfile(name: trimmed, shortcuts: shortcutPayload()), title: "保存自定义配置")
    }

    func loadProfile(_ name: String) {
        guard !name.isEmpty else { return }
        sendBarrier(.loadProfile(name), title: "载入自定义配置")
    }

    func deleteProfile(_ name: String) {
        guard !name.isEmpty else { return }
        send(.deleteProfile(name), title: "删除自定义配置")
    }

    func listProfiles() { send(.listProfiles, title: "读取自定义配置") }
    func runDiagnostics() { send(.diagnostics, title: "运行自检") }
    func exportDiagnostics() { send(.exportDiagnostics, title: "导出诊断包") }
    func cancelStagedRestore() { send(.cancelStagedRestore, title: "取消暂存恢复") }

    func spawnBoon(_ loot: String) {
        guard canSpawnReward, boons.contains(where: { $0.id == loot }) else { return }
        send(.spawnReward(loot), title: "生成掉落物")
    }

    func openSellTraits() {
        guard canOpenNativeBoonScreen else { return }
        send(.openSellTraits, title: "打开祝福出售界面")
    }

    func performSpecialReward(_ reward: String) {
        guard let option = specialRewardOptions.first(where: { $0.id == reward }) else { return }
        if option.kind == "native_choice" {
            guard canOpenNativeBoonScreen, !option.sourceId.isEmpty else { return }
            send(.openSpecialChoice(source: option.sourceId), title: "打开特殊祝福三选一")
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
        enqueueMutation(key: "feature.\(key)", request: .setDesired(feature: key, value: value), title: "更新倍率")
    }

    func setCounter(_ counter: String, text: String) {
        guard canSetVitals, let value = Double(text), value.isFinite, (0...999_999).contains(value) else { return }
        if counter == "spellCharge", let current = spellCharge, abs(current - value) < 0.0001 { return }
        enqueueMutation(key: "counter.\(counter)", request: .setCounter(counter: counter, value: value), title: "更新局内计数")
    }

    func createBackup() {
        send(.backup(runCount: runCount), title: "备份存档") { [weak self] success in
            if success { self?.send(.listBackups, title: "刷新备份列表") }
        }
    }

    func renameBackup(_ backupID: String, name: String) {
        guard backups.contains(where: { $0.id == backupID }), !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        send(.renameBackup(id: backupID, name: name), title: "重命名备份")
    }

    func openBackupFolder(_ backupID: String? = nil) {
        send(.openBackupFolder(backupID), title: backupID == nil ? "打开备份目录" : "在文件夹中显示")
    }

    func restoreBackup(_ backupID: String, backupCurrent: Bool) {
        guard backups.contains(where: { $0.id == backupID && $0.valid }) else {
            error = "请选择校验通过的备份。"; return
        }
        sendBarrier(.restoreBackup(backupID, backupCurrent: backupCurrent), title: "恢复所选存档")
    }

    func deleteBackup(_ backupID: String) {
        guard backups.contains(where: { $0.id == backupID }) else { return }
        send(.deleteBackup(backupID), title: "删除存档备份")
    }

    private func applyProfileShortcuts(_ values: [String: Any]) {
        shortcutStore.applyProfile(values)
        installHotkeys()
    }

    private func updatePendingRestorePolling() {
        pendingRestoreTimer?.invalidate(); pendingRestoreTimer = nil
        guard pendingRestoreID != nil, backendSession.isRunning else { return }
        pendingRestoreTimer = Timer.scheduledTimer(withTimeInterval: 2.5, repeats: true) { [weak self] _ in
            guard let self = self, self.pendingRestoreID != nil, !self.busy, !self.exiting else { return }
            self.send(.scan, title: "等待游戏退出并恢复存档", announceSuccess: false)
        }
    }

    func shortcutChord(_ action: ShortcutAction) -> HotkeyChord { shortcutStore.chord(action) }
    func shortcutText(_ action: ShortcutAction) -> String { shortcutStore.chord(action).displayText }

    func setShortcut(action: ShortcutAction, chord: HotkeyChord) {
        shortcutError = shortcutStore.set(action, chord: chord) ?? ""
        if shortcutError.isEmpty { installHotkeys() }
    }

    private func featureHotkeyFeedback(_ key: String, targetEnabled: Bool) -> TrainerHotkeyFeedback? {
        guard targetEnabled else { return .disabled }
        if activeFeatures[key] == true { return .enabled }
        if dormantFeatures[key] == true || !connected || status != "ready" { return .deferred }
        return nil
    }

    private func performFeatureShortcut(_ key: String, current: Bool) {
        let targetEnabled = !current
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
        } else if activeFeatures["boonRarityEnabled"] == true {
            feedback = .enabled
        } else {
            feedback = .deferred
        }
        TrainerHotkeyFeedbackPlayer.play(feedback)
    }

    private func performShortcut(_ action: ShortcutAction) {
        if action == .disableAll {
            guard connected && !busy && !exiting else { return }
            sendBarrier(.disableAll, title: "全部关闭") { success in
                if success { TrainerHotkeyFeedbackPlayer.play(.disabled) }
            }
            return
        }
        guard !busy && !exiting else { return }
        switch action {
        case .godMode: guard canEditDesired else { return }; performFeatureShortcut("godMode", current: godMode)
        case .infiniteHealth: guard canEditDesired else { return }; performFeatureShortcut("infiniteHealth", current: infiniteHealth)
        case .infiniteMana: guard canEditDesired else { return }; performFeatureShortcut("infiniteMana", current: infiniteMana)
        case .instantCastCooldown: guard canEditDesired else { return }; performFeatureShortcut("instantCastCooldown", current: instantCastCooldown)
        case .hexAlwaysReady: guard canEditDesired else { return }; performFeatureShortcut("hexAlwaysReady", current: hexAlwaysReady)
        case .infiniteAmmo: guard canEditDesired else { return }; performFeatureShortcut("infiniteAmmo", current: infiniteAmmo)
        case .damageEnabled: guard canEditDesired else { return }; performFeatureShortcut("damageEnabled", current: damageEnabled)
        case .autoMiniGames: guard canEditDesired else { return }; performFeatureShortcut("autoMiniGames", current: autoMiniGames)
        case .gardenQoL: guard canEditDesired else { return }; performFeatureShortcut("gardenQoL", current: gardenQoL)
        case .boonRarityEnabled:
            guard canEditDesired else { return }
            performFeatureShortcut("boonRarityEnabled", current: boonRarityEnabled)
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
        case .moneyMultiplierEnabled:
            guard canEditDesired else { return }
            performFeatureShortcut("moneyMultiplierEnabled", current: moneyMultiplierEnabled)
        case .resourceMultiplierEnabled:
            guard canEditDesired else { return }
            performFeatureShortcut("resourceMultiplierEnabled", current: resourceMultiplierEnabled)
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
            HotkeyBinding(actionID: action.rawValue, title: action.title, chord: shortcutChord(action))
        }
        shortcutError = instance.register(bindings)
        hotkeys = instance
    }

    func openLog() {
        appendLog("日志已创建")
        logSink.flush()
        NSWorkspace.shared.open(logSink.url)
    }

    private func appendLog(_ line: String) {
        logSink.append(line)
    }

    private var runtimeCleanupRequired: Bool {
        if activeFeatures.values.contains(true) || dormantFeatures.values.contains(true) { return true }
        if desiredFeatureKeys.contains(where: desiredFeatureEnabled) { return true }
        if abs(gameSpeed - 1.0) > 0.0001 || nextRoomReward != nil { return true }
        if healthLocked || manaLocked || armorLocked || moneyLocked || rerollsLocked { return true }
        if resources.contains(where: \.locked) || elements.contains(where: \.locked) { return true }
        return graspLocked || dodgeLocked || critLocked || chargeSpeedLocked
            || moveSpeedLocked || sprintSpeedLocked || dashSpeedLocked
            || attackSpeedLocked || manaRegenLocked || enemyDamageLocked || enemyHealthLocked
    }

    private func detachForTermination(completion: @escaping (Bool) -> Void) {
        guard connected else {
            finishExit(completion: completion)
            return
        }
        sendBarrier(.disconnect, title: "退出前分离进程", announceSuccess: false) { [weak self] _ in
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

        // Capture verified runtime state before reset_desired updates the UI
        // projection. Durable intent and resident teardown have separate owners:
        // reset_desired never crosses Lua; runtime cleanup is best-effort only.
        let cleanupRequired = runtimeCleanupRequired
        sendBarrier(.resetDesired, title: "退出前重置修改状态", announceSuccess: false) { [weak self] _ in
            guard let self else { completion(true); return }
            guard self.connected, cleanupRequired else {
                self.detachForTermination(completion: completion)
                return
            }
            self.sendBarrier(.disableAll, title: "退出前清理运行时", announceSuccess: false) { [weak self] _ in
                guard let self else { completion(true); return }
                self.detachForTermination(completion: completion)
            }
        }
    }

    private func finishExit(completion: @escaping (Bool) -> Void) {
        pendingRestoreTimer?.invalidate()
        pendingRestoreTimer = nil
        pendingRestoreID = nil
        invalidatePendingMutations()
        shuttingDown = true
        backendSession.stop(suppressTerminationError: true)
        completion(true)
    }
}
