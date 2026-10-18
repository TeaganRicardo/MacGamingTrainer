import SwiftUI

struct Hades2SaveEditorPresentation: Identifiable {
    let model: Hades2SaveEditorModel

    var id: ObjectIdentifier { ObjectIdentifier(model) }
}

extension View {
    func hades2SaveEditorSheet(
        _ presentation: Binding<Hades2SaveEditorPresentation?>
    ) -> some View {
        sheet(item: presentation) { item in
            Hades2SaveEditorView(model: item.model)
        }
    }
}

enum Hades2SaveWorkbenchSection: String, CaseIterable, Identifiable {
    case all
    case story
    case growth
    case resources
    case records
    case advanced

    var id: String { rawValue }
    var titleKey: String { "hades2.saveEditor.workbench.section." + rawValue }
}

struct Hades2SaveEditorView: View {
    @StateObject private var model: Hades2SaveEditorModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var section: Hades2SaveWorkbenchSection = .all
    @State private var drafts: [String: String] = [:]
    @State private var reviewExpanded = false
    @State private var expandedEffects: Set<String> = []
    @State private var confirmingSource = false

    init(model: Hades2SaveEditorModel) {
        _model = StateObject(wrappedValue: model)
    }

    private func text(_ key: String, arguments: [String] = []) -> String {
        Hades2GameModule.resolveText(
            key: key, arguments: arguments, localization: localization
        )
    }

    private var entities: [Hades2SaveEditorEntity] {
        model.entityResults
    }

    var body: some View {
        VStack(spacing: 0) {
            windowHeader
            Divider()
            documentSelection
            Divider()
            if let failure = model.failure {
                TrainerInlineNotice(color: theme.warning) {
                    Text(localization.string(failure))
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, 16)
                .padding(.top, 10)
            }
            workbenchToolbar
            if let queryFailure = model.queryFailure {
                TrainerInlineNotice(color: theme.warning) {
                    Text(localization.string(queryFailure))
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 8)
            }
            Divider()
            inlineResults
                .id(model.workspaceID)
                .frame(height: reviewExpanded ? 445 : 610)
            if model.total > Hades2SaveEditorModel.pageSize {
                Divider()
                pagingControls
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
            }
            if model.pendingCount > 0 {
                Divider()
                changesBar
                if reviewExpanded {
                    Divider()
                    reviewDrawer
                        .frame(height: 190)
                }
            }
            if let receipt = model.lastApplyReceipt {
                Divider()
                applyReceipt(receipt)
            }
        }
        .frame(width: 980)
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
        .confirmationDialog(
            text("hades2.saveEditor.source.confirmTitle"),
            isPresented: $confirmingSource
        ) {
            Button(text("hades2.saveEditor.source.read"), role: .destructive) {
                model.openSelection()
            }
            Button(text("hades2.saveEditor.workbench.cancel"), role: .cancel) {
                model.selectedSourceID = loadedSourceID
            }
        } message: {
            Text(text("hades2.saveEditor.source.confirmBody"))
        }
        .onAppear {
            model.open(language: localization.language)
        }
        .onChange(of: localization.language) { _, language in
            model.setLanguage(language)
        }
        .onChange(of: model.search) { _, _ in
            model.searchChanged()
        }
        .onChange(of: model.selectedSourceID) { _, identifier in
            guard !identifier.isEmpty, identifier != loadedSourceID else { return }
            // The initial inventory owns automatic default opening. An idle
            // source change with no workspace is the user's first manual open.
            // Ignore default selection changes while that opening is in flight.
            if model.busy {
                if model.workspaceID != nil { model.selectedSourceID = loadedSourceID }
                return
            }
            // Clicking away can finish a text edit and start staging before
            // the picker receives the same click. Never re-read that draft.
            guard model.sourceFiles.contains(where: { $0.id == identifier }) else {
                model.selectedSourceID = loadedSourceID
                return
            }
            if model.pendingCount > 0 { confirmingSource = true }
            else { model.openSelection() }
        }
        .onChange(of: model.pendingCount) { previous, current in
            if previous > 0 && current == 0 {
                drafts.removeAll()
                expandedEffects.removeAll()
                reviewExpanded = false
            }
        }
        .onChange(of: model.editRevision) { _, _ in
            if let entryID = model.reconciledEntryID {
                drafts.removeValue(forKey: entryID)
                expandedEffects.remove(entryID)
            } else {
                drafts.removeAll()
            }
        }
        .onChange(of: model.workspaceID) { _, _ in
            drafts.removeAll()
            expandedEffects.removeAll()
            section = .all
            reviewExpanded = false
        }
    }

    private var windowHeader: some View {
        HStack(spacing: 12) {
            Image(systemName: "externaldrive.badge.gearshape")
                .font(.title3)
                .foregroundStyle(theme.accent)
            Text(text("hades2.saveEditor.title"))
                .font(.title3.weight(.semibold))
            if !model.profile.isEmpty {
                Text(model.profile)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else if model.busy {
                ProgressView().controlSize(.small)
            }
            Spacer()
            Menu {
                Text(model.sourceRootID + "/" + model.sourceRelativePath)
                if let snapshotID = model.snapshotID { Text(snapshotID) }
                Text(model.sourceSHA256)
                Text(text("hades2.saveEditor.workbench.sourceHint"))
            } label: {
                Image(systemName: "info.circle")
            }
            .disabled(model.profile.isEmpty)
            .help(text("hades2.saveEditor.workbench.sourceHint"))

            Button {
                guard !model.busy else { return }
                model.selectedSourceID = loadedSourceID
                if model.pendingCount > 0 { confirmingSource = true }
                else { model.openSelection() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(model.busy || model.profile.isEmpty ||
                !model.sourceFiles.contains(where: { $0.id == loadedSourceID }))
            .help(text("hades2.saveEditor.source.read"))
            .accessibilityLabel(text("hades2.saveEditor.source.read"))

            Button(localization.localized("host.done")) {
                dismiss()
            }
        }
        .padding(.horizontal, 19)
        .padding(.vertical, 15)
    }

    private var documentSelection: some View {
        HStack(spacing: 12) {
            Text(text("hades2.saveEditor.source.label"))
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker(text("hades2.saveEditor.source.label"), selection: $model.selectedSourceID) {
                Text(text("hades2.saveEditor.source.choose")).tag("")
                ForEach(model.sourceFiles) { file in
                    Text(file.relativePath).tag(file.id)
                }
                if !loadedSourceID.isEmpty &&
                    !model.sourceFiles.contains(where: { $0.id == loadedSourceID }) {
                    Text(model.sourceRelativePath).tag(loadedSourceID)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 315)
            .disabled(model.busy)

            Button {
                model.refreshFiles()
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
            }
            .buttonStyle(.borderless)
            .disabled(model.busy)
            .help(text("hades2.saveEditor.source.refreshFiles"))
            .accessibilityLabel(text("hades2.saveEditor.source.refreshFiles"))

            Divider().frame(height: 20)

            Text(text("hades2.saveEditor.target.label"))
                .font(.caption)
                .foregroundStyle(.secondary)
            Picker(
                text("hades2.saveEditor.target.label"),
                selection: Binding(get: { model.selectedTargetID }, set: model.selectTarget)
            ) {
                Text(text("hades2.saveEditor.target.choose")).tag("")
                ForEach(model.writeTargets) { file in
                    Text(file.relativePath).tag(file.id)
                }
                if !model.selectedTargetID.isEmpty &&
                    !model.writeTargets.contains(where: { $0.id == model.selectedTargetID }) {
                    Text(selectedTargetLabel).tag(model.selectedTargetID)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 275)
            .disabled(model.busy)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
    }

    private var workbenchToolbar: some View {
        HStack(spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(text("hades2.saveEditor.workbench.search"), text: $model.search)
                    .textFieldStyle(.plain)
                    .onSubmit { model.submitSearch() }
                if !model.search.isEmpty {
                    Button {
                        model.search = ""
                        model.submitSearch()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(10)
            .trainerSurface(.subtle, cornerRadius: 8)
            .disabled(model.busy || model.profile.isEmpty)

            Picker(
                text("hades2.saveEditor.workbench.section.all"),
                selection: Binding(
                    get: { section },
                    set: { item in
                        guard section != item else { return }
                        section = item
                        if item == .advanced {
                            model.selectDomain(.advanced)
                        } else {
                            model.selectScope(item.rawValue)
                        }
                    }
                )
            ) {
                ForEach(Hades2SaveWorkbenchSection.allCases) { item in
                    Text(text(item.titleKey))
                        .tag(item)
                        .disabled(!model.availableDomains.contains(
                            item == .advanced ? .advanced : .entities
                        ))
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .frame(width: 190)
            .disabled(model.busy || model.profile.isEmpty)

            if section == .advanced && !model.advancedPath.isEmpty {
                Button {
                    model.leaveAdvanced()
                } label: {
                    Label(text("hades2.saveEditor.up"), systemImage: "chevron.left")
                }
                .buttonStyle(.borderless)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
    }

    private var inlineResults: some View {
        Group {
            if model.profile.isEmpty && !model.busy {
                TrainerEmptyState(text: text("hades2.saveEditor.source.choose"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if model.profile.isEmpty
                || ((model.busy || model.querying) && model.items.isEmpty) {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if model.items.isEmpty {
                TrainerEmptyState(text: text("hades2.saveEditor.empty"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(entities) { entity in
                            VStack(alignment: .leading, spacing: 0) {
                                if entity.entries.count > 1 {
                                    Text(entity.title)
                                        .font(.subheadline.weight(.semibold))
                                        .padding(.horizontal, 18)
                                        .padding(.top, 16)
                                        .padding(.bottom, 6)
                                }
                                ForEach(entity.entries) { entry in
                                    inlineEntry(entry, in: entity)
                                    Divider().padding(.leading, 18)
                                }
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func inlineEntry(
        _ entry: Hades2SaveEditorEntry, in entity: Hades2SaveEditorEntity
    ) -> some View {
        if entry.domain == "advanced" {
            advancedEntry(entry)
                .padding(.horizontal, 18)
                .padding(.vertical, 10)
        } else if entry.domain == "investigate" {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(fieldTitle(entry, in: entity))
                            .font(.callout)
                            .textSelection(.enabled)
                        if let snippet = entry.investigationSnippet, !snippet.isEmpty {
                            Text(snippet)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                    Spacer(minLength: 8)
                    Button(text("hades2.saveEditor.investigate.details")) {
                        model.inspect(entry)
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy)
                }
                if let detailError = model.detailFailure,
                   model.selectedInvestigationID == entry.rawID {
                    Text(localization.string(detailError))
                        .font(.caption)
                        .foregroundStyle(theme.warning)
                }
                if let detail = model.investigationDetail, detail.scene == entry.rawID {
                    investigationDetailView(detail)
                        .padding(.leading, 12)
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
        } else {
            HStack(spacing: 14) {
                Text(fieldTitle(entry, in: entity))
                    .font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                    .help(entry.rawID)
                if entry.editable && !entry.mutationKinds.isEmpty {
                    editorControl(entry)
                } else if entry.valueType != "table" {
                    Text(valueText(entry.value))
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                if !entry.editable &&
                    (entry.discoveryReasonCode != nil || entry.discoveryReason != nil) {
                    Image(systemName: "info.circle")
                        .foregroundStyle(.secondary)
                        .help(discoveryReason(
                            entry,
                            fallback: entry.discoveryReason ??
                                text("hades2.saveEditor.discovery.reason.readOnly")
                        ))
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 10)
        }
    }

    private func fieldTitle(
        _ entry: Hades2SaveEditorEntry, in entity: Hades2SaveEditorEntity
    ) -> String {
        if entry.displayName.hasPrefix(entity.title + " · ") {
            return String(entry.displayName.dropFirst((entity.title + " · ").count))
        }
        if entry.displayName.hasSuffix(" · " + entity.title) {
            return String(entry.displayName.dropLast((" · " + entity.title).count))
        }
        return entry.displayName
    }

    @ViewBuilder
    private func editorControl(
        _ entry: Hades2SaveEditorEntry, identity: String? = nil
    ) -> some View {
        let workspaceID = model.workspaceID
        let draft = draftBinding(for: entry)
        if entry.valueType == "boolean" {
            TrainerToggleControl(
                isOn: stagedValue(for: entry)?.base as? Bool ?? false,
                enabled: !model.busy,
                helpText: entry.displayName,
                onChange: { value in
                    guard !model.busy, model.workspaceID == workspaceID else { return }
                    _ = model.completeTextEdit(entry, text: value ? "true" : "false")
                }
            )
        } else if entry.valueType == "enum" && !entry.choices.isEmpty {
            Picker(
                text("hades2.saveEditor.value"),
                selection: Binding<String>(
                    get: { stagedValue(for: entry)?.base as? String ?? "" },
                    set: { choice in
                        guard !model.busy, model.workspaceID == workspaceID else { return }
                        _ = model.completeTextEdit(entry, text: choice)
                    }
                )
            ) {
                ForEach(entry.choices, id: \.self) { choice in
                    Text(entry.choiceNames[choice] ?? enumTitle(choice)).tag(choice)
                }
            }
            .labelsHidden()
            .frame(width: 230)
            .disabled(model.busy)
        } else {
            TrainerTextField(
                title: text("hades2.saveEditor.value"),
                text: draft,
                onCommit: { edit in
                    guard model.workspaceID == workspaceID else { return edit.text }
                    return model.completeTextEdit(entry, text: edit.text, changed: edit.changed)
                }
            )
            .id(identity ?? entry.id)
            .disabled(model.busy)
            .frame(width: 175)
        }
    }

    @ViewBuilder
    private func advancedEntry(_ entry: Hades2SaveEditorEntry) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(entry.rawID)
                .font(.callout.monospaced())
                .textSelection(.enabled)
            if let count = entry.childCount {
                Text(text("hades2.saveEditor.childCount", arguments: [String(count)]))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if !entry.pathAmbiguous {
                    Button(text("hades2.saveEditor.workbench.browse")) {
                        if model.selectedDomain == .discover {
                            section = .advanced
                            model.openDiscoveryEntry(entry)
                        } else {
                            model.enterAdvanced(entry)
                        }
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy)
                }
            } else {
                Text(valueText(entry.value))
                    .font(.callout.monospaced())
                    .textSelection(.enabled)
                if model.selectedDomain == .discover && !entry.pathAmbiguous {
                    Button(text("hades2.saveEditor.workbench.browse")) {
                        section = .advanced
                        model.openDiscoveryEntry(entry)
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy)
                }
            }
            if entry.pathAmbiguous {
                Text(text("hades2.saveEditor.ambiguousPath"))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
            }
        }
    }

    private var pagingControls: some View {
        HStack(spacing: 8) {
            Text(pageSummary)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
            Spacer()
            Button { model.previousPage() } label: {
                Image(systemName: "chevron.left")
            }
            .disabled(model.busy || model.offset == 0)
            Button { model.nextPage() } label: {
                Image(systemName: "chevron.right")
            }
            .disabled(model.busy || model.offset + Hades2SaveEditorModel.pageSize >= model.total)
        }
        .buttonStyle(.borderless)
    }

    private var pageSummary: String {
        text("hades2.saveEditor.pageSummary", arguments: [
            String(model.offset + 1),
            String(min(model.offset + model.entityResults.count, model.total)),
            String(model.total)
        ])
    }



    private func investigationDetailView(_ detail: Hades2SaveInvestigationDetail) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if !detail.lines.isEmpty {
                ForEach(detail.lines) { line in
                    VStack(alignment: .leading, spacing: 5) {
                        if !line.speaker.isEmpty {
                            Text(line.speaker)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                        let lines = localization.language == .en ? line.english : line.chinese
                        if lines.isEmpty {
                            Text(text("hades2.saveEditor.investigate.untranslated"))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(lines, id: \.self) { sentence in
                                Text(sentence)
                                    .textSelection(.enabled)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                    .padding(.vertical, 3)
                }
            }
            if detail.canStage && !detail.stageID.isEmpty {
                Button(text("hades2.saveEditor.investigate.clearRecord")) {
                    model.stage(entryID: detail.stageID, operation: "set", value: false)
                }
                .disabled(model.busy)
            }
            if !detail.definitions.isEmpty {
                DisclosureGroup(text("hades2.saveEditor.investigate.conditions")) {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(detail.definitions) { source in
                            ForEach(source.requirements) { requirement in
                                Hades2NarrativeConditionView(
                                    node: requirement.tree, label: text
                                )
                            }
                        }
                    }
                    .padding(.top, 8)
                }
            }
            DisclosureGroup(text("hades2.saveEditor.workbench.technical")) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(detail.scene).font(.caption.monospaced())
                    Text(text("hades2.saveEditor.investigate.future"))
                        .font(.caption)
                    ForEach(detail.definitions) { source in
                        Text("\(source.file):\(source.line)")
                            .font(.caption.monospaced())
                    }
                    if !detail.canStage {
                        Text(text(
                            "hades2.saveEditor.investigate.block."
                                + (detail.blockReasonCode ?? "invalidOwner")
                        ))
                        .font(.caption)
                    }
                }
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var changesBar: some View {
        HStack(spacing: 12) {
            Text(text("hades2.saveEditor.workbench.changes", arguments: [
                String(model.pendingCount)
            ]))
            .font(.callout)
            Spacer()
            Button(text("hades2.saveEditor.workbench.reviewApply")) {
                reviewExpanded.toggle()
                if reviewExpanded { model.review() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.busy)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
    }

    private var reviewDrawer: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(text("hades2.saveEditor.review"))
                        .font(.headline)
                    Text(text("hades2.saveEditor.basket.summary", arguments: [
                        String(model.pendingCount),
                        String(model.pendingEffectCount),
                        String(model.pendingPhysicalChangeCount),
                    ]))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                Spacer()
                Button(text("hades2.saveEditor.cancelChanges")) { model.cancel() }
                    .disabled(model.busy)
                Button(text("hades2.saveEditor.apply")) { model.apply() }
                    .buttonStyle(.borderedProminent)
                    .disabled(model.busy || !model.hasWriteTarget)
            }
            Text(text("hades2.saveEditor.workbench.target", arguments: [
                model.hasWriteTarget ? selectedTargetLabel : text("hades2.saveEditor.target.choose")
            ]))
            .font(.caption)
            .foregroundStyle(.secondary)
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(model.pendingActions) { action in
                        stagedAction(action)
                    }
                }
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .trainerSurface(.panel)
    }

    @ViewBuilder
    private func stagedAction(_ action: Hades2SaveEditorAction) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 9) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(action.name)
                        .font(.callout.weight(.medium))
                        .lineLimit(1)
                    if action.entityName != action.name {
                        Text(action.entityName)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 8)
                editorControl(
                    action.editorEntry,
                    identity: "basket:" + action.entryID
                )
                Button {
                    model.unstage(entryID: action.entryID)
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .help(text("hades2.saveEditor.basket.remove"))
                .accessibilityLabel(text("hades2.saveEditor.basket.remove"))
                .disabled(model.busy)
            }
            HStack(spacing: 6) {
                Text(reviewValue(action.before, for: action))
                .foregroundStyle(.secondary)
                Image(systemName: "arrow.right")
                    .foregroundStyle(.secondary)
                Text(reviewValue(action.after, for: action))
                Spacer()
                if !action.effects.isEmpty {
                    Button(text("hades2.saveEditor.basket.linkedEffects", arguments: [
                        String(action.effects.count)
                    ])) {
                        if expandedEffects.contains(action.id) {
                            expandedEffects.remove(action.id)
                        } else {
                            expandedEffects.insert(action.id)
                        }
                    }
                    .buttonStyle(.borderless)
                }
            }
            .font(.caption.monospacedDigit())
            if expandedEffects.contains(action.id) {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(action.effects) { effect in
                        HStack(spacing: 6) {
                            Text(effect.name ?? effect.rawID)
                                .lineLimit(1)
                            Spacer()
                            Text(effect.beforeDisplay ?? reviewValue(
                                effect.before,
                                operation: effect.operation,
                                domain: effect.domain
                            ))
                            .foregroundStyle(.secondary)
                            Image(systemName: "arrow.right")
                                .foregroundStyle(.secondary)
                            Text(effect.afterDisplay ?? reviewValue(
                                effect.after,
                                operation: effect.operation,
                                domain: effect.domain
                            ))
                        }
                        .font(.caption2.monospacedDigit())
                    }
                }
                .padding(.leading, 12)
            }
        }
        .padding(.vertical, 3)
    }

    private func applyReceipt(_ receipt: Hades2SaveEditorApplyReceipt) -> some View {
        let mode = text(
            receipt.hot
                ? "hades2.saveEditor.applyOutcome.mode.hot"
                : "hades2.saveEditor.applyOutcome.mode.cold"
        )
        let memory = text(
            receipt.runtimeReloaded
                ? "hades2.saveEditor.applyOutcome.memory.reloaded"
                : "hades2.saveEditor.applyOutcome.memory.notReloaded"
        )
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(theme.accent)
                Text(text("hades2.saveEditor.applyOutcome.title"))
                    .font(.callout.weight(.semibold))
            }
            Text(text("hades2.saveEditor.applyOutcome.sourceTarget", arguments: [
                receipt.source,
                receipt.target
            ]))
            .font(.caption)
            .foregroundStyle(.secondary)
            Text(text("hades2.saveEditor.applyOutcome.disk", arguments: [mode, memory]))
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(text("hades2.saveEditor.applyOutcome.recovery", arguments: [
                receipt.previousSnapshotID
            ]))
            .font(.caption)
            .foregroundStyle(.secondary)
            Text(text("hades2.saveEditor.applyOutcome.laterSave"))
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .trainerSurface(.panel)
    }

    private var selectedTargetLabel: String {
        if let file = model.writeTargets.first(where: { $0.id == model.selectedTargetID }) {
            return file.relativePath
        }
        let components = model.selectedTargetID.split(
            separator: "/", maxSplits: 1, omittingEmptySubsequences: false
        )
        return components.count == 2 ? String(components[1]) : model.selectedTargetID
    }

    private var loadedSourceID: String {
        guard !model.sourceRelativePath.isEmpty else { return "" }
        return model.sourceRootID + "/" + model.sourceRelativePath
    }

    private func reviewValue(
        _ value: AnyHashable?, for action: Hades2SaveEditorAction
    ) -> String {
        if action.operation == "setEnum", let raw = value?.base as? String {
            return action.choiceNames[raw] ?? enumTitle(raw)
        }
        return reviewValue(value, operation: action.operation, domain: action.domain)
    }

    private func reviewValue(
        _ value: AnyHashable?, operation: String, domain: String
    ) -> String {
        if operation == "setEnum", let raw = value?.base as? String {
            return enumTitle(raw)
        }
        if let bool = value?.base as? Bool {
            if domain == "dialogue" || domain == "flags" {
                return text(bool ? "hades2.saveEditor.true" : "hades2.saveEditor.false")
            }
            return text(bool
                        ? "hades2.saveEditor.workbench.yes"
                        : "hades2.saveEditor.workbench.no")
        }
        return valueText(value)
    }

    // All controls project the backend-acknowledged requested action, including
    // after the user changes search scope/page and the source row is reloaded.
    private func stagedValue(for entry: Hades2SaveEditorEntry) -> AnyHashable? {
        model.pendingActions.first(where: { $0.entryID == entry.id })?.after ?? entry.value
    }

    private func draftBinding(for entry: Hades2SaveEditorEntry) -> Binding<String> {
        let workspaceID = model.workspaceID
        return Binding(
            get: { drafts[entry.id] ?? valueText(stagedValue(for: entry)) },
            set: { if model.workspaceID == workspaceID { drafts[entry.id] = $0 } }
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



    private func discoveryReason(_ entry: Hades2SaveEditorEntry, fallback: String) -> String {
        guard let code = entry.discoveryReasonCode else { return fallback }
        if entry.domain == "investigate" || entry.domain == "dialogue" {
            return text("hades2.saveEditor.investigate.block." + code)
        }
        let known = [
            "editable", "editableAbsent", "readOnly", "unknownRaw",
            "ambiguousOwner", "unsupportedOwner", "ambiguousRaw", "knownAbsent",
            "rewardClaimed", "starterWeapon", "baseWeaponRequired", "giftHistoryLinked"
        ]
        return known.contains(code)
            ? text("hades2.saveEditor.discovery.reason." + code)
            : fallback
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
