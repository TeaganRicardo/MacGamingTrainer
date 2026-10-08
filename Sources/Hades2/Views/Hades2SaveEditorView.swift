import SwiftUI

struct Hades2SaveEditorView: View {
    @StateObject private var model: Hades2SaveEditorModel
    @Binding var isPresented: Bool
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var drafts: [String: String] = [:]

    init(model: Hades2SaveEditorModel, isPresented: Binding<Bool>) {
        _model = StateObject(wrappedValue: model)
        _isPresented = isPresented
    }

    private func text(_ key: String, arguments: [String] = []) -> String {
        Hades2GameModule.resolveText(key: key, arguments: arguments, localization: localization)
    }

    var body: some View {
        TrainerSheetScaffold(
            title: text("hades2.saveEditor.title"),
            icon: "externaldrive.badge.gearshape",
            width: 920
        ) {
            Button(localization.localized("host.refresh")) {
                model.query(offset: model.offset)
            }
            .disabled(model.busy || model.profile.isEmpty)
        } content: {
            VStack(alignment: .leading, spacing: 12) {
                workspaceHeader
                domainToolbar
                if model.selectedDomain == .advanced {
                    advancedBreadcrumb
                }
                if let failure = model.failure {
                    TrainerInlineNotice(color: theme.warning) {
                        Text(localization.string(failure))
                            .font(.caption)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                editorList
                pagingControls
                reviewPanel
            }
        } footer: {
            HStack(spacing: 10) {
                if model.pendingCount > 0 {
                    Text(text("hades2.saveEditor.pendingCount", arguments: [String(model.pendingCount)]))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button(text("hades2.saveEditor.cancelChanges")) {
                        model.cancel()
                    }
                    .disabled(model.busy)
                    TrainerPrimaryActionButton(
                        title: text("hades2.saveEditor.apply"),
                        systemImage: "checkmark.circle",
                        enabled: !model.busy,
                        action: model.apply
                    )
                }
                Spacer()
                Button(localization.localized("host.done")) {
                    isPresented = false
                }
            }
        }
        .onAppear {
            model.open(language: localization.language)
        }
        .onChange(of: localization.language) { _, language in
            model.setLanguage(language)
        }
        .onChange(of: model.pendingCount) { previous, current in
            if previous > 0 && current == 0 {
                drafts.removeAll()
            }
        }
    }

    private var workspaceHeader: some View {
        VStack(alignment: .leading, spacing: 5) {
            if model.profile.isEmpty {
                ProgressView()
                    .controlSize(.small)
            } else {
                HStack(spacing: 12) {
                    Text(model.profile)
                        .font(.headline)
                    Text(model.relativePath)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    Spacer()
                }
            }
            Text(text("hades2.saveEditor.coldApplyNotice"))
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var domainToolbar: some View {
        HStack(spacing: 10) {
            Picker(
                text("hades2.saveEditor.domain"),
                selection: Binding(
                    get: { model.selectedDomain },
                    set: { model.selectDomain($0) }
                )
            ) {
                ForEach(visibleDomains) { domain in
                    Text(domainTitle(domain)).tag(domain)
                }
            }
            .frame(width: 180)

            TextField(
                text("hades2.saveEditor.search"),
                text: $model.search
            )
            .textFieldStyle(.roundedBorder)
            .onSubmit { model.submitSearch() }

            Button {
                model.submitSearch()
            } label: {
                Label(text("hades2.saveEditor.searchAction"), systemImage: "magnifyingglass")
            }
            .disabled(model.busy || model.profile.isEmpty)
        }
    }

    private var visibleDomains: [Hades2SaveEditorDomain] {
        model.availableDomains
    }

    private func domainTitle(_ domain: Hades2SaveEditorDomain) -> String {
        switch domain {
        case .overview: return text("hades2.saveEditor.domain.overview")
        case .resources: return text("hades2.saveEditor.domain.resources")
        case .playerStats: return text("hades2.saveEditor.domain.playerStats")
        case .progression: return text("hades2.saveEditor.domain.progression")
        case .dialogue: return text("hades2.saveEditor.domain.dialogue")
        case .flags: return text("hades2.saveEditor.domain.flags")
        case .relationships: return text("hades2.saveEditor.domain.relationships")
        case .weapons: return text("hades2.saveEditor.domain.weapons")
        case .advanced: return text("hades2.saveEditor.domain.advanced")
        }
    }

    @ViewBuilder
    private var advancedBreadcrumb: some View {
        HStack(spacing: 8) {
            Button {
                model.leaveAdvanced()
            } label: {
                Label(text("hades2.saveEditor.up"), systemImage: "chevron.left")
            }
            .disabled(model.busy || model.advancedPath.isEmpty)

            Text(advancedPathText)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            Spacer()
        }
    }

    private var advancedPathText: String {
        guard !model.advancedPath.isEmpty else { return "/" }
        return "/" + model.advancedPath.map(pathComponentText).joined(separator: "/")
    }

    private func pathComponentText(_ component: Hades2SaveEditorPathComponent) -> String {
        switch component {
        case .string(let value): return value
        case .integer(let value): return String(value)
        case .number(let value): return String(value)
        case .boolean(let value): return value ? "true" : "false"
        }
    }

    @ViewBuilder
    private var editorList: some View {
        if model.profile.isEmpty || (model.busy && model.items.isEmpty) {
            ProgressView()
                .frame(maxWidth: .infinity, minHeight: 260)
        } else if model.items.isEmpty {
            TrainerEmptyState(text: text("hades2.saveEditor.empty"))
                .frame(minHeight: 220)
        } else {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(model.items) { entry in
                        if model.selectedDomain == .advanced {
                            advancedRow(entry)
                        } else {
                            semanticRow(entry)
                        }
                    }
                }
            }
            .frame(minHeight: 300, maxHeight: 460)
        }
    }

    private func semanticRow(_ entry: Hades2SaveEditorEntry) -> some View {
        TrainerListCard {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(entry.displayName)
                        .font(.subheadline.weight(.semibold))
                    if entry.englishName != entry.displayName && localization.language != .en {
                        Text(entry.englishName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .help(entry.rawID)

                Spacer()

                if entry.editable, entry.mutationKinds.contains("set") {
                    TextField(
                        text("hades2.saveEditor.value"),
                        text: draftBinding(for: entry)
                    )
                    .textFieldStyle(.roundedBorder)
                    .multilineTextAlignment(.trailing)
                    .frame(width: 130)
                    .onSubmit { stageDraft(for: entry) }

                    Button(text("hades2.saveEditor.stage")) {
                        stageDraft(for: entry)
                    }
                    .disabled(model.busy || parsedDraft(for: entry) == nil)
                } else {
                    Text(valueText(entry.value))
                        .font(.body.monospacedDigit())
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func advancedRow(_ entry: Hades2SaveEditorEntry) -> some View {
        TrainerListCard {
            HStack(spacing: 12) {
                Image(systemName: entry.childCount == nil ? "doc.plaintext" : "folder")
                    .foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 3) {
                    Text(entry.displayName)
                        .font(.subheadline.weight(.semibold))
                    if entry.childCount == nil {
                        Text(valueText(entry.value))
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    } else {
                        Text(text("hades2.saveEditor.childCount", arguments: [String(entry.childCount ?? 0)]))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if entry.childCount != nil {
                    Button {
                        model.enterAdvanced(entry)
                    } label: {
                        Image(systemName: "chevron.right")
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy)
                }
            }
        }
    }

    private var pagingControls: some View {
        HStack {
            Text(pageSummary)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button(text("hades2.saveEditor.previousPage")) {
                model.previousPage()
            }
            .disabled(model.busy || model.offset == 0)
            Button(text("hades2.saveEditor.nextPage")) {
                model.nextPage()
            }
            .disabled(model.busy || model.offset + Hades2SaveEditorModel.pageSize >= model.total)
        }
    }

    private var pageSummary: String {
        guard model.total > 0 else {
            return text("hades2.saveEditor.pageSummary", arguments: ["0", "0", "0"])
        }
        let first = model.offset + 1
        let last = min(model.offset + model.items.count, model.total)
        return text(
            "hades2.saveEditor.pageSummary",
            arguments: [String(first), String(last), String(model.total)]
        )
    }

    @ViewBuilder
    private var reviewPanel: some View {
        if !model.pendingChanges.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(text("hades2.saveEditor.review"))
                    .font(.headline)
                ForEach(model.pendingChanges) { change in
                    HStack(spacing: 8) {
                        Text(model.displayName(for: change))
                            .font(.caption.weight(.semibold))
                            .lineLimit(1)
                            .help(change.rawID)
                        Spacer()
                        Text(valueText(change.before))
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                        Image(systemName: "arrow.right")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(valueText(change.after))
                            .font(.caption.monospaced())
                    }
                }
            }
            .trainerPanel(padding: 12, cornerRadius: theme.controlCornerRadius)
        }
    }

    private func draftBinding(for entry: Hades2SaveEditorEntry) -> Binding<String> {
        Binding(
            get: { drafts[entry.id] ?? valueText(entry.value) },
            set: { drafts[entry.id] = $0 }
        )
    }

    private func stageDraft(for entry: Hades2SaveEditorEntry) {
        guard let value = parsedDraft(for: entry) else { return }
        model.stage(entryID: entry.id, operation: "set", value: value)
    }

    private func parsedDraft(for entry: Hades2SaveEditorEntry) -> Any? {
        let raw = drafts[entry.id] ?? valueText(entry.value)
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        if entry.constraints?.integer == true || entry.valueType == "integer" {
            guard let value = Int(trimmed) else { return nil }
            if let minimum = entry.constraints?.minimum, Double(value) < minimum { return nil }
            if let maximum = entry.constraints?.maximum, Double(value) > maximum { return nil }
            return value
        }
        if entry.valueType == "number" {
            guard let value = Double(trimmed), value.isFinite else { return nil }
            if let minimum = entry.constraints?.minimum, value < minimum { return nil }
            if let maximum = entry.constraints?.maximum, value > maximum { return nil }
            return value
        }
        if entry.valueType == "boolean" {
            if trimmed == "true" { return true }
            if trimmed == "false" { return false }
            return nil
        }
        if entry.valueType == "string" {
            return trimmed
        }
        return nil
    }

    private func valueText(_ value: AnyHashable?) -> String {
        guard let value else { return "—" }
        if let bool = value.base as? Bool { return bool ? "true" : "false" }
        return String(describing: value.base)
    }
}
