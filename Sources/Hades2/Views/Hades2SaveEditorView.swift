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
                if model.selectedDomain == .investigate {
                    investigationWorkbench
                } else {
                    editorList
                }
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

            if model.selectedDomain == .investigate {
                Picker(
                    text("hades2.saveEditor.investigate.all"),
                    selection: Binding(
                        get: { model.investigationFilter },
                        set: { model.setInvestigationFilter($0) }
                    )
                ) {
                    ForEach(["all", "recorded", "notRecorded", "ambiguous", "unknown"], id: \.self) { value in
                        Text(text("hades2.saveEditor.investigate." + value)).tag(value)
                    }
                }
                .labelsHidden()
                .frame(width: 145)
            }

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
        case .investigate: return text("hades2.saveEditor.domain.investigate")
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
    private var investigationWorkbench: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.investigationSourceStatus == "missing" || model.investigationSourceStatus == "mismatch" {
                Text(text("hades2.saveEditor.investigate." + model.investigationSourceStatus))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(alignment: .top, spacing: 12) {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(model.items) { entry in
                            Button {
                                model.inspect(entry)
                            } label: {
                                TrainerListCard {
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(entry.displayName)
                                            .font(.subheadline.weight(.semibold))
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                        Text(text("hades2.saveEditor.investigate." + (entry.investigationStatus ?? "unknown")))
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        if let excerpt = entry.investigationSnippet, !excerpt.isEmpty {
                                            Text(excerpt)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(2)
                                                .frame(maxWidth: .infinity, alignment: .leading)
                                        }
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(entry.displayName)
                            .accessibilityHint(text("hades2.saveEditor.investigate.details"))
                        }
                    }
                }
                .frame(minWidth: 290, maxWidth: 360, minHeight: 300, maxHeight: 460)

                if let detail = model.investigationDetail {
                    ScrollView {
                        investigationDetailView(detail)
                    }
                    .frame(maxWidth: .infinity, minHeight: 300, maxHeight: 460)
                } else {
                    Text(text("hades2.saveEditor.investigate.select"))
                        .foregroundStyle(.secondary)
                        .font(.callout)
                        .frame(maxWidth: .infinity, minHeight: 300)
                }
            }
        }
    }

    private func investigationDetailView(_ detail: Hades2SaveInvestigationDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(detail.scene)
                .font(.headline)
                .textSelection(.enabled)
            Text(text("hades2.saveEditor.investigate." + detail.status))
                .font(.subheadline)
            Text(text("hades2.saveEditor.investigate.future"))
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if detail.canStage && !detail.stageID.isEmpty {
                Button(text("hades2.saveEditor.investigate.clearRecord")) {
                    model.stage(entryID: detail.stageID, operation: "set", value: false)
                }
                .disabled(model.busy)
            } else {
                Text(text("hades2.saveEditor.investigate.readOnly"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if detail.status == "recorded" && !detail.canStage {
                Text(text("hades2.saveEditor.investigate.block." + (detail.blockReasonCode ?? "invalidOwner")))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
                    .fixedSize(horizontal: false, vertical: true)
                    .help(detail.reason)
            } else {
                Text(text("hades2.saveEditor.investigate." + (detail.sourceStatus == "available" ? detail.status + "Reason" : "sourceReason")))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if detail.sourceResolution == "unresolved" {
                Text(text("hades2.saveEditor.investigate.sourceUnresolved"))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
            }
            if !detail.definitions.isEmpty {
                Text(text("hades2.saveEditor.investigate.authored"))
                    .font(.subheadline.weight(.semibold))
                ForEach(detail.definitions) { source in
                    DisclosureGroup("\(source.file):\(source.line)") {
                        VStack(alignment: .leading, spacing: 6) {
                            if source.partner {
                                Text("Partner / CopyDataFromPartner")
                                    .font(.caption)
                            }
                            ForEach(source.requirements) { requirement in
                                DisclosureGroup("\(text("hades2.saveEditor.investigate.conditions")) · \(requirement.line)") {
                                    Hades2NarrativeConditionView(node: requirement.tree, label: self.text)
                                }
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .font(.caption)
                }
            }
            Text(text("hades2.saveEditor.investigate.lines"))
                .font(.subheadline.weight(.semibold))
            ForEach(detail.lines) { line in
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(line.speaker.isEmpty ? "Cue" : line.speaker) · \(line.cueID)")
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    let official = localization.language == .en ? line.english : line.chinese
                    if official.isEmpty {
                        Text(text("hades2.saveEditor.investigate.untranslated"))
                            .font(.caption)
                            .foregroundStyle(theme.warning)
                    } else {
                        ForEach(official, id: \.self) { lineText in
                            Text(lineText)
                                .font(.callout)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
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
                    if let group = entry.group {
                        Text(group)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if entry.englishName != entry.displayName && localization.language != .en {
                        Text(entry.englishName)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .help(entry.rawID)

                Spacer()

                if entry.editable, !entry.mutationKinds.isEmpty {
                    if entry.valueType == "boolean" {
                        Picker(text("hades2.saveEditor.value"), selection: draftBinding(for: entry)) {
                            Text(text("hades2.saveEditor.false")).tag("false")
                            Text(text("hades2.saveEditor.true")).tag("true")
                        }
                        .labelsHidden()
                        .frame(width: 130)
                    } else if entry.valueType == "enum", !entry.choices.isEmpty {
                        Picker(text("hades2.saveEditor.value"), selection: draftBinding(for: entry)) {
                            ForEach(entry.choices, id: \.self) { choice in
                                Text(entry.choiceNames[choice] ?? enumTitle(choice)).tag(choice)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 150)
                    } else {
                        TextField(
                            text("hades2.saveEditor.value"),
                            text: draftBinding(for: entry)
                        )
                        .textFieldStyle(.roundedBorder)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 130)
                        .onSubmit { stageDraft(for: entry) }
                    }

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
                if entry.pathAmbiguous {
                    Text(text("hades2.saveEditor.ambiguousPath"))
                        .font(.caption)
                        .foregroundStyle(theme.warning)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if entry.childCount != nil {
                    Button {
                        model.enterAdvanced(entry)
                    } label: {
                        Image(systemName: "chevron.right")
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy || entry.pathAmbiguous)
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
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
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
                }
                .frame(maxHeight: 220)
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

    private func enumTitle(_ value: String) -> String {
        switch value {
        case "Unlocked": return text("hades2.saveEditor.quest.unlocked")
        case "Complete": return text("hades2.saveEditor.quest.complete")
        case "CashedOut": return text("hades2.saveEditor.quest.cashedOut")
        default: return value
        }
    }

    private func stageDraft(for entry: Hades2SaveEditorEntry) {
        guard let value = parsedDraft(for: entry) else { return }
        let operation = entry.mutationKinds.contains("setEnum") ? "setEnum" : "set"
        model.stage(entryID: entry.id, operation: operation, value: value)
    }

    private func parsedDraft(for entry: Hades2SaveEditorEntry) -> Any? {
        let raw = drafts[entry.id] ?? valueText(entry.value)
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if entry.valueType == "enum" {
            return entry.choices.contains(trimmed) ? trimmed : nil
        }
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

private struct Hades2NarrativeConditionView: View {
    let node: Hades2NarrativeCondition
    let label: (String, [String]) -> String

    var body: some View {
        if node.children.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
                Text(node.label)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                Text(label("hades2.saveEditor.investigate.path." + node.evidence, []))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                if let observation = node.observation {
                    Text(label("hades2.saveEditor.investigate.path.observation", [observation]))
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            DisclosureGroup(node.label) {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(node.children) { child in
                        Hades2NarrativeConditionView(node: child, label: label)
                    }
                }
            }
            .font(.caption)
        }
    }
}
