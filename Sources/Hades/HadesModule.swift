import Foundation
import SwiftUI

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
    @Published private(set) var resources: [String: Double] = [:]
    @Published private(set) var traits: [HadesCurrentTrait] = []
    @Published private(set) var catalog: [HadesCatalogEntry] = []
    @Published private(set) var resourceCatalog: [HadesResourceDefinition] = []
    @Published private(set) var traitNames: [String: [String: String]] = [:]
    @Published private(set) var target: HadesHeroTarget?
    @Published private(set) var localError = ""
    @Published private(set) var shortcutError = ""
    @Published private(set) var shortcutRevision = 0
    @Published private(set) var feedback: TrainerFeedbackNotice?
    @Published var shortcutSettingsPresented = false

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
        targetObservation = observation
        resetObservation()
    }
    func hostDidBecomeActive() { if connected && !busy { refreshFromHost() } }

    func isEnabled(_ feature: HadesFeature) -> Bool { features[feature.rawValue]?.bool ?? false }
    func number(_ feature: HadesFeature) -> Double { features[feature.rawValue]?.number ?? feature.neutralValue }
    func setInvincibility(_ enabled: Bool) { setFeature(.invincibility, value: enabled) }
    func setFeature(_ feature: HadesFeature, value: Any) {
        guard canMutate else { return }
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
    func heal() { sendToHero("heal", target: target, operation: "hades.heal") }
    func addTrait(_ trait: HadesCatalogEntry, rarity: String, level: Int) {
        sendToHero("add_trait", params: ["trait": trait.id, "rarity": rarity, "level": level], target: target, operation: "hades.acquire")
    }
    func updateTrait(_ trait: HadesCurrentTrait, rarity: String, level: Int, target: HadesHeroTarget?) {
        sendToHero("update_trait", params: ["instanceId": trait.instanceId, "rarity": rarity, "level": level], target: target, operation: "hades.apply")
    }
    func removeTrait(_ trait: HadesCurrentTrait) {
        sendToHero("remove_trait", params: ["instanceId": trait.instanceId], target: target, operation: "hades.remove")
    }
    func disableAll() {
        guard hostActionsEnabled else { return }
        send("disable_all", operation: "host.disableAll")
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
        hotkeys.register(HadesShortcutAction.allCases.map { HotkeyBinding(actionID: $0.rawValue, chord: shortcuts.chord($0)) })
    }
    private func performShortcut(_ rawValue: String) {
        guard canMutate, !shortcutSettingsPresented, let action = HadesShortcutAction(rawValue: rawValue) else {
            TrainerHotkeyFeedbackPlayer.play(.rejected); return
        }
        if action == .heal { heal() }
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
            if announceSuccess && ok {
                self?.feedback = TrainerFeedbackNotice(text: TrainerTextToken(key: "host.backend.notice.completed"), tone: .success)
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
            if payload["catalog"] != nil {
                let decoded = try JSONDecoder().decode(HadesCatalogPayload.self, from: data)
                catalog = decoded.catalog
                resourceCatalog = decoded.resourceCatalog
                traitNames = decoded.traitNames ?? [:]
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
            resources = state.resources ?? [:]
            traits = state.traits ?? []
        } catch {
            if payload["catalog"] == nil { resetObservation() }
            localError = payload["catalog"] != nil ? "hades.error.catalog" : "hades.error.protocol"
        }
    }
    private func resetObservation() {
        connected = false; heroReady = false; invincible = false
        health = 0; maxHealth = 0; money = 0; rerolls = 0; godGauge = 0; maxGodGauge = 0
        target = nil; features = [:]; resources = [:]; traits = []
    }
}

struct HadesGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(sidebarIconSystemName: "flame.fill", platformLabel: "Intel · Rosetta", headerTitle: "HADES")
    static let presentationKeyPrefix = "hades."
    static func makeModel(session: TrainerBackendSession) -> HadesTrainerModel { HadesTrainerModel(session: session) }
    static func makeContent(model: HadesTrainerModel) -> HadesTrainerView { HadesTrainerView(model: model) }
    static func makeSidebarActions(model: HadesTrainerModel) -> HadesSidebarActions { HadesSidebarActions(model: model) }
    static func makeHeaderActions(model: HadesTrainerModel) -> some View { EmptyView() }
    static func makeFeedback(model: HadesTrainerModel) -> HadesOperationFeedback { HadesOperationFeedback(model: model) }
    static func makeManagementCommands(model: HadesTrainerModel, localization: TrainerLocalizationStore) -> HadesManagementCommands {
        HadesManagementCommands(model: model, localization: localization)
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        HadesPresentation.text(key, language: language)
    }
}
