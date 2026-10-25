import AppKit
import Combine
import SwiftUI

struct TrainerHostView<Module: TrainerGameModule>: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    private let context: TrainerGameContext<Module>
    @ObservedObject private var model: Module.Model
    @ObservedObject private var targetMonitor: TrainerTargetProcessMonitor
    @ObservedObject private var saveManager: TrainerSaveManagerModel
    private var toolWindows: TrainerToolWindowStore { context.toolWindows }

    init(context: TrainerGameContext<Module>) {
        self.context = context
        _model = ObservedObject(wrappedValue: context.model)
        _targetMonitor = ObservedObject(wrappedValue: context.targetMonitor)
        _saveManager = ObservedObject(wrappedValue: context.saveManager)
    }

    private var managementActions: TrainerManagementActions {
        guard Module.descriptor.supportsSaveManagement else { return .none }
        return TrainerManagementActions(openSaveManagement: {
            toolWindows.open(id: "host-save-management", title: localization.localized("host.saveManagement"),
                             localization: localization, theme: theme) {
                saveManager.refresh()
                return TrainerToolWindowContent(canClose: { !saveManager.busy }) {
                    TrainerSaveManagerView(model: saveManager, managedBackupEditor:
                        Module.managedBackupEditor.map { factory in { snapshot in factory(model, snapshot) } })
                }
            }
        })
    }

    var body: some View {
        TrainerShell {
            TrainerSidebar(
                descriptor: Module.descriptor,
                presentation: Module.presentation,
                connected: model.connected,
                busy: model.busy,
                targetRunning: targetMonitor.isRunning,
                operationToken: model.operation,
                statusToken: model.statusTitle,
                detailToken: model.connectionDetailText
            ) {
                TrainerConnectionStatusCard(
                    connected: model.connected,
                    backendAvailable: model.backendAvailable,
                    actionsEnabled: model.hostActionsEnabled,
                    onRefresh: model.refreshFromHost,
                    onPrimary: context.toggleConnection,
                    onRestart: model.restartBackendFromHost,
                    targetRunning: targetMonitor.isRunning,
                    onLaunch: model.launchActionFromHost
                )
                Module.makeSidebarActions(model: model)
            }
        } content: {
            VStack(alignment: .leading, spacing: theme.pageSpacing) {
                Module.makeHeaderActions(model: model)
                Module.makeContent(model: model)
                    .environment(\.trainerManagementActions, managementActions)
            }
            .frame(minWidth: theme.contentMinWidth, maxWidth: theme.pageMaxWidth, minHeight: theme.contentMinHeight, alignment: .topLeading)
        } feedback: {
            Module.makeFeedback(model: model)
        }
        .environment(\.trainerToolWindows, toolWindows.actions(localization: localization, theme: theme))
        .onAppear { context.registerPresentation(localization) }
    }
}
