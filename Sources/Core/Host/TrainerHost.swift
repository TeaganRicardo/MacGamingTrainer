import AppKit
import Combine
import SwiftUI

struct TrainerHostView<Module: TrainerGameModule>: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @ObservedObject var model: Module.Model
    @StateObject private var targetMonitor: TrainerTargetProcessMonitor
    @StateObject private var saveManager: TrainerSaveManagerModel
    @State private var connectionPolicy = TrainerConnectionPolicy()
    @State private var saveManagerPresented = false

    init(model: Module.Model, session: TrainerBackendSession) {
        self.model = model
        _saveManager = StateObject(wrappedValue: TrainerSaveManagerModel(session: session))
        _targetMonitor = StateObject(wrappedValue: TrainerTargetProcessMonitor(
            processName: Module.descriptor.targetProcessName,
            bundleIdentifier: Module.descriptor.targetBundleIdentifier
        ))
    }

    private var managementActions: TrainerManagementActions {
        guard Module.descriptor.supportsSaveManagement else { return .none }
        return TrainerManagementActions(openSaveManagement: {
            saveManagerPresented = true
            saveManager.refresh()
        })
    }

    /// Register the selected module's presentation namespace before the first
    /// render. Core stores only the resolver closure, so the shell resolves
    /// module tokens without knowing the module's vocabulary, and switching
    /// language re-resolves them live.
    private func registerModulePresentation(_ localization: TrainerLocalizationStore) {
        localization.registerModulePresentation(prefix: Module.presentationKeyPrefix) {
            key, arguments, language in
            Module.presentationText(key: key, arguments: arguments, language: language)
        }
    }

    var body: some View {
        TrainerShell {
            TrainerSidebar(
                descriptor: Module.descriptor,
                presentation: Module.presentation,
                connected: model.connected
            ) {
                Module.makeSidebarActions(model: model)
            }
        } content: {
            VStack(alignment: .leading, spacing: theme.pageSpacing) {
                TrainerPageHeader(title: Module.presentation.headerTitle) {
                    Module.makeHeaderActions(model: model)
                }
                TrainerConnectionStatusCard(
                    busy: model.busy,
                    connected: model.connected,
                    operationToken: model.operation,
                    statusToken: model.statusTitle,
                    detailToken: model.connectionDetailText,
                    backendAvailable: model.backendAvailable,
                    actionsEnabled: model.hostActionsEnabled,
                    onRefresh: model.refreshFromHost,
                    onPrimary: handlePrimaryConnectionAction,
                    onRestart: model.restartBackendFromHost
                )
                Module.makeContent(model: model)
                    .environment(\.trainerManagementActions, managementActions)
            }
            .frame(minWidth: theme.contentMinWidth, maxWidth: theme.pageMaxWidth, minHeight: theme.contentMinHeight, alignment: .topLeading)
        } feedback: {
            Module.makeFeedback(model: model)
        }
        .onAppear {
            registerModulePresentation(localization)
            targetMonitor.refresh()
            connectionPolicy.observeTarget(running: targetMonitor.isRunning, launchGeneration: targetMonitor.launchGeneration)
            reconcileAutomaticConnection()
        }
        .onChange(of: targetMonitor.targetObservation) { previous, observed in
            // One published snapshot carries both presence and launch intent.
            // Notify modules before consuming the Host's connection grant so
            // game-owned readiness from an earlier process cannot be reused.
            if observed.launchGeneration != previous.launchGeneration ||
               (previous.isRunning && !observed.isRunning) {
                model.hostTargetLifetimeChanged(running: observed.isRunning)
            }
            connectionPolicy.observeTarget(
                running: observed.isRunning,
                launchGeneration: observed.launchGeneration,
                allowDiscoveryConnect: false
            )
            if !observed.isRunning, Module.descriptor.supportsSaveManagement, model.backendAvailable {
                saveManager.applyStagedIfPossible()
            }
            reconcileAutomaticConnection()
        }
        .onChange(of: targetMonitor.activationGeneration) { _, _ in
            // Target activation can arrive before this app's resign-active
            // notification. Record the opportunity only; consume it when the
            // trainer itself becomes foreground again.
            connectionPolicy.targetActivated()
        }
        .onChange(of: model.backendAvailable) { _, available in
            if available {
                connectionPolicy.backendBecameAvailable()
                if Module.descriptor.supportsSaveManagement, !targetMonitor.isRunning {
                    saveManager.applyStagedIfPossible()
                }
            } else {
                connectionPolicy.backendBecameUnavailable()
            }
            reconcileAutomaticConnection()
        }
        .onChange(of: model.busy) { _, _ in
            reconcileAutomaticConnection()
        }
        .onChange(of: model.connected) { _, connected in
            connectionPolicy.connectionChanged(connected: connected)
        }
        .sheet(isPresented: $saveManagerPresented) {
            TrainerSaveManagerView(model: saveManager)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            targetMonitor.refresh()
            // Repair policy state synchronously even when the published
            // isRunning value did not change and SwiftUI therefore emits no
            // onChange callback.
            connectionPolicy.observeTarget(
                running: targetMonitor.isRunning,
                launchGeneration: targetMonitor.launchGeneration,
                allowDiscoveryConnect: false
            )
            reconcileAutomaticConnection()
            model.hostDidBecomeActive()
        }
    }

    private func handlePrimaryConnectionAction() {
        connectionPolicy.userWillToggleConnection(currentlyConnected: model.connected)
        model.toggleConnectionFromHost()
    }

    /// Lifecycle events may first recover a missing backend and then connect once
    /// that backend reports available. There is no polling/retry timer: target
    /// launch/activation and backend lifecycle transitions are the only triggers.
    private func reconcileAutomaticConnection() {
        if connectionPolicy.consumeTargetExitRefreshIfEligible(
            backendAvailable: model.backendAvailable,
            busy: model.busy,
            connected: model.connected
        ) {
            model.refreshFromHost()
            return
        }

        // A true target-process launch grants one background connect chance
        // that survives transient Host/backend busy states until consumed.
        // Target activation never grants this, so active gameplay cannot gain
        // a surprise LLDB attach merely from Alt-Tab.
        guard connectionPolicy.backgroundConnectionAllowed || NSApp.isActive else { return }
        if connectionPolicy.consumeAutomaticBackendRestartIfEligible(
            backendAvailable: model.backendAvailable,
            busy: model.busy,
            actionsEnabled: model.hostActionsEnabled
        ) {
            model.restartBackendFromHost()
            return
        }
        let targetJustLaunched = connectionPolicy.backgroundConnectionAllowed
        guard connectionPolicy.consumeAutomaticConnectIfEligible(
            backendAvailable: model.backendAvailable,
            busy: model.busy,
            connected: model.connected,
            actionsEnabled: model.hostActionsEnabled
        ) else { return }
        model.connectAutomaticallyFromHost(targetJustLaunched: targetJustLaunched)
    }
}
