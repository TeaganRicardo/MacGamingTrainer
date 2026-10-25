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

    private let session: TrainerBackendSession
    private let logSink: TrainerLogSink
    private let backendScriptURL: URL?
    private var targetObservation: TrainerTargetObservation?

    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var operation: TrainerTextToken { backendStatus.operation }
    var hostActionsEnabled: Bool { backendAvailable && !busy && backendStatus.protocolCompatible }
    var statusTitle: TrainerTextToken { TrainerTextToken(key: connected ? "host.connected" : "host.disconnected") }
    var connectionDetailText: TrainerTextToken {
        TrainerTextToken(key: connected ? (heroReady ? "hades.ready" : "hades.waitingForHero") : "hades.connectionHelp")
    }
    var launchActionFromHost: (() -> Void)? { { [weak self] in self?.send("launch", operation: "host.launchGame") } }

    init(session: TrainerBackendSession, backendScriptURL: URL? = nil) {
        self.session = session
        self.backendScriptURL = backendScriptURL
        self.logSink = TrainerLogSink(gameID: "hades")
        DispatchQueue.main.async { [weak self] in self?.startBackend() }
    }

    private func startBackend() {
        do {
            try session.start(
                descriptor: HadesGameModule.descriptor,
                backendScriptURL: backendScriptURL,
                applyPayload: { [weak self] in self?.apply($0) },
                resetGameState: { [weak self] in self?.resetObservation() },
                log: { [weak self] in self?.logSink.append($0) },
                onStatusChange: { [weak self] in self?.backendStatus = $0 }
            )
            refreshFromHost()
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

    func hostDidBecomeActive() {
        if connected && !busy { refreshFromHost() }
    }

    func setInvincibility(_ enabled: Bool) {
        send("set_invincibility", params: ["value": enabled], operation: "hades.invincibility")
    }

    func prepareForTermination(completion: @escaping () -> Void) {
        guard connected else {
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
        session.send(command, params: params, operation: operation, announceSuccess: announceSuccess,
                     timeout: command == "connect" ? 130 : 20, completion: completion)
    }

    private func apply(_ payload: [String: Any]) {
        if payload["connected"] as? Bool == true, let observation = targetObservation {
            if !observation.isRunning || (observation.processIdentifier != nil && payload["pid"] as? Int32 != observation.processIdentifier) {
                resetObservation()
                return
            }
        }
        connected = payload["connected"] as? Bool ?? false
        heroReady = payload["heroReady"] as? Bool ?? false
        invincible = payload["invincible"] as? Bool ?? false
        health = payload["health"] as? Double ?? 0
        maxHealth = payload["maxHealth"] as? Double ?? 0
        money = payload["money"] as? Double ?? 0
    }

    private func resetObservation() {
        connected = false
        heroReady = false
        invincible = false
        health = 0
        maxHealth = 0
        money = 0
    }
}

struct HadesTrainerView: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @ObservedObject var model: HadesTrainerModel

    private func text(_ key: String) -> String {
        HadesGameModule.presentationText(key: key, arguments: [], language: localization.language)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            TrainerSection(title: text("hades.currentHero"), icon: "person.fill") {
                HStack(spacing: theme.sectionSpacing) {
                    TrainerMetricCard(title: text("hades.health"), icon: "heart.fill", tint: .red) {
                        Text(model.heroReady ? "\(Int(model.health)) / \(Int(model.maxHealth))" : "—")
                            .font(.title2.monospacedDigit())
                    }
                    TrainerMetricCard(title: text("hades.money"), icon: "circle.fill", tint: theme.accent) {
                        Text(model.heroReady ? String(Int(model.money)) : "—")
                            .font(.title2.monospacedDigit())
                    }
                }
                TrainerFeatureToggleRow(
                    title: text("hades.invincibility"), icon: "shield.fill",
                    state: TrainerFeatureControlState(
                        isOn: model.invincible, isInteractive: model.hostActionsEnabled && model.connected && model.heroReady,
                        canEditValue: false, opacity: model.heroReady ? 1 : 0.6, indicatorColor: theme.accent,
                        helpText: text("hades.invincibilityHelp"), isWarning: false
                    ), shortcutText: nil
                ) { model.setInvincibility(!model.invincible) }
                Text(text(model.heroReady ? "hades.invincibilityHelp" : "hades.waitingForHero"))
                    .font(.callout).foregroundStyle(.secondary)
            }
            if !model.backendStatus.error.isEmpty {
                TrainerMessageBanner(
                    text: localization.presentation(model.backendStatus.error, arguments: model.backendStatus.errorArguments),
                    icon: "exclamationmark.triangle.fill", color: theme.warning
                )
            }
        }
    }
}

struct HadesGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "flame.fill", platformLabel: "Intel · Rosetta", headerTitle: "HADES"
    )
    static let presentationKeyPrefix = "hades."
    static func makeModel(session: TrainerBackendSession) -> HadesTrainerModel { HadesTrainerModel(session: session) }
    static func makeContent(model: HadesTrainerModel) -> HadesTrainerView { HadesTrainerView(model: model) }
    static func makeSidebarActions(model: HadesTrainerModel) -> some View { EmptyView() }
    static func makeHeaderActions(model: HadesTrainerModel) -> some View { EmptyView() }
    static func makeManagementCommands(model: HadesTrainerModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands { TrainerEmptyCommands() }

    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        let pairs: [String: TrainerLocalizedText] = [
            "hades.ready": .init(zhCN: "角色已就绪", en: "Hero Ready"),
            "hades.waitingForHero": .init(zhCN: "进入游戏后读取当前角色。", en: "Enter the game to observe the current hero."),
            "hades.connectionHelp": .init(zhCN: "支持本机 Hades Steam 版本；通过 Rosetta 连接。", en: "Supports the local Hades Steam build through Rosetta."),
            "hades.currentHero": .init(zhCN: "当前角色", en: "Current Hero"),
            "hades.health": .init(zhCN: "生命值", en: "Health"),
            "hades.money": .init(zhCN: "金钱", en: "Money"),
            "hades.invincibility": .init(zhCN: "当前角色无敌", en: "Current Hero Invincibility"),
            "hades.invincibilityHelp": .init(zhCN: "仅管理 Trainer 自己的保护标记，保留游戏原有保护；新角色需重新开启。", en: "Controls the Trainer's own protection flag and preserves native protection. Enable again for a new hero."),
            "hades.error.notRunning": .init(zhCN: "请先启动 Hades。", en: "Launch Hades first."),
            "hades.error.ambiguousTarget": .init(zhCN: "发现多个 Hades 进程，请保留一个后重试。", en: "Multiple Hades processes found. Keep one running and retry."),
            "hades.error.notConnected": .init(zhCN: "Hades 连接已断开，请重新连接。", en: "Hades is disconnected. Connect again."),
            "hades.error.invalidValue": .init(zhCN: "修改值无效。", en: "Invalid feature value."),
            "hades.error.unknownCommand": .init(zhCN: "当前模块不支持此操作。", en: "This module does not support this action."),
            "hades.error.heroNotReady": .init(zhCN: "当前没有可修改的角色，请进入游戏后刷新。", en: "No hero is ready. Enter the game and refresh."),
            "hades.error.unsupportedRuntime": .init(zhCN: "当前角色状态不兼容，未执行修改。", en: "The current hero state is incompatible. No change was made."),
            "hades.error.unsupportedBuild": .init(zhCN: "此 Hades 镜像尚未适配，未执行修改。", en: "This Hades image is unsupported. No change was made."),
            "hades.error.attachDenied": .init(zhCN: "系统拒绝连接 Hades；请确认调试权限并重新连接。", en: "The system denied attaching to Hades. Check debugger access and reconnect."),
            "hades.error.debuggerStart": .init(zhCN: "无法启动调试组件，请检查 Xcode 命令行工具。", en: "Unable to start the debugger. Check Xcode command line tools."),
            "hades.error.debuggerLost": .init(zhCN: "调试连接丢失，请重启后台后重新连接。", en: "Debugger connection lost. Restart the backend and reconnect."),
            "hades.error.debuggerProtocol": .init(zhCN: "调试组件响应不兼容，请重启后台。", en: "Incompatible debugger reply. Restart the backend."),
            "hades.error.debuggerCall": .init(zhCN: "无法读取游戏状态，请刷新或重新连接。", en: "Unable to read game state. Refresh or reconnect."),
            "hades.error.outcomeUnknown": .init(zhCN: "操作结果不明，未自动重试；请检查游戏并重启游戏后再连接。", en: "The operation outcome is unknown and was not retried. Inspect and restart the game before reconnecting."),
            "hades.error.restartRequired": .init(zhCN: "上次操作结果不明，请重启游戏后再连接。", en: "The previous outcome is unknown. Restart the game before reconnecting."),
            "hades.error.stopTimeout": .init(zhCN: "等待游戏暂停超时，请重新连接。", en: "Timed out waiting for the game to stop. Reconnect."),
            "hades.error.resumeFailed": .init(zhCN: "游戏尚未恢复运行，请保持连接并重试断开。", en: "The game has not resumed. Keep connected and retry disconnecting."),
            "hades.error.restoreFailed": .init(zhCN: "后台暂停设置尚未恢复，请保持连接并重试断开。", en: "The background focus setting has not been restored. Keep connected and retry disconnecting."),
            "hades.error.unexpectedStop": .init(zhCN: "游戏发生非预期暂停，未执行当前修改。", en: "The game stopped unexpectedly. The current change was not executed."),
            "hades.error.runtimeNotReady": .init(zhCN: "游戏脚本尚未就绪，请稍后刷新。", en: "Game scripts are not ready. Refresh when the game is ready."),
            "hades.error.detachFailed": .init(zhCN: "尚未断开调试连接，请重试断开。", en: "The debugger is still attached. Retry disconnecting."),
        ]
        return pairs[key]?.resolve(for: language) ?? key
    }
}
