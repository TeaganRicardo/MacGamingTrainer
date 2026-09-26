import Foundation
import SwiftUI

final class ReferenceFixtureModel: ObservableObject, TrainerHostModel {
    @Published private(set) var backendStatus = TrainerBackendStatus()
    @Published private(set) var connected = false
    @Published private(set) var enabled = false

    private let backendSession: TrainerBackendSession
    private let backendScriptURL: URL?
    private let log: (String) -> Void

    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var operation: String { backendStatus.operation }
    var statusTitle: String { connected ? "已连接" : "尚未连接" }
    var connectionDetailText: String { "Reference fixture" }
    var hostActionsEnabled: Bool {
        backendAvailable && !busy && backendStatus.protocolCompatible
    }

    init(
        session: TrainerBackendSession,
        backendScriptURL: URL? = nil,
        log: @escaping (String) -> Void = { _ in }
    ) {
        backendSession = session
        self.backendScriptURL = backendScriptURL
        self.log = log
        DispatchQueue.main.async { [weak self] in
            self?.startBackend()
        }
    }

    func toggleConnectionFromHost() {
        send(connected ? "disconnect" : "connect", operation: connected ? "断开 Reference Fixture" : "连接 Reference Fixture")
    }

    func refreshFromHost() {
        send("status", operation: "刷新 Reference Fixture", announceSuccess: false)
    }

    func restartBackendFromHost() {
        backendSession.restart()
    }

    func setEnabled(_ value: Bool) {
        send("set_enabled", params: ["value": value], operation: value ? "启用 Reference Feature" : "关闭 Reference Feature")
    }

    func prepareForTermination(completion: @escaping (Bool) -> Void) {
        backendSession.stop(suppressTerminationError: true)
        completion(true)
    }

    private func startBackend() {
        guard !backendSession.isStarted else {
            refreshFromHost()
            return
        }
        do {
            try backendSession.start(
                descriptor: ReferenceFixtureGameModule.descriptor,
                backendScriptURL: backendScriptURL,
                applyPayload: { [weak self] payload in self?.apply(payload) },
                resetGameState: { [weak self] in self?.resetGameState() },
                log: log,
                onStatusChange: { [weak self] status in
                    self?.backendStatus = status
                }
            )
            refreshFromHost()
        } catch {
            backendSession.markUnavailable(BackendFailure(
                code: "backend_start_failed",
                presentation: "无法启动 Reference Fixture 后端，请查看日志。",
                diagnostic: error.localizedDescription,
                recoveryPath: nil
            ))
        }
    }

    private func send(
        _ command: String,
        params: [String: Any] = [:],
        operation: String,
        announceSuccess: Bool = true
    ) {
        backendSession.send(
            command,
            params: params,
            operation: operation,
            announceSuccess: announceSuccess
        )
    }

    private func apply(_ payload: [String: Any]) {
        if let connected = payload["connected"] as? Bool {
            self.connected = connected
        }
        if let enabled = payload["enabled"] as? Bool {
            self.enabled = enabled
        }
    }

    private func resetGameState() {
        connected = false
        enabled = false
    }
}

struct ReferenceFixtureContent: View {
    @ObservedObject var model: ReferenceFixtureModel

    var body: some View {
        TrainerFeatureToggleRow(
            title: "Reference Feature",
            icon: "checkmark.circle",
            state: TrainerFeatureControlState(
                isOn: model.enabled,
                isInteractive: model.backendAvailable && !model.busy,
                canEditValue: false,
                opacity: 1,
                indicatorColor: .accentColor,
                helpText: "",
                isWarning: false
            ),
            shortcutText: nil
        ) {
            model.setEnabled(!model.enabled)
        }
    }
}

struct ReferenceFixtureGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "checkmark.seal",
        headerTitle: "REFERENCE"
    )

    static func makeModel(session: TrainerBackendSession) -> ReferenceFixtureModel {
        ReferenceFixtureModel(session: session)
    }

    static func makeContent(model: ReferenceFixtureModel) -> ReferenceFixtureContent {
        ReferenceFixtureContent(model: model)
    }

    static func makeSidebarActions(model: ReferenceFixtureModel) -> some View {
        EmptyView()
    }

    static func makeHeaderActions(model: ReferenceFixtureModel) -> some View {
        EmptyView()
    }

    static func makeManagementCommands(model: ReferenceFixtureModel) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
}
