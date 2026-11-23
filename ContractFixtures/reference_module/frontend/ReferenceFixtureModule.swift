import Foundation
import SwiftUI
import TrainerCore

enum ReferenceFixturePresentation {
    private static let table = TrainerModuleStringTable(
        moduleID: ReferenceFixtureGameModule.descriptor.id,
        resolveArgumentKeys: true
    )

    static func text(
        _ key: String,
        arguments: [String] = [],
        language: TrainerPresentationLanguage
    ) -> String {
        table.string(key, language: language, arguments: arguments)
    }
}

enum ReferenceFixtureShortcutAction: String, CaseIterable {
    case toggleFeature
    case disableAll

    var labelKey: String {
        "referenceFixture.shortcut.\(rawValue)"
    }

    var icon: String {
        switch self {
        case .toggleFeature: TrainerSemanticIcon.Concept.controls
        case .disableAll: TrainerSemanticIcon.Tool.disableAll
        }
    }

    var isEditable: Bool {
        self != .disableAll
    }
}

struct ReferenceFixtureShortcutStore {
    static let orderedActions: [ReferenceFixtureShortcutAction] = [.toggleFeature, .disableAll]
    private var core: TrainerShortcutStore<ReferenceFixtureShortcutAction>

    static func defaultLayout() -> [ReferenceFixtureShortcutAction: HotkeyChord] {
        TrainerHotkeyLayout.defaultLayout(
            orderedActions: orderedActions,
            dedicated: [.disableAll: TrainerHotkeyLayout.disableAllChord]
        )
    }

    init(defaults: UserDefaults = .standard) {
        self.core = TrainerShortcutStore(
            orderedActions: Self.orderedActions,
            defaultLayout: Self.defaultLayout(),
            lockedActions: [.disableAll: TrainerHotkeyLayout.disableAllChord],
            storage: TrainerShortcutStorage(
                moduleID: ReferenceFixtureGameModule.descriptor.id,
                defaults: defaults
            )
        )
    }

    func chord(_ action: ReferenceFixtureShortcutAction) -> HotkeyChord {
        core.chord(action)
    }

    mutating func set(_ action: ReferenceFixtureShortcutAction, chord proposed: HotkeyChord) -> ReferenceFixtureShortcutAction? {
        core.set(action, chord: proposed)
    }

    mutating func reset() {
        core.reset()
    }

    func payload() -> [String: Any] {
        core.payload()
    }

    @discardableResult
    mutating func applyProfile(_ values: [String: Any]) -> TrainerShortcutProfileApplyResult {
        core.applyProfile(values)
    }
}

struct ReferenceFixtureProfile: Decodable, Identifiable, Equatable {
    let name: String
    let updatedAt: String
    var id: String { name }
}

enum ReferenceFixtureRequest {
    case status
    case connect
    case disconnect
    case setEnabled(Bool)
    case disableAll
    case listProfiles
    case saveProfile(name: String, shortcuts: [String: Any])
    case loadProfile(name: String)
    case deleteProfile(name: String)
    case diagnostics
    case fail

    var command: ReferenceFixtureCommand {
        switch self {
        case .status: .status
        case .connect: .connect
        case .disconnect: .disconnect
        case .setEnabled: .setEnabled
        case .disableAll: .disableAll
        case .listProfiles: .listProfiles
        case .saveProfile: .saveProfile
        case .loadProfile: .loadProfile
        case .deleteProfile: .deleteProfile
        case .diagnostics: .diagnostics
        case .fail: .fail
        }
    }

    var params: [String: Any] {
        switch self {
        case .setEnabled(let value):
            return ["value": value]
        case .saveProfile(let name, let shortcuts):
            return ["name": name, "shortcuts": shortcuts]
        case .loadProfile(let name), .deleteProfile(let name):
            return ["name": name]
        case .status, .connect, .disconnect, .disableAll, .listProfiles, .diagnostics, .fail:
            return [:]
        }
    }
}

final class ReferenceFixtureModel: ObservableObject, TrainerHostModel {
    @Published private(set) var connected = false
    @Published private(set) var enabled = false
    @Published private(set) var profiles: [ReferenceFixtureProfile] = []
    @Published private(set) var diagnostics: [TrainerDiagnosticCheck] = []
    @Published private(set) var shortcutRevision = 0
    @Published private(set) var shortcutRegistrationFailure: TrainerHotkeyRegistrationFailure?
    @Published private(set) var profileShortcutWarning: TrainerTextToken?
    @Published private(set) var sampleIssueArgument: String?
    @Published var shortcutSettingsPresented = false
    @Published var profilesPresented = false
    @Published var diagnosticsPresented = false

    private let services: TrainerModuleServices
    private var statusObserver: UUID?
    private var shortcuts: ReferenceFixtureShortcutStore
    private var diagnosticsReport: [String: Any]?
    private lazy var hotkeys = services.makeHotkeys(registrationChanged: { [weak self] failure in
        self?.shortcutRegistrationFailure = failure
    }) { [weak self] action in
        self?.performShortcut(action)
    }

    private var backendSession: TrainerBackendSession { services.session }
    var feedbackCenter: TrainerFeedbackCenter { services.feedback }
    var diagnosticsService: TrainerDiagnosticsService { services.diagnostics }
    var backendStatus: TrainerBackendStatus { services.backendStatus }
    var backendAvailable: Bool { backendStatus.backendAvailable }
    var busy: Bool { backendStatus.busy }
    var canUseBackend: Bool { backendAvailable && backendStatus.protocolCompatible }

    // Language-neutral tokens resolved against the Host / module presentation layer.
    var statusTitle: TrainerTextToken {
        TrainerTextToken(key: connected ? "host.connected" : "host.disconnected")
    }
    var connectionDetailText: TrainerTextToken { TrainerTextToken(key: "host.gameLibrary") }
    var hostActionsEnabled: Bool { canUseBackend && !busy }
    var canAcceptRuntimeAction: Bool { !busy && !backendStatus.requiresTargetRestart }

    var hostCurrentIssues: [TrainerCurrentIssue] {
        guard let sampleIssueArgument else { return [] }
        return [
            TrainerCurrentIssue(
                id: "referenceFixture.sampleIssue",
                text: TrainerTextToken(key: "referenceFixture.issue.sample", arguments: [sampleIssueArgument])
            ),
        ]
    }

    init(services: TrainerModuleServices, defaults: UserDefaults = .standard) {
        self.services = services
        self.shortcuts = ReferenceFixtureShortcutStore(defaults: defaults)
        statusObserver = backendSession.observeStatus { [weak self] _, _ in
            self?.objectWillChange.send()
        }
        installShortcuts()
    }

    isolated deinit {
        if let statusObserver { services.session.removeStatusObserver(statusObserver) }
    }

    func connectFromHost(reason: TrainerHostConnectReason) {
        guard !connected, hostActionsEnabled else { return }
        send(.connect, operation: "host.connectGame")
    }

    func disconnectFromHost() {
        guard connected, hostActionsEnabled else { return }
        send(.disconnect, operation: "host.disconnectGame")
    }

    func backendDidStart() { refreshFromHost() }

    func refreshFromHost() {
        send(.status, operation: "host.refreshStatus", announceSuccess: false)
    }

    func setEnabled(_ value: Bool) {
        send(
            .setEnabled(value),
            operation: value ? "host.feature.enable" : "host.feature.disable"
        )
    }

    func disableAll() {
        guard hostActionsEnabled else { return }
        send(.disableAll, operation: "host.disableAll")
    }

    func listProfiles() {
        send(.listProfiles, operation: "referenceFixture.manage.profiles", announceSuccess: false)
    }

    func saveProfile(_ name: String, completion: ((Bool) -> Void)? = nil) {
        send(
            .saveProfile(name: name, shortcuts: shortcuts.payload()),
            operation: "referenceFixture.profile.save",
            completion: completion
        )
    }

    func loadProfile(_ name: String) {
        profileShortcutWarning = nil
        send(.loadProfile(name: name), operation: "referenceFixture.profile.load")
    }

    func deleteProfile(_ name: String) {
        send(.deleteProfile(name: name), operation: "host.delete")
    }

    func clearProfileShortcutWarning() {
        profileShortcutWarning = nil
    }

    func runDiagnostics() {
        send(.diagnostics, operation: "referenceFixture.manage.diagnostics", announceSuccess: false)
    }

    func exportDiagnostics(saveHandler: TrainerDiagnosticsService.ExportSaveHandler? = nil) {
        backendSession.flushDiagnostics()
        services.logSink.flush()
        send(
            .diagnostics,
            operation: "referenceFixture.diagnostics.export",
            announceSuccess: false
        ) { [weak self] ok in
            guard ok, let self, let report = self.diagnosticsReport else { return }
            self.services.diagnostics.exportReport(report, saveHandler: saveHandler)
        }
    }

    func reportSampleFeedback(argument: String, tone: TrainerFeedbackTone = .warning) {
        sampleIssueArgument = argument
        services.feedback.syncCurrentIssues()
        services.feedback.present("referenceFixture.issue.sample", arguments: [argument], tone: tone)
    }

    func clearSampleFeedback() {
        sampleIssueArgument = nil
        services.feedback.syncCurrentIssues()
        services.feedback.clearNotice()
    }

    func shortcutText(_ action: ReferenceFixtureShortcutAction) -> String {
        shortcuts.chord(action).displayText
    }

    @discardableResult
    func setShortcut(_ action: ReferenceFixtureShortcutAction, chord: HotkeyChord) -> TrainerShortcutAssignmentResult {
        if let conflict = shortcuts.set(action, chord: chord) {
            return .conflict(actionID: conflict.rawValue)
        }
        shortcutRevision += 1
        installShortcuts()
        return .applied
    }

    func resetShortcuts() {
        shortcuts.reset()
        shortcutRevision += 1
        installShortcuts()
    }

    private func installShortcuts() {
        hotkeys.register(
            ReferenceFixtureShortcutStore.orderedActions.map {
                HotkeyBinding(actionID: $0.rawValue, chord: shortcuts.chord($0))
            }
        )
    }

    private func performShortcut(_ rawValue: String) {
        guard !shortcutSettingsPresented, let action = ReferenceFixtureShortcutAction(rawValue: rawValue) else {
            return
        }
        switch action {
        case .toggleFeature:
            guard hostActionsEnabled else { return }
            setEnabled(!enabled)
        case .disableAll:
            disableAll()
        }
    }

    func send(
        _ request: ReferenceFixtureRequest,
        operation: String,
        announceSuccess: Bool = true,
        completion: ((Bool) -> Void)? = nil
    ) {
        backendSession.send(
            request.command.rawValue,
            params: request.params,
            operation: operation,
            announceSuccess: announceSuccess,
            timeout: request.command.timeout,
            requiresTrustedTarget: request.command.requiresTrustedTarget(connected: connected),
            completion: completion
        )
    }

    /// Connection state describes the target that was running when the request
    /// began. This backend reports no process identifier; a backend that
    /// attaches to a process should report it and return `.process`.
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget {
        payload["connected"] is Bool ? .lifetime : .independent
    }

    /// The rejected reply described an earlier target. Read the state again
    /// under the current one rather than keep showing what it replaced.
    func applyStaleBackendPayload(_ payload: [String: Any]) {
        refreshFromHost()
    }

    func applyBackendPayload(_ payload: [String: Any]) {
        if let rows = payload["profiles"],
           let data = try? JSONSerialization.data(withJSONObject: rows),
           let decoded = try? JSONDecoder().decode([ReferenceFixtureProfile].self, from: data)
        {
            profiles = decoded
        }
        if let profileShortcuts = payload["shortcuts"] as? [String: Any] {
            switch shortcuts.applyProfile(profileShortcuts) {
            case .applied:
                profileShortcutWarning = nil
                shortcutRevision += 1
                installShortcuts()
            case .unsupportedLayoutVersion(let version):
                profileShortcutWarning = TrainerTextToken(
                    key: "referenceFixture.error.profileShortcutLayoutUnsupported",
                    arguments: [String(version)]
                )
            }
        }
        if let report = payload["diagnostics"] as? [String: Any],
           let checks = report["checks"] as? [[String: Any]]
        {
            diagnostics = checks.compactMap(TrainerDiagnosticCheck.decode)
            diagnosticsReport = report
        }
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
        diagnosticsReport = nil
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
    @Environment(\.trainerManagementGroups) private var managementGroups
    @ObservedObject var model: ReferenceFixtureModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(ReferenceFixtureLocalizationProbe.hostGameLibrary(using: localization))
                .font(.caption)
                .foregroundStyle(.secondary)
            TrainerFeatureToggleRow(
                title: localization.string(ReferenceFixtureShortcutAction.toggleFeature.labelKey),
                icon: ReferenceFixtureShortcutAction.toggleFeature.icon,
                state: TrainerFeatureControlState(
                    isOn: model.enabled,
                    isInteractive: model.backendAvailable && !model.busy,
                    canEditValue: false,
                    opacity: 1,
                    indicatorColor: .accentColor,
                    helpText: "",
                    isWarning: false
                ),
                shortcutText: model.shortcutText(.toggleFeature)
            ) {
                model.setEnabled(!model.enabled)
            }
            .trainerSectionTarget("referenceFixture.main")
            TrainerManagementGroups(groups: managementGroups)
                .trainerPanel()
                .trainerSectionTarget("referenceFixture.management")
        }
        .sheet(isPresented: $model.shortcutSettingsPresented) {
            ReferenceFixtureShortcutSettingsView(model: model)
        }
        .sheet(isPresented: $model.profilesPresented) {
            ReferenceFixtureProfileManagerView(model: model)
        }
        .sheet(isPresented: $model.diagnosticsPresented) {
            ReferenceFixtureDiagnosticsView(model: model)
        }
        .background {
            TrainerGamePageVisibilityObserver { visible in
                if !visible {
                    model.shortcutSettingsPresented = false
                    model.profilesPresented = false
                    model.diagnosticsPresented = false
                }
            }
        }
    }
}

private struct ReferenceFixtureShortcutSettingsView: View {
    @ObservedObject var model: ReferenceFixtureModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    var body: some View {
        TrainerShortcutSettingsView(
            isPresented: $model.shortcutSettingsPresented,
            entries: ReferenceFixtureShortcutStore.orderedActions.map { action in
                TrainerShortcutSettingsEntry(
                    id: action.rawValue,
                    title: localization.string(action.labelKey),
                    icon: action.icon,
                    chordText: model.shortcutText(action),
                    isEditable: action.isEditable
                )
            },
            registrationFailure: model.shortcutRegistrationFailure,
            resetTitle: localization.localized("host.hotkeys.resetDefaults"),
            onReset: model.resetShortcuts,
            onAssign: { actionID, chord in
                guard let action = ReferenceFixtureShortcutAction(rawValue: actionID) else {
                    return .rejected(messageKey: "host.hotkeys.unrecognized")
                }
                return model.setShortcut(action, chord: chord)
            }
        )
    }
}

private struct ReferenceFixtureProfileManagerView: View {
    @ObservedObject var model: ReferenceFixtureModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String { localization.string(key) }

    private var errorText: String {
        let key = model.backendStatus.error
        return key.isEmpty ? "" : localization.string(key, arguments: model.backendStatus.errorArguments)
    }

    var body: some View {
        TrainerProfileManagerView(
            labels: .init(
                title: text("referenceFixture.manage.profiles"),
                explanation: text("referenceFixture.profile.explanation"),
                name: text("referenceFixture.profile.name"),
                picker: text("referenceFixture.manage.profiles"),
                save: text("referenceFixture.profile.save"),
                load: text("referenceFixture.profile.load"),
                empty: text("referenceFixture.profile.empty")
            ),
            entries: model.profiles.map { .init(name: $0.name, updatedAt: $0.updatedAt) },
            busy: model.busy,
            enabled: model.canUseBackend && model.canAcceptRuntimeAction,
            warning: model.profileShortcutWarning.map { localization.string($0) } ?? "",
            error: errorText,
            actions: .init(
                refresh: model.listProfiles,
                save: { name, completion in model.saveProfile(name, completion: completion) },
                load: model.loadProfile,
                delete: model.deleteProfile,
                dismiss: { model.profilesPresented = false }
            )
        )
        .onDisappear { model.clearProfileShortcutWarning() }
    }
}

private struct ReferenceFixtureDiagnosticsView: View {
    @ObservedObject var model: ReferenceFixtureModel
    @EnvironmentObject private var localization: TrainerLocalizationStore

    private func text(_ key: String) -> String { localization.string(key) }

    private var enabled: Bool { model.canUseBackend && model.canAcceptRuntimeAction }

    private var errorText: String {
        let key = model.backendStatus.error
        return key.isEmpty ? "" : localization.string(key, arguments: model.backendStatus.errorArguments)
    }

    var body: some View {
        TrainerDiagnosticsView(
            labels: .init(
                title: text("referenceFixture.manage.diagnostics"),
                explanation: text("referenceFixture.diagnostics.explanation"),
                refresh: text("referenceFixture.diagnostics.rerun"),
                export: text("referenceFixture.diagnostics.export")
            ),
            checks: model.diagnostics.map { TrainerDiagnosticEntry(check: $0, localization: localization) },
            busy: model.busy,
            canRefresh: enabled,
            canExport: enabled,
            error: errorText,
            actions: .init(
                refresh: model.runDiagnostics,
                export: { model.exportDiagnostics() },
                dismiss: { model.diagnosticsPresented = false }
            )
        )
    }
}

struct ReferenceFixtureGameModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "checkmark.seal"
    )

    static func makeModel(services: TrainerModuleServices) -> ReferenceFixtureModel {
        ReferenceFixtureModel(services: services)
    }

    static func makeContent(model: ReferenceFixtureModel) -> ReferenceFixtureContent {
        ReferenceFixtureContent(model: model)
    }

    static func workbenchSections(model: ReferenceFixtureModel) -> [TrainerWorkbenchSectionItem] {
        [
            TrainerWorkbenchSectionItem(
                id: "referenceFixture.main",
                titleKey: "referenceFixture.section.main",
                icon: TrainerSemanticIcon.Section.general
            ),
            TrainerWorkbenchSectionItem(
                id: "referenceFixture.management",
                titleKey: "referenceFixture.section.management",
                icon: TrainerSemanticIcon.Section.settings,
                separatedFromPrevious: true
            ),
        ]
    }

    static func makeManagementCatalog(
        model: ReferenceFixtureModel,
        localization: TrainerLocalizationStore,
        toolWindows: TrainerToolWindowActions
    ) -> TrainerManagementCatalog? {
        let canUseBackend = { model.canUseBackend }
        let canStartBackendAction = { canUseBackend() && !model.busy }
        return TrainerManagementCatalog(
            refresh: .init(
                .refreshStatus,
                localization: localization,
                enabled: canStartBackendAction,
                action: model.refreshFromHost
            ),
            disableAll: .init(
                .disableAll,
                localization: localization,
                enabled: canStartBackendAction,
                action: model.disableAll
            ),
            profiles: .init(
                id: "profiles",
                title: localization.string("referenceFixture.manage.profiles"),
                icon: TrainerSemanticIcon.Tool.profiles,
                enabled: canStartBackendAction
            ) {
                model.profilesPresented = true
                model.listProfiles()
            },
            shortcuts: .init(.shortcuts, localization: localization) {
                model.shortcutSettingsPresented = true
            },
            diagnostics: .init(
                id: "diagnostics",
                title: localization.string("referenceFixture.manage.diagnostics"),
                icon: TrainerSemanticIcon.Tool.diagnostics,
                enabled: canStartBackendAction
            ) {
                model.diagnosticsPresented = true
                model.runDiagnostics()
            }
        )
    }

    // A module owns its own key namespace and resolves its packaged string
    // table through Core's TrainerModuleStringTable without touching Core.
    static let presentationKeyPrefix = "referenceFixture."

    static func presentationText(
        key: String,
        arguments: [String],
        language: TrainerPresentationLanguage
    ) -> String {
        ReferenceFixturePresentation.text(key, arguments: arguments, language: language)
    }
}
