import SwiftUI

struct Hades2SidebarActions: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerNavigateToSection) private var navigate
    @Environment(\.trainerGamePageVisible) private var pageVisible

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Divider().padding(.vertical, 2)
            ForEach(Hades2WorkbenchSection.allCases) { section in
                if section == .management { Divider().padding(.vertical, 2) }
                TrainerSectionButton(
                    title: Hades2GameModule.resolveText(key: section.titleKey, localization: localization),
                    systemImage: section.icon
                ) {
                    model.showWorkbenchSection(section)
                    navigate(section.id)
                }
                // Section rows are navigation shortcuts, not form controls: the
                // window's initial key view lands on the first row and would
                // otherwise keep a focus ring on it until something else takes
                // focus. Keep them keyboard-reachable without the persistent box.
                .focusEffectDisabled()
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
    @Environment(\.trainerGamePageVisible) private var pageVisible
    @State private var resultsPresented = false

    private var results: [Hades2WorkbenchEntry] {
        Hades2WorkbenchCatalog.matches(model.workbenchSearch) { key in
            TrainerPresentationLanguage.allCases.map {
                Hades2GameModule.resolveText(key: key, language: $0, localization: localization)
            }
        }
    }

    private func locate(_ entry: Hades2WorkbenchEntry) {
        model.showWorkbenchSection(entry.section)
        navigate(entry.section.id)
        resultsPresented = false
    }

    private func submitSearch() {
        if let first = results.first { locate(first) }
        else { resultsPresented = false }
    }

    var body: some View {
        TrainerSearchField(
            text: $model.workbenchSearch,
            placeholder: Hades2GameModule.resolveText(key: "hades2.workbench.search", localization: localization),
            clearLabel: localization.localized("host.search.clear")
        ) {
            submitSearch()
        }
        .popover(isPresented: $resultsPresented, arrowEdge: .bottom) {
            Group {
                if results.isEmpty {
                    TrainerEmptyState(text: Hades2GameModule.resolveText(key: "hades2.workbench.searchEmpty", localization: localization))
                } else {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(results) { entry in
                                TrainerSectionButton(
                                    title: Hades2GameModule.resolveText(key: entry.titleKey, localization: localization),
                                    detail: Hades2GameModule.resolveText(key: entry.section.titleKey, localization: localization),
                                    systemImage: entry.icon
                                ) { locate(entry) }
                            }
                        }
                    }
                    .frame(height: min(CGFloat(results.count) * 52, 312))
                }
            }
            .frame(width: 420)
            .padding(8)
        }
        .onChange(of: model.workbenchSearch) { _, query in
            guard pageVisible else { return }
            resultsPresented = !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        .onChange(of: pageVisible) { _, visible in
            if !visible { resultsPresented = false }
        }
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
        CommandMenu(localization.localized("host.trainerMenu")) {
            Button(localization.localized("host.refreshStatus")) { model.refreshFromHost() }
                .disabled(model.busy)
            Button(localization.localized("host.disableAll")) { model.disableAll() }
                .disabled(model.busy || !model.connected)
            Divider()
            Button(localization.localized("host.shortcutSettings")) { model.shortcutSettingsPresented = true }
            Button(localization.localized("host.viewLog")) { model.openLog() }
            Button(localization.localized("host.viewLogHistory")) { model.openLogHistory() }
            Button(localization.localized("host.clearCompletedLogs")) { model.clearCompletedLogs() }
        }
    }
}
