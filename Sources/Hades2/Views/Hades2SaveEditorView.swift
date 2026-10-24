import SwiftUI

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
    @Environment(\.trainerCloseToolWindow) private var closeWindow
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var section: Hades2SaveWorkbenchSection = .all
    @State private var drafts: [String: String] = [:]
    @State private var confirmingSource = false
    @State private var advancedEditingEntry: Hades2SaveEditorEntry?

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
            ForEach(model.operationFailures.keys.sorted(by: { $0.rawValue < $1.rawValue }), id: \.rawValue) { command in
                if let failure = model.operationFailures[command] {
                    TrainerInlineNotice(color: theme.warning) {
                        Text(localization.string(failure))
                            .font(.caption)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.top, theme.controlPadding)
                }
            }
            workbenchToolbar
            if let queryFailure = model.queryFailure {
                TrainerInlineNotice(color: theme.warning) {
                    Text(localization.string(queryFailure))
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, theme.rowHorizontalPadding)
                .padding(.bottom, theme.compactControlSpacing)
            }
            Divider()
            inlineResults
                .id(model.workspaceID)
                .frame(height: model.pendingCount > 0 ? 445 : 610)
            if model.total > Hades2SaveEditorModel.pageSize {
                Divider()
                pagingControls
                    .padding(.horizontal, theme.rowHorizontalPadding)
                    .padding(.vertical, theme.inlineRowVerticalPadding)
            }
            if model.pendingCount > 0 {
                Divider()
                reviewDrawer
                    .frame(height: 240)
            }
            if let receipt = model.lastApplyReceipt {
                Divider()
                applyReceipt(receipt)
            }
        }
        .frame(width: 980)
        .trainerSurface(.canvas)
        .trainerDismissTextEditingOnClickAway()
        .sheet(item: $advancedEditingEntry) { entry in
            Hades2SaveAdvancedValueView(model: model, entry: entry)
        }
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
        .onChange(of: model.editRevision) { _, _ in
            if let entryIDs = model.reconciledEntryIDs {
                for entryID in entryIDs {
                    drafts.removeValue(forKey: entryID)
                }
            } else {
                drafts.removeAll()
            }
        }
        .onChange(of: model.workspaceID) { _, _ in
            advancedEditingEntry = nil
            drafts.removeAll()
            section = .all
        }
    }

    private var windowHeader: some View {
        HStack(spacing: theme.sectionSpacing) {
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
                if let closeWindow { closeWindow() } else { dismiss() }
            }
            .disabled(model.busy)
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, 15)
    }

    private var documentSelection: some View {
        HStack(spacing: theme.sectionSpacing) {
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
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
    }

    private var workbenchToolbar: some View {
        HStack(spacing: theme.sectionSpacing) {
            TrainerSearchField(
                text: $model.search,
                placeholder: text("hades2.saveEditor.workbench.search"),
                clearLabel: localization.localized("host.search.clear"),
                onSubmit: { model.submitSearch() }
            )
            .disabled(model.busy || model.profile.isEmpty)

            if model.querying {
                ProgressView().controlSize(.small)
            }

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
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.sectionSpacing)
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
                    LazyVStack(alignment: .leading, spacing: theme.pageSpacing) {
                        ForEach(Hades2SaveEditorEntityGrouping.sections(from: entities)) { resultSection in
                            TrainerSection(title: text(resultSection.titleKey), icon: resultSection.icon) {
                                ForEach(resultSection.entities) { entity in
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(entity.title)
                                            .font(.headline)
                                            .accessibilityAddTraits(.isHeader)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                            .padding(.horizontal, theme.rowHorizontalPadding)
                                            .padding(.vertical, theme.sectionSpacing)
                                            .trainerSurface(.subtle)
                                        ForEach(Hades2SaveEditorEntityGrouping.fields(in: entity)) { fields in
                                            if let title = fields.title {
                                                Text(title)
                                                    .font(.subheadline.weight(.semibold))
                                                    .foregroundStyle(.secondary)
                                                    .accessibilityAddTraits(.isHeader)
                                                    .padding(.horizontal, theme.rowHorizontalPadding)
                                                    .padding(.top, theme.sectionSpacing)
                                            }
                                            ForEach(fields.entries) { entry in
                                                if entry.id != fields.entries.first?.id {
                                                    Divider().padding(.horizontal, theme.rowHorizontalPadding)
                                                }
                                                inlineEntry(entry, in: entity)
                                            }
                                        }
                                    }
                                    .trainerSurface(.panel, cornerRadius: theme.panelCornerRadius)
                                    .trainerGroupedRows()
                                }
                            }
                        }
                    }
                    .padding(theme.panelPadding)
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
                .padding(.horizontal, theme.rowHorizontalPadding)
                .padding(.vertical, theme.inlineRowVerticalPadding)
        } else if entry.domain == "investigate" {
            VStack(alignment: .leading, spacing: theme.compactControlSpacing) {
                Text(fieldTitle(entry, in: entity))
                    .font(.callout)
                ForEach(Array(entry.content.enumerated()), id: \.offset) { _, line in
                    Text(line).font(.callout).textSelection(.enabled)
                }
                if entry.content.isEmpty, let snippet = entry.investigationSnippet {
                    Text(snippet).font(.callout).textSelection(.enabled)
                }
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.vertical, theme.sectionSpacing)
        } else {
            VStack(alignment: .leading, spacing: theme.compactControlSpacing) {
                HStack(spacing: 14) {
                    Text(fieldTitle(entry, in: entity))
                        .font(.callout)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                    if entry.editable && !entry.mutationKinds.isEmpty {
                        editorControl(entry)
                    } else if entry.valueType != "table" {
                        Text(valueText(entry.value))
                            .font(.callout.monospacedDigit())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }
                ForEach(Array(entry.content.enumerated()), id: \.offset) { _, line in
                    if line != entity.title {
                        Text(line)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .textSelection(.enabled)
                    }
                }
                if !entry.editable, let reason = entry.discoveryReason {
                    Text(discoveryReason(entry, fallback: reason))
                        .font(.caption)
                        .foregroundStyle(theme.warning)
                }
                if let warning = entry.warning {
                    Text(warning).font(.caption).foregroundStyle(theme.warning)
                }
                editFailure(entry)
            }
            .padding(.horizontal, theme.rowHorizontalPadding)
            .padding(.vertical, theme.inlineRowVerticalPadding)
        }
    }

    private func fieldTitle(
        _ entry: Hades2SaveEditorEntry, in entity: Hades2SaveEditorEntity
    ) -> String {
        if entry.displayName == entity.title {
            return text("hades2.saveEditor.value")
        }
        if entry.displayName.hasPrefix(entity.title + " · ") {
            return String(entry.displayName.dropFirst((entity.title + " · ").count))
        }
        if entry.displayName.hasSuffix(" · " + entity.title) {
            return String(entry.displayName.dropLast((" · " + entity.title).count))
        }
        return entry.displayName
    }

    @ViewBuilder
    private func editFailure(_ entry: Hades2SaveEditorEntry) -> some View {
        if let failure = model.editFailures[entry.id] {
            Text(localization.string(failure))
                .font(.caption)
                .foregroundStyle(theme.warning)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(entry.displayName + ": " + localization.string(failure))
        }
    }

    @ViewBuilder
    private func editorControl(
        _ entry: Hades2SaveEditorEntry, identity: String? = nil
    ) -> some View {
        let workspaceID = model.workspaceID
        let draft = draftBinding(for: entry)
        if entry.domain == "advanced",
           let removed = model.pendingActions.first(where: { $0.entryID == entry.id }), !removed.afterPresent {
            Text(text("hades2.saveEditor.advanced.removed")).font(.caption).foregroundStyle(.secondary)
            if let before = removed.typedBefore, removed.beforePresent {
                Button(text("hades2.saveEditor.advanced.restore")) {
                    model.stage(entryID: entry.id, operation: "set", value: before.object)
                }.disabled(model.busy)
            }
        } else if entry.domain == "advanced" &&
                    (entry.typedValue != nil || ["table", "binary", "nil"].contains(entry.valueType)) {
            Button(text("hades2.saveEditor.advanced.editValue")) { advancedEditingEntry = entry }
                .accessibilityIdentifier("saveEditor.editValue." + entry.id)
                .disabled(model.busy)
        } else if entry.valueType == "boolean" {
            TrainerToggleControl(
                title: entry.displayName,
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
                entry.displayName,
                selection: Binding<String>(
                    get: { enumToken(stagedValue(for: entry)) },
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
                accessibilityLabel: entry.displayName,
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
            Text(entry.displayName)
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
                if entry.editable { editorControl(entry) }
                else {
                    Text(valueText(entry.value))
                        .font(.callout.monospaced())
                        .textSelection(.enabled)
                }
                if model.selectedDomain == .discover && !entry.pathAmbiguous {
                    Button(text("hades2.saveEditor.workbench.browse")) {
                        section = .advanced
                        model.openDiscoveryEntry(entry)
                    }
                    .buttonStyle(.borderless)
                    .disabled(model.busy)
                }
            }
            if entry.editable {
                if entry.childCount != nil { editorControl(entry) }
                else if !["binary", "nil"].contains(entry.valueType) && entry.typedValue == nil {
                    Button(text("hades2.saveEditor.advanced.editValue")) { advancedEditingEntry = entry }
                        .accessibilityIdentifier("saveEditor.editValue." + entry.id)
                        .disabled(model.busy)
                }
                if entry.mutationKinds.contains("unset") {
                    Button(text("hades2.saveEditor.advanced.removeField")) {
                        model.stage(entryID: entry.id, operation: "unset", value: nil)
                    }
                    .accessibilityIdentifier("saveEditor.unset." + entry.id)
                    .disabled(model.busy)
                }
            }
            if let warning = entry.warning {
                Text(warning).font(.caption).foregroundStyle(theme.warning)
            }
            if !entry.editable, let reason = entry.discoveryReason {
                Text(reason).font(.caption).foregroundStyle(theme.warning)
            }
            editFailure(entry)
            if entry.pathAmbiguous {
                Text(text("hades2.saveEditor.ambiguousPath"))
                    .font(.caption)
                    .foregroundStyle(theme.warning)
            }
        }
    }

    private var pagingControls: some View {
        HStack(spacing: theme.compactControlSpacing) {
            Text(pageSummary)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
            Spacer()
            Button { model.previousPage() } label: {
                Image(systemName: "chevron.left")
            }
            .disabled(model.busy || model.offset == 0)
            .accessibilityLabel(text("hades2.saveEditor.previousPage"))
            .help(text("hades2.saveEditor.previousPage"))
            Button { model.nextPage() } label: {
                Image(systemName: "chevron.right")
            }
            .disabled(model.busy || model.offset + Hades2SaveEditorModel.pageSize >= model.total)
            .accessibilityLabel(text("hades2.saveEditor.nextPage"))
            .help(text("hades2.saveEditor.nextPage"))
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
                TrainerPrimaryActionButton(
                    title: text("hades2.saveEditor.apply"),
                    enabled: !model.busy && model.hasWriteTarget
                ) {
                    model.apply()
                }
            }
            Text(text("hades2.saveEditor.workbench.target", arguments: [
                model.hasWriteTarget ? selectedTargetLabel : text("hades2.saveEditor.target.choose")
            ]))
            .font(.caption)
            .foregroundStyle(.secondary)
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(model.pendingActions) { action in
                        stagedAction(action)
                    }
                }
            }
        }
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
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
                .accessibilityIdentifier("saveEditor.remove." + action.entryID)
                .disabled(model.busy)
            }
            editFailure(action.editorEntry)
            HStack(spacing: 6) {
                Text(action.domain == "advanced"
                     ? typedReviewValue(action.typedBefore, present: action.beforePresent)
                     : reviewValue(action.before, for: action))
                .foregroundStyle(.secondary)
                Image(systemName: "arrow.right")
                    .foregroundStyle(.secondary)
                Text(action.domain == "advanced"
                     ? typedReviewValue(action.typedAfter, present: action.afterPresent)
                     : reviewValue(action.after, for: action))
                Spacer()
            }
            .font(.caption.monospacedDigit())
            if !action.effects.isEmpty {
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
            HStack(spacing: theme.compactControlSpacing) {
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
        .padding(.horizontal, theme.rowHorizontalPadding)
        .padding(.vertical, theme.inlineRowVerticalPadding)
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
        if action.operation == "setEnum", value != nil {
            let raw = enumToken(value)
            return action.choiceNames[raw] ?? enumTitle(raw)
        }
        return reviewValue(value, operation: action.operation, domain: action.domain)
    }

    private func typedReviewValue(_ value: Hades2SaveTypedValue?, present: Bool) -> String {
        guard present else { return text("hades2.saveEditor.advanced.removed") }
        return value?.json ?? "—"
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

    private func enumToken(_ value: AnyHashable?) -> String {
        guard let value else { return "" }
        return (value.base as? String) ?? String(describing: value.base)
    }



    private func discoveryReason(_ entry: Hades2SaveEditorEntry, fallback: String) -> String {
        guard let code = entry.discoveryReasonCode else { return fallback }
        if entry.domain == "investigate" || entry.domain == "dialogue" {
            return text("hades2.saveEditor.investigate.block." + code)
        }
        let known = [
            "editable", "editableAbsent", "readOnly", "unknownRaw",
            "ambiguousOwner", "unsupportedOwner", "ambiguousRaw", "knownAbsent",
            "rewardClaimed", "starterWeapon", "baseWeaponRequired", "giftHistoryLinked",
            "familiarUpgradeOwnerUnsupported", "noIndependentToolSelection"
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
