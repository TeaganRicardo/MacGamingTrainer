import Foundation
import SwiftUI
import TrainerCore

final class ReferenceFixtureModel: ObservableObject, TrainerHostModel {
    @Published private(set) var connected = false
    @Published private(set) var enabled = false

    private let services: TrainerModuleServices
    private var statusObserver: UUID?
    private var backendSession: TrainerBackendSession { services.session }

    var backendStatus: TrainerBackendStatus { services.backendStatus }
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    // Language-neutral tokens, exactly like a real game module. The fixture uses
    // the shared Host keys here; a module with its own namespace registers a
    // resolver instead. Core requires neither shape to know the module.
    var statusTitle: TrainerTextToken {
        TrainerTextToken(key: connected ? "host.connected" : "host.disconnected")
    }
    var connectionDetailText: TrainerTextToken { TrainerTextToken(key: "host.gameLibrary") }
    var hostActionsEnabled: Bool {
        backendAvailable && !busy && backendStatus.protocolCompatible
    }

    init(services: TrainerModuleServices) {
        self.services = services
        statusObserver = backendSession.observeStatus { [weak self] _, _ in
            self?.objectWillChange.send()
        }
    }

    isolated deinit {
        if let statusObserver { services.session.removeStatusObserver(statusObserver) }
    }

    func connectFromHost(reason: TrainerHostConnectReason) {
        guard !connected, hostActionsEnabled else { return }
        send("connect", operation: "host.connectGame")
    }

    func disconnectFromHost() {
        guard connected, hostActionsEnabled else { return }
        send("disconnect", operation: "host.disconnectGame")
    }

    func backendDidStart() { refreshFromHost() }

    func refreshFromHost() {
        send("status", operation: "host.refreshStatus", announceSuccess: false)
    }

    func setEnabled(_ value: Bool) {
        send("set_enabled", params: ["value": value], operation: value ? "host.feature.enable" : "host.feature.disable")
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

    /// Connection state describes the target that was running when the request
    /// began. This backend reports no process identifier; a backend that
    /// attaches to a process should report it and return `.process`.
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget {
        payload["connected"] is Bool ? .lifetime : .independent
    }

    func applyBackendPayload(_ payload: [String: Any]) {
        if let connected = payload["connected"] as? Bool {
            self.connected = connected
        }
        if let enabled = payload["enabled"] as? Bool {
            self.enabled = enabled
        }
    }

    func backendDidStop() {
        connected = false
        enabled = false
    }
}

@MainActor
enum ReferenceFixtureLocalizationProbe {
    static func hostGameLibrary(using localization: TrainerLocalizationStore) -> String {
        localization.localized("host.gameLibrary")
    }

    static func hostConnectionStatus(
        connected: Bool,
        using localization: TrainerLocalizationStore
    ) -> String {
        localization.presentation(connected ? "host.connected" : "host.disconnected")
    }
}

struct ReferenceFixtureContent: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @ObservedObject var model: ReferenceFixtureModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(ReferenceFixtureLocalizationProbe.hostGameLibrary(using: localization))
                .font(.caption)
                .foregroundStyle(.secondary)
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
}

struct ReferenceFixtureGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "checkmark.seal",
        headerTitle: "REFERENCE"
    )

    static func makeModel(services: TrainerModuleServices) -> ReferenceFixtureModel {
        ReferenceFixtureModel(services: services)
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

    static func makeManagementCommands(
        model: ReferenceFixtureModel,
        localization: TrainerLocalizationStore
    ) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }

    // A module owns its own key namespace. This fixture uses a prefix of its own
    // rather than a real game module's, which is what proves the seam is generic.
    static let presentationKeyPrefix = "referenceFixture."

    static func presentationText(
        key: String,
        arguments: [String],
        language: TrainerPresentationLanguage
    ) -> String {
        let tables: [String: [TrainerPresentationLanguage: String]] = [
            "referenceFixture.connected": [.zhCN: "夹具已连接", .en: "Fixture Connected"],
            "referenceFixture.operable": [.zhCN: "夹具可操作", .en: "Fixture Ready"],
            // The key the fixture backend emits on a typed failure. It lives in
            // this module's own namespace so the fixture proves the seam end to
            // end: key -> module table -> text, not just a wire shape.
            "referenceFixture.error.failed": [.zhCN: "夹具请求失败（{0}，{1}）。", .en: "Fixture request failed ({0}, {1})."],
        ]
        guard let template = tables[key]?[language] else { return key }
        var value = template
        for (index, argument) in arguments.enumerated() {
            value = value.replacingOccurrences(of: "{\(index)}", with: argument)
        }
        return value
    }
}
