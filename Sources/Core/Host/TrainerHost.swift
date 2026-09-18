import AppKit
import Combine
import SwiftUI

struct TrainerHostView<Module: TrainerGameModule>: View {
    @Environment(\.trainerTheme) private var theme
    @ObservedObject var model: Module.Model
    @StateObject private var targetMonitor: TrainerTargetProcessMonitor
    @State private var connectionPolicy = TrainerConnectionPolicy()

    init(model: Module.Model) {
        self.model = model
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
        .onChange(of: targetMonitor.activationGeneration) { _, _ in
            connectionPolicy.targetActivated()
            reconcileAutomaticConnection()
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
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            targetMonitor.refresh()
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
        // Attaching LLDB can stop the target for seconds. Never start that work
        // while the trainer is in the background and the player is using the
        // game; lifecycle events retain their pending intent until this app is
        // foreground again.
        guard NSApp.isActive else { return }
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
