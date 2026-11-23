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
            context.openSaveManagement(localization: localization, theme: theme)
        })
    }

    var body: some View {
        TrainerWorkbenchViewport(navigation: context.navigation) {
            VStack(alignment: .leading, spacing: theme.pageSpacing) {
                if let search = Module.workbenchSearch(model: model) {
                    TrainerHostWorkbenchSearch(catalog: search)
                }
                Module.makeContent(model: model)
                    .environment(\.trainerManagementActions, managementActions)
                    .environment(\.trainerManagementGroups,
                                 context.managementGroups(localization: localization, theme: theme))
            }
            .frame(minWidth: theme.contentMinWidth, maxWidth: .infinity, minHeight: theme.contentMinHeight, alignment: .topLeading)
        } feedback: {
            TrainerHostOperationFeedback(feedback: context.feedback)
        }
        .environment(\.trainerToolWindows, toolWindows.actions(localization: localization, theme: theme))
        .environment(\.trainerGamePageVisibility, context.pageVisibility)
        .onAppear {
            targetMonitor.refresh()
        }
    }
}

package struct TrainerHostSidebarSections: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    @Environment(\.trainerSelectedSection) private var selectedSection
    let sections: [TrainerWorkbenchSectionItem]
    let feedback: TrainerFeedbackCenter
    let diagnostics: TrainerDiagnosticsService

    package init(
        sections: [TrainerWorkbenchSectionItem],
        feedback: TrainerFeedbackCenter,
        diagnostics: TrainerDiagnosticsService
    ) {
        self.sections = sections
        self.feedback = feedback
        self.diagnostics = diagnostics
    }

    package var body: some View {
        if !sections.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Divider().padding(.vertical, 2)
                ForEach(sections) { section in
                    if section.separatedFromPrevious { Divider().padding(.vertical, 2) }
                    let button = TrainerSectionButton(
                        title: localization.string(section.titleKey),
                        systemImage: section.icon,
                        selected: selectedSection == section.id
                            || (selectedSection == nil && section.id == sections.first?.id)
                    ) {
                        section.onSelect?()
                        navigate(section.id)
                    }
                    .accessibilityIdentifier("trainer.section.\(section.id)")
                    if let shortcut = section.keyboardShortcut {
                        button.keyboardShortcut(shortcut)
                    } else {
                        button
                    }
                }
                TrainerHostSidebarIssuesEntry(feedback: feedback, diagnostics: diagnostics)
            }
        } else {
            TrainerHostSidebarIssuesEntry(feedback: feedback, diagnostics: diagnostics)
        }
    }
}

package struct TrainerHostWorkbenchSearch: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    let catalog: TrainerWorkbenchSearchCatalog

    package init(catalog: TrainerWorkbenchSearchCatalog) {
        self.catalog = catalog
    }

    package var body: some View {
        TrainerWorkbenchSearchField(
            text: catalog.query,
            placeholder: localization.string(catalog.placeholderKey),
            clearLabel: localization.localized("host.search.clear"),
            emptyLabel: localization.string(catalog.emptyLabelKey),
            search: { query in catalog.search(query, localization) },
            title: { $0.title },
            detail: { $0.detail },
            icon: { $0.icon },
            onNavigate: { result in
                result.onNavigate()
                navigate(result.sectionID)
            }
        )
    }
}

struct TrainerHostSidebarCard<Module: TrainerGameModule>: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @ObservedObject private var context: TrainerGameContext<Module>
    private var model: Module.Model { context.model }
    private var targetMonitor: TrainerTargetProcessMonitor { context.targetMonitor }
    @ObservedObject private var navigation: TrainerSectionNavigation
    let selected: Bool
    let onSelect: () -> Void

    init(context: TrainerGameContext<Module>, selected: Bool, onSelect: @escaping () -> Void) {
        _context = ObservedObject(wrappedValue: context)
        _navigation = ObservedObject(wrappedValue: context.navigation)
        self.selected = selected
        self.onSelect = onSelect
    }

    private var launchAction: (@MainActor () -> Void)? {
        guard let launch = model.launchActionFromHost else { return nil }
        return {
            // Retain the existing owner and refresh before choosing launch or
            // connection; sidebar animation does not choose either action.
            targetMonitor.refresh()
            if targetMonitor.isRunning { context.performConnectionAction() }
            else { launch() }
        }
    }

    var body: some View {
        TrainerSidebarCard(
            descriptor: Module.descriptor, presentation: Module.presentation,
            connected: model.connected, busy: context.backendStatus.busy, targetRunning: context.services.targetObservation.isRunning,
            operationToken: context.backendStatus.operation, statusToken: model.statusTitle,
            detailToken: model.connectionDetailText, selected: selected, onSelect: onSelect
        ) {
            context.connectionStatusCard(onLaunch: launchAction)
            TrainerHostSidebarSections(
                sections: Module.workbenchSections(model: model),
                feedback: context.feedback,
                diagnostics: context.services.diagnostics
            )
        }
        .environment(\.trainerNavigateToSection, navigation.navigate)
        .environment(\.trainerSelectedSection, navigation.selection)
        .environment(\.trainerToolWindows, context.toolWindows.actions(localization: localization, theme: theme))
        .environment(\.trainerGamePageVisibility, context.pageVisibility)
    }
}
