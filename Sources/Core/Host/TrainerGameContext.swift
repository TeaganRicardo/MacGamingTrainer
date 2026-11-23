import AppKit
import Combine
import SwiftUI

@MainActor
final class TrainerGamePageVisibility: ObservableObject {
    @Published private(set) var isVisible = true

    func setVisible(_ visible: Bool) {
        guard isVisible != visible else { return }
        isVisible = visible
    }
}

private struct TrainerGamePageVisibilityKey: EnvironmentKey {
    static let defaultValue: TrainerGamePageVisibility? = nil
}

extension EnvironmentValues {
    var trainerGamePageVisibility: TrainerGamePageVisibility? {
        get { self[TrainerGamePageVisibilityKey.self] }
        set { self[TrainerGamePageVisibilityKey.self] = newValue }
    }
}

/// Subscribe to visibility at the narrowest view that actually needs it.
/// The retained game-page root receives only the stable reference, so switching
/// modules does not invalidate every control in both full workbench trees.
package struct TrainerGamePageVisibilityGate<Content: View>: View {
    @Environment(\.trainerGamePageVisibility) private var visibility
    let content: (Bool) -> Content

    package init(@ViewBuilder content: @escaping (Bool) -> Content) {
        self.content = content
    }

    @ViewBuilder
    package var body: some View {
        if let visibility {
            TrainerObservedGamePageVisibility(visibility: visibility, content: content)
        } else {
            content(true)
        }
    }
}

private struct TrainerObservedGamePageVisibility<Content: View>: View {
    @ObservedObject var visibility: TrainerGamePageVisibility
    let content: (Bool) -> Content

    var body: some View { content(visibility.isVisible) }
}

package struct TrainerGamePageVisibilityObserver: View {
    let onChange: (Bool) -> Void

    package init(onChange: @escaping (Bool) -> Void) {
        self.onChange = onChange
    }

    package var body: some View {
        TrainerGamePageVisibilityGate { visible in
            Color.clear
                .frame(width: 0, height: 0)
                .onChange(of: visible, initial: true) { _, value in onChange(value) }
        }
    }
}

@MainActor
package final class TrainerGameContext<Module: TrainerGameModule>: ObservableObject {
    package let model: Module.Model
    let services: TrainerModuleServices
    let session: TrainerBackendSession
    var feedback: TrainerFeedbackCenter { services.feedback }
    var diagnostics: TrainerDiagnosticsService { services.diagnostics }
    let targetMonitor: TrainerTargetProcessMonitor
    let saveManager: TrainerSaveManagerModel
    let toolWindows = TrainerToolWindowStore()
    let navigation = TrainerSectionNavigation()
    let pageVisibility = TrainerGamePageVisibility()
    private var ownership: TrainerTargetOwnership?
    private var connectionPolicy = TrainerConnectionPolicy()
    private var subscriptions: Set<AnyCancellable> = []
    private var lastKnownTargetProcessIdentifier: pid_t?
    private var previousBackendAvailable: Bool
    private var previousConnected: Bool
    private var terminationRequested = false
    private var registeredStoreIDs: Set<ObjectIdentifier> = []

    package convenience init() {
        let ownership = TrainerApplicationStartup.requireOwnership(
            targetProcessName: Module.descriptor.targetProcessName,
            targetBundleIdentifier: Module.descriptor.targetBundleIdentifier,
            executablePathSuffix: Module.descriptor.targetExecutablePathSuffix
        )
        self.init(session: TrainerBackendSession())
        self.ownership = ownership
    }

    package convenience init(localization: TrainerLocalizationStore) {
        self.init()
        registerPresentation(localization)
    }

    init(
        session: TrainerBackendSession,
        backendScriptURL: URL? = nil,
        logSink: TrainerLogSink? = nil,
        targetMonitor: TrainerTargetProcessMonitor? = nil,
        localization: TrainerLocalizationStore? = nil,
        makeModel: ((TrainerModuleServices) -> Module.Model)? = nil
    ) {
        let descriptor = Module.descriptor
        let monitor = targetMonitor ?? TrainerTargetProcessMonitor(
            processName: descriptor.targetProcessName,
            bundleIdentifier: descriptor.targetBundleIdentifier,
            executablePathSuffix: descriptor.targetExecutablePathSuffix
        )
        self.targetMonitor = monitor
        self.session = session
        saveManager = TrainerSaveManagerModel(session: session)
        services = TrainerModuleServices(
            descriptor: descriptor, session: session,
            logSink: logSink ?? TrainerLogSink(gameID: descriptor.id),
            targetObservation: monitor.targetObservation
        )
        model = (makeModel ?? Module.makeModel)(services)
        services.feedback.setIssueProvider(observing: model) { [weak model] in model?.hostCurrentIssues ?? [] }
        let target = services.targetObservation
        lastKnownTargetProcessIdentifier = target.processIdentifier
        previousBackendAvailable = false
        previousConnected = model.connected
        notifyTargetLifetime(target)
        connectionPolicy.observeTarget(running: target.isRunning, launchGeneration: target.launchGeneration)
        model.objectWillChange.receive(on: DispatchQueue.main).sink { [weak self] _ in
            self?.modelChanged()
        }.store(in: &subscriptions)
        let statusObserver = session.observeStatus { [weak self] _, _ in
            // Session status can become idle mid-reply. Reconcile only after
            // the payload and receipt have reached their owners.
            DispatchQueue.main.async { [weak self] in self?.modelChanged() }
        }
        AnyCancellable { @Sendable [weak session] in
            Task { @MainActor in session?.removeStatusObserver(statusObserver) }
        }.store(in: &subscriptions)
        monitor.$targetObservation.dropFirst().sink { [weak self] observed in
            self?.targetChanged(observed)
        }.store(in: &subscriptions)
        monitor.$activationGeneration.dropFirst().sink { [weak self] _ in
            guard self?.terminationRequested == false else { return }
            self?.connectionPolicy.targetActivated()
        }.store(in: &subscriptions)
        saveManager.objectWillChange.receive(on: DispatchQueue.main).sink { [weak self] _ in
            self?.objectWillChange.send()
        }.store(in: &subscriptions)
        NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification).sink { [weak self] _ in
            self?.applicationBecameActive()
        }.store(in: &subscriptions)
        if let localization {
            registerPresentation(localization)
        }
        if session.isStarted {
            modelChanged()
        } else {
            startBackend(scriptURL: backendScriptURL)
        }
    }

    var backendStatus: TrainerBackendStatus { services.backendStatus }
    var canTerminate: Bool { !backendStatus.busy && !saveManager.busy && toolWindows.canCloseAll }

    private func startBackend(scriptURL: URL?) {
        let logSink = services.logSink
        do {
            try session.start(
                descriptor: services.descriptor,
                backendScriptURL: scriptURL,
                applyPayload: { [weak self] in self?.applyBackendPayload($0) },
                resetGameState: { [weak model, feedback = services.feedback] in
                    feedback.clearNotice()
                    model?.backendDidStop()
                },
                log: { logSink.append($0) },
                backendLog: { logSink.append($0, source: "BACKEND") }
            )
            model.backendDidStart()
        } catch {
            // The session publishes the startup failure and records diagnostics.
        }
    }

    private func applyBackendPayload(_ payload: [String: Any]) {
        let current = services.targetObservation
        let isCurrent: Bool
        switch model.backendPayloadTarget(payload) {
        case .independent:
            isCurrent = true
        case .lifetime:
            isCurrent = session.activeRequestHasCurrentTargetObservation
        case .process(let identifier):
            isCurrent = session.activeRequestHasCurrentTargetObservation && current.isRunning
                && (current.processIdentifier == nil || identifier == current.processIdentifier.map(Int.init))
            if !isCurrent { connectionPolicy.retainTargetExitRefresh() }
        }
        if isCurrent {
            model.applyBackendPayload(payload)
        } else {
            model.applyStaleBackendPayload(payload)
        }
    }

    /// Host-owned backend recovery eligibility for both the automatic restart
    /// opportunity and the connection card's restart action. It reads the
    /// session directly instead of a module request gate such as
    /// `hostActionsEnabled`, which is false precisely while the backend is
    /// unavailable. An incompatible protocol would fail again with the same
    /// backend, and quit owns the session from its first step. Restarting the
    /// worker never clears the session's unknown-outcome target trust gate.
    /// A session whose startup never recorded a configuration cannot restart.
    var backendRestartAllowed: Bool {
        let status = backendStatus
        return !terminationRequested && session.canRestart && !status.busy && status.protocolCompatible
    }

    func restartBackend() {
        guard backendRestartAllowed else { return }
        model.backendWillRestart()
        session.restart()
    }

    /// The sidebar connection card's single production composition. The module
    /// request gate governs connect/launch/refresh; restart uses Host eligibility.
    func connectionStatusCard(onLaunch: (@MainActor () -> Void)?) -> TrainerConnectionStatusCard {
        TrainerConnectionStatusCard(
            connected: model.connected,
            backendAvailable: backendStatus.backendAvailable,
            actionsEnabled: model.hostActionsEnabled,
            restartEnabled: backendRestartAllowed,
            onRefresh: { [targetMonitor, model] in
                targetMonitor.refresh()
                model.refreshFromHost()
            },
            onPrimary: performConnectionAction,
            onRestart: restartBackend,
            targetRunning: services.targetObservation.isRunning,
            onLaunch: onLaunch
        )
    }

    func performConnectionAction() {
        guard !terminationRequested else { return }
        if model.connected {
            connectionPolicy.userWillDisconnect()
            model.disconnectFromHost()
        } else {
            connectionPolicy.userWillConnect()
            model.connectFromHost(reason: .manual)
        }
    }

    var canOpenSaveManagementFromHost: Bool {
        let status = backendStatus
        return status.backendAvailable && status.protocolCompatible
            && !terminationRequested && model.canAcceptManagementActionsFromHost
    }

    func openSaveManagement(localization: TrainerLocalizationStore, theme: TrainerTheme) {
        guard Module.descriptor.supportsSaveManagement else { return }
        toolWindows.open(
            id: "host-save-management",
            title: localization.localized("host.saveManagement"),
            localization: localization,
            theme: theme
        ) {
            self.saveManager.refresh()
            return TrainerToolWindowContent(canClose: { !self.saveManager.busy }) {
                TrainerSaveManagerView(
                    model: self.saveManager,
                    managedBackupEditor: Module.managedBackupEditor.map { factory in
                        { snapshot in factory(self.model, snapshot) }
                    }
                )
            }
        }
    }

    package func resolvedManagementCatalog(
        localization: TrainerLocalizationStore,
        theme: TrainerTheme = .standard
    ) -> TrainerManagementCatalog? {
        guard let catalog = Module.makeManagementCatalog(
            model: model,
            localization: localization,
            toolWindows: toolWindows.actions(localization: localization, theme: theme)
        ) else {
            return nil
        }
        let saveManagementAction: TrainerManagementAction? = Module.descriptor.supportsSaveManagement
            ? TrainerManagementAction(
                .saveManagement,
                localization: localization,
                enabled: { [weak self] in self?.canOpenSaveManagementFromHost ?? false },
                action: { [weak self] in self?.openSaveManagement(localization: localization, theme: theme) }
            )
            : nil
        return catalog.resolvingHostDefaults(
            localization: localization,
            diagnostics: services.diagnostics,
            saveManagement: saveManagementAction
        )
    }

    package func managementGroups(
        localization: TrainerLocalizationStore,
        theme: TrainerTheme = .standard
    ) -> [TrainerManagementGroup] {
        resolvedManagementCatalog(localization: localization, theme: theme)?.groups ?? []
    }

    func registerPresentation(_ localization: TrainerLocalizationStore) {
        guard !Module.presentationKeyPrefix.isEmpty else { return }
        guard registeredStoreIDs.insert(ObjectIdentifier(localization)).inserted else { return }
        let registered = localization.registerModulePresentation(prefix: Module.presentationKeyPrefix) { key, arguments, language in
            Module.presentationText(key: key, arguments: arguments, language: language)
        }
        precondition(registered, "Invalid or overlapping module presentation prefix: \(Module.presentationKeyPrefix)")
    }

    private func modelChanged() {
        guard !terminationRequested else { objectWillChange.send(); return }
        let backendAvailable = backendStatus.backendAvailable
        if backendAvailable != previousBackendAvailable {
            previousBackendAvailable = backendAvailable
            if backendAvailable {
                connectionPolicy.backendBecameAvailable()
                if services.descriptor.supportsSaveManagement, !services.targetObservation.isRunning {
                    saveManager.applyStagedIfPossible()
                }
            } else {
                connectionPolicy.backendBecameUnavailable()
            }
        }
        if model.connected != previousConnected {
            previousConnected = model.connected
            connectionPolicy.connectionChanged(connected: model.connected)
        }
        reconcileAutomaticConnection()
        objectWillChange.send()
    }

    private func targetChanged(_ observed: TrainerTargetObservation) {
        let previous = services.targetObservation
        guard previous != observed else { return }
        services.targetObservation = observed
        // Already-admitted replies still settle during quit. Keep validating
        // their observations without scheduling any new lifecycle work.
        guard !terminationRequested else {
            session.invalidateTargetObservation()
            return
        }
        let launched = observed.launchGeneration != previous.launchGeneration
        let pidChanged = previous.processIdentifier != observed.processIdentifier
        let replacement = lastKnownTargetProcessIdentifier != nil && observed.processIdentifier != nil &&
            lastKnownTargetProcessIdentifier != observed.processIdentifier
        if let pid = observed.processIdentifier { lastKnownTargetProcessIdentifier = pid }
        if previous.isRunning && observed.isRunning && pidChanged && !launched {
            connectionPolicy.targetStateChanged(running: false, allowAutomaticConnect: false)
        }
        connectionPolicy.observeTarget(
            running: observed.isRunning, launchGeneration: observed.launchGeneration,
            allowDiscoveryConnect: false
        )
        if model.connected { connectionPolicy.retainTargetExitRefresh() }
        notifyTargetLifetime(observed)
        if launched || replacement {
            session.targetLifetimeChanged()
        } else {
            session.invalidateTargetObservation()
        }
        if !observed.isRunning, services.descriptor.supportsSaveManagement, backendStatus.backendAvailable {
            saveManager.applyStagedIfPossible()
        }
        reconcileAutomaticConnection()
        objectWillChange.send()
    }

    private func notifyTargetLifetime(_ observation: TrainerTargetObservation) {
        services.logSink.targetLifetimeChanged(running: observation.isRunning, identity: .init(
            processName: services.descriptor.targetProcessName,
            bundleIdentifier: services.descriptor.targetBundleIdentifier,
            processIdentifier: observation.processIdentifier
        ))
        model.hostTargetLifetimeChanged(observation: observation)
    }

    private func applicationBecameActive() {
        guard !terminationRequested else { return }
        targetMonitor.refresh()
        connectionPolicy.observeTarget(
            running: targetMonitor.isRunning, launchGeneration: targetMonitor.launchGeneration,
            allowDiscoveryConnect: false
        )
        reconcileAutomaticConnection()
        model.hostDidBecomeActive()
    }

    private func reconcileAutomaticConnection() {
        guard !terminationRequested else { return }
        let status = backendStatus
        switch connectionPolicy.nextAutomaticAction(
            foreground: NSApp?.isActive == true,
            backendAvailable: status.backendAvailable, busy: status.busy,
            connected: model.connected, actionsEnabled: model.hostActionsEnabled,
            recoveryAllowed: backendRestartAllowed, requiresTargetRestart: status.requiresTargetRestart
        ) {
        case .refreshAfterTargetExit:
            model.refreshFromHost()
        case .restartBackend:
            restartBackend()
        case .connect(let targetJustLaunched):
            model.connectFromHost(reason: .automatic(targetJustLaunched: targetJustLaunched))
        case .none:
            break
        }
    }

    func beginTermination() {
        terminationRequested = true
        model.beginTerminationFromHost()
        session.beginTermination()
        toolWindows.setInteractionEnabled(false)
    }

    func prepareForTermination(completion: @escaping () -> Void) {
        model.prepareForTermination { [session, logSink = services.logSink] in
            session.flushDiagnostics()
            session.stop(suppressTerminationError: true)
            logSink.flush()
            completion()
        }
    }
}

@MainActor
package final class AnyTrainerGameContext: ObservableObject, Identifiable {
    package nonisolated let descriptor: GameModuleDescriptor
    package nonisolated var id: String { descriptor.id }
    let content: AnyView
    private let sidebarCard: (Bool, @escaping () -> Void) -> AnyView
    private let setPageVisible: (Bool) -> Void
    private let storage: Any
    private let connectedValue: () -> Bool
    private let canTerminateValue: () -> Bool
    private let terminate: (@escaping () -> Void) -> Void
    private let closeWindows: () -> Void
    private let registerPresentationResolver: (TrainerLocalizationStore) -> Void
    private var subscription: AnyCancellable?

    package init<Module>(_ context: TrainerGameContext<Module>) {
        descriptor = Module.descriptor
        storage = context
        content = AnyView(TrainerHostView(context: context))
        sidebarCard = { selected, onSelect in
            AnyView(TrainerHostSidebarCard(context: context, selected: selected, onSelect: onSelect))
        }
        setPageVisible = { visible in
            context.pageVisibility.setVisible(visible)
            context.navigation.setVisible(visible)
        }
        connectedValue = { context.model.connected }
        canTerminateValue = { context.canTerminate }
        terminate = context.prepareForTermination
        closeWindows = context.toolWindows.closeAll
        suspendInteraction = context.beginTermination
        registerPresentationResolver = context.registerPresentation
        subscription = context.objectWillChange.sink { [weak self] _ in self?.objectWillChange.send() }
    }

    var connected: Bool { connectedValue() }
    var canTerminate: Bool { canTerminateValue() }

    func makeSidebarCard(selected: Bool, onSelect: @escaping () -> Void) -> AnyView {
        sidebarCard(selected, onSelect)
    }
    func pageVisibilityChanged(_ visible: Bool) { setPageVisible(visible) }

    package func typed<Module: TrainerGameModule>(as module: Module.Type) -> TrainerGameContext<Module>? {
        storage as? TrainerGameContext<Module>
    }

    func prepareForTermination(completion: @escaping () -> Void) { terminate(completion) }
    func closeToolWindows() { closeWindows() }
    private let suspendInteraction: () -> Void
    func suspendUserActions() { suspendInteraction() }
    func registerPresentation(_ localization: TrainerLocalizationStore) {
        registerPresentationResolver(localization)
    }
}

@MainActor
package final class TrainerApplicationCoordinator: ObservableObject {
    let contexts: [AnyTrainerGameContext]
    @Published package var selectedGameID: String {
        didSet {
            // Cancel pending navigation synchronously, before SwiftUI updates
            // visibility. A captured old-page callback cannot scroll it later.
            contexts.forEach { $0.pageVisibilityChanged($0.id == selectedGameID) }
            if !terminationRequested { GlobalHotkeys.selectGame(selectedGameID) }
        }
    }
    private var subscriptions: Set<AnyCancellable> = []
    @Published package private(set) var terminationRequested = false
    private var terminationCompletion: (() -> Void)?
    private var nextTerminationIndex = 0
    private var finalizingContext = false
    private var finalizationStarted = false

    package init(contexts: [AnyTrainerGameContext], localization: TrainerLocalizationStore) {
        precondition(!contexts.isEmpty)
        self.contexts = contexts
        contexts.forEach { $0.registerPresentation(localization) }
        selectedGameID = contexts[0].id
        contexts.forEach { $0.pageVisibilityChanged($0.id == selectedGameID) }
        GlobalHotkeys.selectGame(selectedGameID)
        for context in contexts {
            context.objectWillChange.receive(on: DispatchQueue.main).sink { [weak self] _ in
                self?.objectWillChange.send()
                self?.attemptTermination()
            }.store(in: &subscriptions)
        }
    }

    package func context(id: String) -> AnyTrainerGameContext? { contexts.first { $0.id == id } }

    package func prepareForTermination(completion: @escaping () -> Void) {
        terminationCompletion = completion
        terminationRequested = true
        GlobalHotkeys.selectGame(nil)
        contexts.forEach { $0.suspendUserActions() }
        attemptTermination()
    }

    private func attemptTermination() {
        guard terminationCompletion != nil, !finalizingContext else { return }
        if !finalizationStarted {
            guard contexts.allSatisfy(\.canTerminate) else { return }
            finalizationStarted = true
        }
        guard nextTerminationIndex < contexts.count else {
            contexts.forEach { $0.closeToolWindows() }
            let completion = terminationCompletion
            terminationCompletion = nil
            completion?()
            return
        }
        let context = contexts[nextTerminationIndex]
        guard context.canTerminate else { return }
        finalizingContext = true
        context.prepareForTermination { [weak self] in
            guard let self else { return }
            self.finalizingContext = false
            self.nextTerminationIndex += 1
            self.attemptTermination()
        }
    }
}
