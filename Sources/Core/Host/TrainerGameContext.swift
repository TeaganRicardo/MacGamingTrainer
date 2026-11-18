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
    let session: TrainerBackendSession
    let targetMonitor: TrainerTargetProcessMonitor
    let saveManager: TrainerSaveManagerModel
    let toolWindows = TrainerToolWindowStore()
    let navigation = TrainerSectionNavigation()
    let pageVisibility = TrainerGamePageVisibility()
    private var ownership: TrainerTargetOwnership?
    private var connectionPolicy = TrainerConnectionPolicy()
    private var subscriptions: Set<AnyCancellable> = []
    private var previousTarget: TrainerTargetObservation
    private var lastKnownTargetProcessIdentifier: pid_t?
    private var previousBackendAvailable: Bool
    private var previousConnected: Bool
    private var terminationRequested = false

    package convenience init() {
        let ownership = TrainerApplicationStartup.requireOwnership(
            targetProcessName: Module.descriptor.targetProcessName,
            targetBundleIdentifier: Module.descriptor.targetBundleIdentifier,
            executablePathSuffix: Module.descriptor.targetExecutablePathSuffix
        )
        let session = TrainerBackendSession()
        self.init(model: Module.makeModel(session: session), session: session)
        self.ownership = ownership
    }

    init(model: Module.Model, session: TrainerBackendSession) {
        self.model = model
        self.session = session
        saveManager = TrainerSaveManagerModel(session: session)
        targetMonitor = TrainerTargetProcessMonitor(
            processName: Module.descriptor.targetProcessName,
            bundleIdentifier: Module.descriptor.targetBundleIdentifier,
            executablePathSuffix: Module.descriptor.targetExecutablePathSuffix
        )
        previousTarget = targetMonitor.targetObservation
        lastKnownTargetProcessIdentifier = previousTarget.processIdentifier
        // This tracks the availability processed by this Context. A module
        // can finish starting before the Context installs its subscription.
        previousBackendAvailable = false
        previousConnected = model.connected
        model.hostTargetLifetimeChanged(observation: previousTarget)
        connectionPolicy.observeTarget(running: previousTarget.isRunning, launchGeneration: previousTarget.launchGeneration)
        model.objectWillChange.receive(on: DispatchQueue.main).sink { [weak self] _ in
            self?.modelChanged()
        }.store(in: &subscriptions)
        targetMonitor.$targetObservation.dropFirst().sink { [weak self] observed in
            self?.targetChanged(observed)
        }.store(in: &subscriptions)
        targetMonitor.$activationGeneration.dropFirst().sink { [weak self] _ in
            guard self?.terminationRequested == false else { return }
            self?.connectionPolicy.targetActivated()
        }.store(in: &subscriptions)
        saveManager.objectWillChange.receive(on: DispatchQueue.main).sink { [weak self] _ in
            self?.objectWillChange.send()
        }.store(in: &subscriptions)
        NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification).sink { [weak self] _ in
            self?.applicationBecameActive()
        }.store(in: &subscriptions)
        // Reuse the transition owner once for an already-running backend.
        // Leave an unavailable module's startup/recovery lifecycle unchanged.
        if model.backendAvailable { modelChanged() }
    }

    var canTerminate: Bool { !model.busy && !saveManager.busy && toolWindows.canCloseAll }

    /// Host-owned backend recovery eligibility for both the automatic restart
    /// opportunity and the connection card's restart action. It reads the
    /// session directly instead of a module request gate such as
    /// `hostActionsEnabled`, which is false precisely while the backend is
    /// unavailable. An incompatible protocol would fail again with the same
    /// backend, and quit owns the session from its first step. Restarting the
    /// worker never clears the session's unknown-outcome target trust gate.
    /// A session whose startup never recorded a configuration cannot restart.
    var backendRestartAllowed: Bool {
        let status = session.currentStatus
        return !terminationRequested && session.canRestart && !status.busy && status.protocolCompatible
    }

    /// Consumes the pending automatic backend-restart opportunity with the
    /// Host-owned eligibility. Callers apply the foreground/launch and
    /// unknown-outcome gates of `reconcileAutomaticConnection` first.
    func consumeAutomaticBackendRestart() -> Bool {
        guard connectionPolicy.consumeAutomaticBackendRestartIfEligible(
            backendAvailable: model.backendAvailable, busy: model.busy, recoveryAllowed: backendRestartAllowed
        ) else { return false }
        model.restartBackendFromHost()
        return true
    }

    /// The sidebar connection card's single production composition. The module
    /// request gate governs connect/launch/refresh; restart uses Host eligibility.
    func connectionStatusCard(onLaunch: (() -> Void)?) -> TrainerConnectionStatusCard {
        TrainerConnectionStatusCard(
            connected: model.connected,
            backendAvailable: model.backendAvailable,
            actionsEnabled: model.hostActionsEnabled,
            restartEnabled: backendRestartAllowed,
            onRefresh: { [targetMonitor, model] in
                targetMonitor.refresh()
                model.refreshFromHost()
            },
            onPrimary: toggleConnection,
            onRestart: model.restartBackendFromHost,
            targetRunning: targetMonitor.isRunning,
            onLaunch: onLaunch
        )
    }

    func toggleConnection() {
        guard !terminationRequested else { return }
        connectionPolicy.userWillToggleConnection(currentlyConnected: model.connected)
        model.toggleConnectionFromHost()
    }

    func registerPresentation(_ localization: TrainerLocalizationStore) {
        localization.registerModulePresentation(prefix: Module.presentationKeyPrefix) { key, arguments, language in
            Module.presentationText(key: key, arguments: arguments, language: language)
        }
    }

    private func modelChanged() {
        guard !terminationRequested else { objectWillChange.send(); return }
        if model.backendAvailable != previousBackendAvailable {
            previousBackendAvailable = model.backendAvailable
            if model.backendAvailable {
                connectionPolicy.backendBecameAvailable()
                if Module.descriptor.supportsSaveManagement, !targetMonitor.isRunning {
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
        guard !terminationRequested else { return }
        let previous = previousTarget
        previousTarget = observed
        let pidChanged = previous.processIdentifier != observed.processIdentifier
        if observed.launchGeneration != previous.launchGeneration ||
            (lastKnownTargetProcessIdentifier != nil && observed.processIdentifier != nil &&
             lastKnownTargetProcessIdentifier != observed.processIdentifier) {
            session.targetLifetimeChanged()
        }
        if let pid = observed.processIdentifier { lastKnownTargetProcessIdentifier = pid }
        if observed.launchGeneration != previous.launchGeneration || pidChanged ||
            (previous.isRunning && !observed.isRunning) {
            model.hostTargetLifetimeChanged(observation: observed)
        }
        if previous.isRunning && observed.isRunning && pidChanged &&
            observed.launchGeneration == previous.launchGeneration {
            connectionPolicy.targetStateChanged(running: false, allowAutomaticConnect: false)
        }
        connectionPolicy.observeTarget(
            running: observed.isRunning, launchGeneration: observed.launchGeneration,
            allowDiscoveryConnect: false
        )
        if !observed.isRunning, Module.descriptor.supportsSaveManagement, model.backendAvailable {
            saveManager.applyStagedIfPossible()
        }
        reconcileAutomaticConnection()
        objectWillChange.send()
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
        guard !terminationRequested, !session.currentStatus.requiresTargetRestart else { return }
        if connectionPolicy.consumeTargetExitRefreshIfEligible(
            backendAvailable: model.backendAvailable, busy: model.busy, connected: model.connected
        ) {
            model.refreshFromHost()
            return
        }
        guard connectionPolicy.backgroundConnectionAllowed || NSApp.isActive else { return }
        if consumeAutomaticBackendRestart() { return }
        let targetJustLaunched = connectionPolicy.backgroundConnectionAllowed
        guard connectionPolicy.consumeAutomaticConnectIfEligible(
            backendAvailable: model.backendAvailable, busy: model.busy,
            connected: model.connected, actionsEnabled: model.hostActionsEnabled
        ) else { return }
        model.connectAutomaticallyFromHost(targetJustLaunched: targetJustLaunched)
    }

    func beginTermination() {
        terminationRequested = true
        session.beginTermination()
        model.beginTerminationFromHost()
        toolWindows.setInteractionEnabled(false)
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
        terminate = context.model.prepareForTermination
        closeWindows = context.toolWindows.closeAll
        suspendInteraction = context.beginTermination
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

    package init(contexts: [AnyTrainerGameContext]) {
        precondition(!contexts.isEmpty)
        self.contexts = contexts
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
