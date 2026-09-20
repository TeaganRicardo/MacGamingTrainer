import AppKit
import Combine
import SwiftUI

struct TrainerHostView<Module: TrainerGameModule>: View {
    @Environment(\.trainerTheme) private var theme
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

    var body: some View {
        TrainerShell {
            TrainerSidebar(
                descriptor: Module.descriptor,
                presentation: Module.presentation,
                connected: model.connected
            ) {
                VStack(alignment: .leading, spacing: 16) {
                    Module.makeSidebarActions(model: model)
                    if Module.descriptor.supportsSaveManagement {
                        Button {
                            saveManagerPresented = true
                            saveManager.refresh()
                        } label: {
                            Label("存档管理", systemImage: "externaldrive")
                        }
                        .disabled(!model.backendAvailable || model.busy)
                    }
                }
            }
        } content: {
            VStack(alignment: .leading, spacing: theme.pageSpacing) {
                TrainerPageHeader(title: Module.presentation.headerTitle) {
                    Module.makeHeaderActions(model: model)
                }
                TrainerConnectionStatusCard(
                    busy: model.busy,
                    connected: model.connected,
                    operationText: model.operation,
                    statusText: model.statusTitle,
                    detailText: model.connectionDetailText,
                    backendAvailable: model.backendAvailable,
                    actionsEnabled: model.hostActionsEnabled,
                    onRefresh: model.refreshFromHost,
                    onPrimary: handlePrimaryConnectionAction,
                    onRestart: model.restartBackendFromHost
                )
                Module.makeContent(model: model)
            }
            .frame(minWidth: theme.contentMinWidth, maxWidth: theme.pageMaxWidth, minHeight: theme.contentMinHeight, alignment: .topLeading)
        }
        .onAppear {
            targetMonitor.refresh()
            connectionPolicy.targetStateChanged(running: targetMonitor.isRunning)
            reconcileAutomaticConnection()
        }
        .onChange(of: targetMonitor.isRunning) { _, running in
            connectionPolicy.targetStateChanged(running: running)
            if !running, model.backendAvailable && !model.busy {
                model.refreshFromHost()
            }
            reconcileAutomaticConnection()
        }
        .onChange(of: targetMonitor.launchGeneration) { _, _ in
            // Only a real NSWorkspace launch may grant the one background
            // debugger-attach opportunity. Initial process discovery remains
            // foreground-only.
            connectionPolicy.targetStateChanged(running: targetMonitor.isRunning)
            connectionPolicy.targetLaunched()
            reconcileAutomaticConnection()
        }
        .onChange(of: targetMonitor.activationGeneration) { _, _ in
            // Target activation can arrive before this app's resign-active
            // notification. Record the opportunity only; consume it when the
            // trainer itself becomes foreground again.
            connectionPolicy.targetActivated()
        }
        .onChange(of: model.backendAvailable) { _, available in
            if available { connectionPolicy.backendBecameAvailable() }
            else { connectionPolicy.backendBecameUnavailable() }
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
            connectionPolicy.targetStateChanged(running: targetMonitor.isRunning)
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
        guard connectionPolicy.consumeAutomaticConnectIfEligible(
            backendAvailable: model.backendAvailable,
            busy: model.busy,
            connected: model.connected,
            actionsEnabled: model.hostActionsEnabled
        ) else { return }
        model.toggleConnectionFromHost()
    }
}
