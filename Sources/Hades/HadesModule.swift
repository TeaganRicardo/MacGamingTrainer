import Foundation
import AppKit
import SwiftUI
import UniformTypeIdentifiers

final class HadesTrainerModel: ObservableObject, TrainerHostModel {
    @Published private(set) var backendStatus = TrainerBackendStatus()
    @Published private(set) var connected = false
    @Published private(set) var heroReady = false
    @Published private(set) var invincible = false
    @Published private(set) var health = 0.0
    @Published private(set) var maxHealth = 0.0
    @Published private(set) var money = 0.0
    @Published private(set) var rerolls = 0.0
    @Published private(set) var godGauge = 0.0
    @Published private(set) var maxGodGauge = 0.0
    @Published private(set) var features: [String: HadesFeatureValue] = [:]
    @Published private(set) var activeFeatures: [String: Bool] = [:]
    @Published private(set) var resources: [String: Double] = [:]
    @Published private(set) var traits: [HadesCurrentTrait] = []
    @Published private(set) var world: HadesWorldObservation?
    @Published private(set) var worldRewards: [HadesWorldReward] = []
    @Published private(set) var worldTerms: [String: [String: String]] = [:]
    @Published private(set) var catalog: [HadesCatalogEntry] = []
    @Published private(set) var resourceCatalog: [HadesResourceDefinition] = []
    @Published private(set) var traitNames: [String: [String: String]] = [:]
    @Published private(set) var target: HadesHeroTarget?
    @Published private(set) var localError = ""
    @Published private(set) var shortcutError = ""
    @Published private(set) var shortcutRevision = 0
    @Published private(set) var feedback: TrainerFeedbackNotice?
    @Published var shortcutSettingsPresented = false
    @Published var workbenchSearch = ""
    @Published var numericControlsExpanded = false
    @Published var profilesPresented = false
    @Published var diagnosticsPresented = false
    @Published private(set) var profiles: [HadesSettingsProfile] = []
    @Published private(set) var diagnostics: [HadesDiagnosticCheck] = []
    private var diagnosticsReport: [String: Any]?

    private let session: TrainerBackendSession
    private let logSink: TrainerLogSink
    private let backendScriptURL: URL?
    private var targetObservation: TrainerTargetObservation?
    private var shortcuts: HadesShortcutStore
    private lazy var hotkeys = GlobalHotkeys(gameID: "hades", registrationChanged: { [weak self] failure in
        self?.shortcutError = failure == nil ? "" : "hades.error.shortcutRegistration"
    }) { [weak self] action in self?.performShortcut(action) }

    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var operation: TrainerTextToken { backendStatus.operation }
    var hostActionsEnabled: Bool { backendAvailable && !busy && backendStatus.protocolCompatible }
    var canEditIntent: Bool { backendAvailable && backendStatus.protocolCompatible && connected }
    var canMutate: Bool { backendAvailable && backendStatus.protocolCompatible && connected && heroReady }
    var statusTitle: TrainerTextToken { TrainerTextToken(key: connected ? "host.connected" : "host.disconnected") }
    var connectionDetailText: TrainerTextToken {
        TrainerTextToken(key: connected ? (heroReady ? "hades.ready" : "hades.waitingForHero") : "hades.connectionHelp")
    }
    var launchActionFromHost: (() -> Void)? { { [weak self] in self?.send("launch", operation: "host.launchGame") } }

    init(session: TrainerBackendSession, backendScriptURL: URL? = nil,
         defaults: UserDefaults = .standard, logSink: TrainerLogSink? = nil) {
        self.session = session
        self.backendScriptURL = backendScriptURL
        self.logSink = logSink ?? TrainerLogSink(gameID: "hades")
        self.shortcuts = HadesShortcutStore(defaults: defaults)
        DispatchQueue.main.async { [weak self] in
            self?.startBackend()
            self?.installShortcuts()
        }
    }

    private func startBackend() {
        do {
            try session.start(
                descriptor: HadesGameModule.descriptor,
                backendScriptURL: backendScriptURL,
                applyPayload: { [weak self] in self?.apply($0) },
                resetGameState: { [weak self] in self?.resetObservation() },
                log: { [weak self] in self?.logSink.append($0) },
                onStatusChange: { [weak self] in self?.receiveStatus($0) }
            )
            refreshFromHost()
            send("catalog", operation: "hades.catalog", announceSuccess: false)
        } catch {
            // TrainerBackendSession publishes the startup failure.
        }
    }

    func toggleConnectionFromHost() {
        send(connected ? "disconnect" : "connect", operation: connected ? "host.disconnectGame" : "host.connectGame")
    }
    func refreshFromHost() { send("status", operation: "host.refreshStatus", announceSuccess: false) }
    func restartBackendFromHost() { session.restart() }
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {
        logSink.targetLifetimeChanged(running: observation.isRunning, identity: .init(
            processName: HadesGameModule.descriptor.targetProcessName,
            bundleIdentifier: HadesGameModule.descriptor.targetBundleIdentifier,
            processIdentifier: observation.processIdentifier))
        targetObservation = observation
        resetObservation()
    }
    func hostDidBecomeActive() { if connected && !busy { refreshFromHost() } }

    func isEnabled(_ feature: HadesFeature) -> Bool { features[feature.rawValue]?.bool ?? false }
    func isActive(_ feature: HadesFeature) -> Bool { activeFeatures[feature.rawValue] ?? false }
    func number(_ feature: HadesFeature) -> Double { features[feature.rawValue]?.number ?? feature.neutralValue }
    func setInvincibility(_ enabled: Bool) { setFeature(.invincibility, value: enabled) }
    func setFeature(_ feature: HadesFeature, value: Any) {
        guard canEditIntent else { return }
        send("set_feature", params: ["feature": feature.rawValue, "value": value], operation: feature.key)
    }
    func setNumber(_ feature: HadesFeature, text: String) -> String {
        guard let value = Double(text), value.isFinite,
              feature == .dashBonus ? (value >= 0 && value <= 20 && value.rounded() == value) : (value >= 0.1 && value <= 100) else {
            localError = "hades.error.invalidValue"
            return text
        }
        setFeature(feature, value: value)
        return HadesNumberDraft.format(value)
    }
    func setValue(_ field: String, value: Double, target: HadesHeroTarget?) {
        sendToHero("set_value", params: ["field": field, "value": value], target: target, operation: "hades.values")
    }
    func setResource(_ resource: String, value: Double, target: HadesHeroTarget?) {
        sendToHero("set_resource", params: ["resource": resource, "value": value], target: target, operation: "hades.resources")
    }
    func gainResource(_ resource: String, amount: Double, target: HadesHeroTarget?) {
        sendToHero("gain_resource", params: ["resource": resource, "amount": amount], target: target, operation: "hades.gainResource")
    }
    func worldAction(_ command: String, roomID: String?, params: [String: Any] = [:], operation: String) {
        guard let roomID, roomID == world?.roomId else { localError = "hades.error.staleRoom"; return }
        var payload = params
        payload["roomId"] = roomID
        sendToHero(command, params: payload, target: target, operation: operation)
    }
    func generateFishing() {
        worldAction("generate_fishing", roomID: world?.roomId, operation: "hades.generateFishing")
    }
    func generateChaosGate() {
        worldAction("generate_chaos_gate", roomID: world?.roomId, operation: "hades.generateChaosGate")
    }
    func addTrait(_ trait: HadesCatalogEntry, rarity: String, level: Int) {
        sendToHero("add_trait", params: ["trait": trait.id, "rarity": rarity, "level": level], target: target, operation: "hades.acquire")
    }
    func updateTrait(_ trait: HadesCurrentTrait, rarity: String, level: Int, target: HadesHeroTarget?) {
        sendToHero("update_trait", params: ["instanceId": trait.instanceId, "rarity": rarity, "level": level], target: target, operation: "hades.apply")
    }
    func removeTrait(_ trait: HadesCurrentTrait) {
        sendToHero("remove_trait", params: ["instanceId": trait.instanceId], target: target, operation: "hades.remove")
    }
    func addChaosPair(blessing: HadesCatalogEntry, curse: String, rarity: String, encounters: Int) {
        sendToHero("add_chaos_pair", params: ["blessing": blessing.id, "curse": curse,
                   "rarity": rarity, "encounters": encounters], target: target, operation: "hades.chaosPair")
    }
    func setTraitUses(_ trait: HadesCurrentTrait, uses: Int, target: HadesHeroTarget?) {
        sendToHero("set_trait_uses", params: ["instanceId": trait.instanceId, "uses": uses],
                   target: target, operation: "hades.remainingUses")
    }
    func expireTrait(_ trait: HadesCurrentTrait) {
        sendToHero("expire_trait", params: ["instanceId": trait.instanceId], target: target,
                   operation: trait.blessing == nil ? "hades.expireEffect" : "hades.activateBlessing")
    }
    func refreshTrait(_ trait: HadesCurrentTrait) {
        sendToHero("refresh_trait", params: ["instanceId": trait.instanceId], target: target,
                   operation: "hades.refreshEffect")
    }
    func disableAll() {
        guard hostActionsEnabled else { return }
        send("disable_all", operation: "host.disableAll")
    }
    func makeSaveEditorModel(snapshotID: String? = nil) -> HadesSaveEditorModel {
        HadesSaveEditorModel(session: session, snapshotID: snapshotID)
    }
    func listProfiles() { send("list_profiles", operation: "hades.manage.profiles", announceSuccess: false) }
    func saveProfile(_ name: String) { send("save_profile", params: ["name": name], operation: "hades.profile.save") }
    func loadProfile(_ name: String) { send("load_profile", params: ["name": name], operation: "hades.profile.load") }
    func deleteProfile(_ name: String) { send("delete_profile", params: ["name": name], operation: "host.delete") }
    func runDiagnostics() { send("diagnostics", operation: "hades.manage.diagnostics", announceSuccess: false) }
    func openLog() {
        session.flushDiagnostics()
        logSink.flush()
        NSWorkspace.shared.open(logSink.currentSessionURL() ?? logSink.currentLogURL())
    }
    func openLogHistory() {
        do {
            logSink.flush()
            try FileManager.default.createDirectory(at: logSink.historyURL, withIntermediateDirectories: true)
            NSWorkspace.shared.open(logSink.historyURL)
        } catch { localError = "hades.error.logOpen" }
    }
    func clearCompletedLogs() {
        let cleared = logSink.clearCompletedSessions()
        feedback = TrainerFeedbackNotice(
            text: TrainerTextToken(key: cleared ? "host.logs.cleared" : "host.logs.clearFailed"),
            tone: cleared ? .success : .warning)
    }
    func exportDiagnostics() {
        session.flushDiagnostics()
        logSink.flush()
        send("diagnostics", operation: "hades.diagnostics.export", announceSuccess: false) { [weak self] ok in
            guard ok, let self, var report = self.diagnosticsReport else { return }
            self.session.flushDiagnostics()
            self.logSink.flush()
            do {
                var logs: [String: String] = [:]
                let urls: [URL]
                if let bundle = self.logSink.currentSessionURL() {
                    urls = ["manifest.json", "host.log", "backend.log", "runtime.log"].map { bundle.appendingPathComponent($0) }
                } else { urls = [self.logSink.currentLogURL()] }
                for url in urls where FileManager.default.fileExists(atPath: url.path) {
                    logs[url.lastPathComponent] = try String(contentsOf: url, encoding: .utf8)
                }
                report["logs"] = logs
                let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
                let panel = NSSavePanel()
                panel.allowedContentTypes = [.json]
                panel.nameFieldStringValue = "Hades-Diagnostics.json"
                panel.begin { [weak self] response in
                    guard response == .OK, let url = panel.url else { return }
                    do {
                        try data.write(to: url, options: .atomic)
                        self?.feedback = TrainerFeedbackNotice(text: TrainerTextToken(key: "host.backend.notice.completed"), tone: .success)
                    } catch { self?.localError = "hades.error.diagnosticsExport" }
                }
            } catch { self.localError = "hades.error.diagnosticsExport" }
        }
    }
    func rejectInvalidValue() { localError = "hades.error.invalidValue" }
    func dismissFeedback(_ id: UUID) { if feedback?.id == id { feedback = nil } }
    func traitName(_ trait: HadesCurrentTrait, language: TrainerPresentationLanguage) -> String {
        catalog.first { $0.id == trait.name }?.name(language: language.rawValue)
            ?? traitNames[trait.name]?[language.rawValue]
            ?? traitNames[trait.name]?["en"]
            ?? HadesPresentation.text("hades.unknownTrait", language: language)
    }

    private func sendToHero(_ command: String, params: [String: Any] = [:], target captured: HadesHeroTarget?, operation: String) {
        guard canMutate else { return }
        guard let captured, captured == target else { localError = "hades.error.staleHero"; return }
        var payload = params
        payload["target"] = captured.payload
        send(command, params: payload, operation: operation)
    }

    func shortcutText(_ action: HadesShortcutAction) -> String { shortcuts.chord(action).displayText }
    func setShortcut(_ action: HadesShortcutAction, chord: HotkeyChord) {
        guard chord.modifiers & (HotkeyChord.controlModifier | HotkeyChord.optionModifier | HotkeyChord.commandModifier) != 0 else {
            shortcutError = "hades.error.shortcutModifier"; return
        }
        if shortcuts.set(action, chord: chord) != nil { shortcutError = "hades.error.shortcutConflict"; return }
        shortcutError = ""
        shortcutRevision += 1
        installShortcuts()
    }
    func resetShortcuts() { shortcuts.reset(); shortcutRevision += 1; installShortcuts() }
    private func installShortcuts() {
        hotkeys.register(HadesWorkbenchCatalog.orderedShortcutActions.map { HotkeyBinding(actionID: $0.rawValue, chord: shortcuts.chord($0)) })
    }
    func performShortcut(_ rawValue: String) {
        guard !shortcutSettingsPresented, let action = HadesShortcutAction(rawValue: rawValue),
              (action == .disableAll ? hostActionsEnabled : canEditIntent) else {
            TrainerHotkeyFeedbackPlayer.play(.rejected); return
        }
        if action == .generateFishing { generateFishing() }
        else if action == .generateChaosGate { generateChaosGate() }
        else if action == .disableAll { disableAll() }
        else if let feature = HadesFeature(rawValue: rawValue) { setFeature(feature, value: !isEnabled(feature)) }
    }

    func prepareForTermination(completion: @escaping () -> Void) {
        guard backendAvailable else {
            session.flushDiagnostics()
            session.stop(suppressTerminationError: true)
            completion()
            return
        }
        send("disable_all", operation: "host.disableAll", announceSuccess: false) { [weak self] _ in
            guard let self else { completion(); return }
            self.send("disconnect", operation: "host.disconnectGame", announceSuccess: false) { [weak self] _ in
                self?.session.flushDiagnostics()
                self?.session.stop(suppressTerminationError: true)
                completion()
            }
        }
    }

    private func send(_ command: String, params: [String: Any] = [:], operation: String,
                      announceSuccess: Bool = true, completion: ((Bool) -> Void)? = nil) {
        localError = ""
        session.send(command, params: params, operation: operation, announceSuccess: announceSuccess,
                     timeout: command == "connect" ? 130 : 20, completion: { [weak self] ok in
            if announceSuccess, ok, let self {
                let pendingCleanup = command == "disable_all" && !self.connected
                let pendingProfile = command == "load_profile" && !self.connected
                let noticeKey: String
                if pendingCleanup { noticeKey = "hades.disableAllPending" }
                else if pendingProfile { noticeKey = "hades.profile.pending" }
                else if command == "set_door_route" && params["route"] as? String == "thanatos" {
                    noticeKey = "hades.routeScheduled"
                } else { noticeKey = "host.backend.notice.completed" }
                self.feedback = TrainerFeedbackNotice(text: TrainerTextToken(key: noticeKey),
                    tone: pendingCleanup || pendingProfile ? .warning : .success)
            }
            completion?(ok)
        })
    }

    private func receiveStatus(_ status: TrainerBackendStatus) {
        let previousError = backendStatus.error
        backendStatus = status
        switch status.error {
        case "hades.error.outcomeUnknown", "hades.error.restartRequired", "hades.error.debuggerProtocol":
            resetObservation()
        default: break
        }
        if !status.error.isEmpty && status.error != previousError {
            feedback = TrainerFeedbackNotice(text: TrainerTextToken(key: status.error, arguments: status.errorArguments), tone: .warning)
        }
    }

    private func apply(_ payload: [String: Any]) {
        do {
            let data = try JSONSerialization.data(withJSONObject: payload)
            if let rows = payload["profiles"] {
                profiles = try JSONDecoder().decode([HadesSettingsProfile].self,
                    from: JSONSerialization.data(withJSONObject: rows))
            }
            if let report = payload["diagnostics"] as? [String: Any], let checks = report["checks"] {
                diagnostics = try JSONDecoder().decode([HadesDiagnosticCheck].self,
                    from: JSONSerialization.data(withJSONObject: checks))
                diagnosticsReport = report
            }
            if payload["catalog"] != nil {
                let decoded = try JSONDecoder().decode(HadesCatalogPayload.self, from: data)
                catalog = decoded.catalog
                resourceCatalog = decoded.resourceCatalog
                traitNames = decoded.traitNames ?? [:]
                worldRewards = decoded.worldRewards ?? []
                worldTerms = decoded.worldTerms ?? [:]
            }
            guard payload["connected"] != nil else { return }
            let state = try JSONDecoder().decode(HadesObservation.self, from: data)
            if state.connected, let observation = targetObservation {
                if !observation.isRunning || (observation.processIdentifier != nil && state.pid != observation.processIdentifier) {
                    resetObservation(); return
                }
            }
            connected = state.connected
            heroReady = state.heroReady
            invincible = state.invincible ?? false
            health = state.health ?? 0
            maxHealth = state.maxHealth ?? 0
            money = state.money ?? 0
            rerolls = state.rerolls ?? 0
            godGauge = state.godGauge ?? 0
            maxGodGauge = state.maxGodGauge ?? 0
            target = state.target
            features = state.features ?? [:]
            activeFeatures = state.activeFeatures ?? [:]
            resources = state.resources ?? [:]
            traits = state.traits ?? []
            world = state.world
        } catch {
            if payload["catalog"] == nil { resetObservation() }
            localError = payload["catalog"] != nil ? "hades.error.catalog" : "hades.error.protocol"
        }
    }
    private func resetObservation() {
        connected = false; heroReady = false; invincible = false
        health = 0; maxHealth = 0; money = 0; rerolls = 0; godGauge = 0; maxGodGauge = 0
        target = nil; features = [:]; activeFeatures = [:]; resources = [:]; traits = []; world = nil
    }
}

struct HadesGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(sidebarIconSystemName: "flame.fill", platformLabel: "Intel · Rosetta", headerTitle: "HADES")
    static let presentationKeyPrefix = "hades."

    /// Function discovery and module-hosted controls may contain Host-owned keys.
    /// Resolve those through Host localization in the requested language.
    @MainActor
    static func resolveText(
        key: String,
        language: TrainerPresentationLanguage? = nil,
        localization: TrainerLocalizationStore
    ) -> String {
        let language = language ?? localization.language
        guard key.hasPrefix(presentationKeyPrefix) else {
            return localization.string(key, arguments: [], language: language)
        }
        return HadesPresentation.text(key, language: language)
    }

    static func makeModel(session: TrainerBackendSession) -> HadesTrainerModel { HadesTrainerModel(session: session) }
    static func makeContent(model: HadesTrainerModel) -> HadesTrainerView { HadesTrainerView(model: model) }
    static func makeSidebarActions(model: HadesTrainerModel) -> HadesSidebarActions { HadesSidebarActions(model: model) }
    static func makeHeaderActions(model: HadesTrainerModel) -> some View { HadesHeaderActions(model: model) }
    static func makeFeedback(model: HadesTrainerModel) -> HadesOperationFeedback { HadesOperationFeedback(model: model) }
    static var managedBackupEditor: ((HadesTrainerModel, TrainerSaveSnapshot) -> TrainerToolWindowContent)? {
        { model, snapshot in makeSaveEditorWindow(model: model, snapshotID: snapshot.id) }
    }
    static func makeSaveEditorWindow(model: HadesTrainerModel, snapshotID: String? = nil) -> TrainerToolWindowContent {
        let editor = model.makeSaveEditorModel(snapshotID: snapshotID)
        return TrainerToolWindowContent(canClose: { !editor.busy }, onClose: editor.close) {
            HadesSaveEditorView(model: editor)
        }
    }
    static func makeManagementCommands(model: HadesTrainerModel, localization: TrainerLocalizationStore) -> HadesManagementCommands {
        HadesManagementCommands(model: model, localization: localization)
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        var result = HadesPresentation.text(key, language: language)
        for argument in arguments {
            if let range = result.range(of: "%@") { result.replaceSubrange(range, with: argument) }
        }
        return result
    }
}
