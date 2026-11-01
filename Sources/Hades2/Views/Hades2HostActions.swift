import SwiftUI

struct Hades2SidebarActions: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    @Environment(\.trainerSelectedSection) private var selectedSection
    @Environment(\.trainerGamePageVisible) private var pageVisible

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Divider().padding(.vertical, 2)
            ForEach(Hades2WorkbenchSection.allCases) { section in
                if section == .management { Divider().padding(.vertical, 2) }
                TrainerSectionButton(
                    title: Hades2GameModule.resolveText(key: section.titleKey, localization: localization),
                    systemImage: section.icon,
                    selected: selectedSection == section.id || (selectedSection == nil && section == .values)
                ) {
                    model.showWorkbenchSection(section)
                    navigate(section.id)
                }
                .accessibilityIdentifier("trainer.section.\(section.id)")
            }
            if !model.currentIssues.isEmpty {
                Button { model.showFeedbackDetails() } label: {
                    Label(localization.localized("host.feedback.currentIssues"), systemImage: "exclamationmark.circle")
                        .font(.callout)
                }
                .popover(isPresented: Binding(
                    get: { model.feedbackDetailsPresented },
                    set: { if !$0 { model.closeFeedbackDetails() } }
                )) {
                    Hades2FeedbackDetails(model: model)
                }
            }
        }
        .onChange(of: model.currentIssues) { _, issues in
            if issues.isEmpty { model.closeFeedbackDetails() }
        }
        .onChange(of: pageVisible) { _, visible in
            if !visible { model.closeFeedbackDetails() }
        }
    }
}

struct Hades2HeaderActions: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate

    private func locate(_ entry: Hades2WorkbenchEntry) {
        model.showWorkbenchSection(entry.section)
        navigate(entry.section.id)
    }

    var body: some View {
        TrainerWorkbenchSearchField(
            text: $model.workbenchSearch,
            placeholder: Hades2GameModule.resolveText(key: "hades2.workbench.search", localization: localization),
            clearLabel: localization.localized("host.search.clear"),
            emptyLabel: Hades2GameModule.resolveText(key: "hades2.workbench.searchEmpty", localization: localization),
            search: { query in
                Hades2WorkbenchCatalog.matches(query) { key in
                    TrainerPresentationLanguage.allCases.map {
                        Hades2GameModule.resolveText(key: key, language: $0, localization: localization)
                    }
                }
            },
            title: { Hades2GameModule.resolveText(key: $0.titleKey, localization: localization) },
            detail: { Hades2GameModule.resolveText(key: $0.section.titleKey, localization: localization) },
            icon: { $0.icon },
            onNavigate: locate
        )
    }
}

struct Hades2ManagementCommands: Commands {
    @ObservedObject var model: Hades2TrainerModel
    @ObservedObject private var localization: TrainerLocalizationStore

    init(model: Hades2TrainerModel, localization: TrainerLocalizationStore) {
        self.model = model
        _localization = ObservedObject(wrappedValue: localization)
    }

    var body: some Commands {
        TrainerManagementCommandMenu(title: localization.localized("host.trainerMenu"),
            groups: Hades2ManagementCatalog.make(model: model, localization: localization).groups)
    }
}
