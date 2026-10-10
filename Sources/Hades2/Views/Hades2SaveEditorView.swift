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

private enum Hades2SaveWorkbenchSection: String, CaseIterable, Identifiable {
    case all
    case story
    case people
    case resources
    case growth
    case equipment
    case records
    case advanced

    var id: String { rawValue }

    var domain: Hades2SaveEditorDomain {
        switch self {
        case .all: return .discover
        case .story: return .investigate
        case .people: return .relationships
        case .resources: return .resources
        case .growth: return .progression
        case .equipment: return .weapons
        case .records: return .playerStats
        case .advanced: return .advanced
        }
    }

    var icon: String {
        switch self {
        case .all: return "square.grid.2x2"
        case .story: return "text.book.closed"
        case .people: return "person.2"
        case .resources: return "shippingbox"
        case .growth: return "sparkles.rectangle.stack"
        case .equipment: return "shield.lefthalf.filled"
        case .records: return "chart.bar.xaxis"
        case .advanced: return "chevron.left.forwardslash.chevron.right"
        }
    }
}

struct Hades2SaveEditorView: View {
    @StateObject private var model: Hades2SaveEditorModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    @State private var section: Hades2SaveWorkbenchSection = .all
    @State private var selectedEntityID: String?
    @State private var drafts: [String: String] = [:]
    @State private var reviewExpanded = false
    @State private var confirmingApply = false

    init(model: Hades2SaveEditorModel) {
        _model = StateObject(wrappedValue: model)
    }

    private func text(_ key: String, arguments: [String] = []) -> String {
        Hades2GameModule.resolveText(
            key: key, arguments: arguments, localization: localization
        )
    }

    private var entities: [Hades2SaveEditorEntity] {
        Hades2SaveEditorEntityGrouping.entities(from: model.items)
    }

    private var selectedEntity: Hades2SaveEditorEntity? {
        entities.first(where: { $0.id == selectedEntityID })
    }

    var body: some View {
        VStack(spacing: 0) {
            windowHeader
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

            HSplitView {
                navigation
                    .frame(minWidth: 175, idealWidth: 200, maxWidth: 250)
                resultList
                    .frame(minWidth: 290, idealWidth: 390, maxWidth: 500)
                inspector
                    .frame(minWidth: 360, maxWidth: .infinity)
            }
            .frame(height: reviewExpanded ? 430 : 620)

            if model.pendingCount > 0 {
                Divider()
                changesBar
                if reviewExpanded {
                    Divider()
                    reviewDrawer
                        .frame(height: 190)
                }
            }
        }
        .frame(width: 1180)
        .background(theme.background.ignoresSafeArea())
        .confirmationDialog(
            text("hades2.saveEditor.workbench.confirmTitle"),
            isPresented: $confirmingApply,
            titleVisibility: .visible
        ) {
            Button(text("hades2.saveEditor.apply"), role: .destructive) {
                model.apply()
            }
            Button(text("hades2.saveEditor.workbench.cancel"), role: .cancel) {}
        } message: {
            Text(text("hades2.saveEditor.workbench.confirmBody", arguments: [model.relativePath]))
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
                reviewExpanded = false
            }
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
            } else {
                ProgressView().controlSize(.small)
            }
            Spacer()
            Menu {
                Text(model.relativePath)
                Text(text("hades2.saveEditor.workbench.sourceHint"))
            } label: {
                Image(systemName: "info.circle")
            }
            .disabled(model.profile.isEmpty)
            .help(text("hades2.saveEditor.workbench.sourceHint"))

            Button {
                selectedEntityID = nil
                model.query(offset: model.offset)
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(model.busy || model.profile.isEmpty)
            .help(localization.localized("host.refresh"))

            Button(localization.localized("host.done")) {
                dismiss()
            }
        }
        .padding(.horizontal, 19)
        .padding(.vertical, 15)
    }

    private var navigation: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Hades2SaveWorkbenchSection.allCases.filter { $0 != .advanced }) { item in
                navigationButton(item)
            }
            Spacer(minLength: 8)
            Divider().padding(.vertical, 8)
            navigationButton(.advanced)
        }
        .padding(10)
        .background(theme.sidebarBackground)
    }

    private func navigationButton(_ item: Hades2SaveWorkbenchSection) -> some View {
        Button {
            guard section != item else { return }
            section = item
            selectedEntityID = nil
            model.selectDomain(item.domain)
        } label: {
            Label(text("hades2.saveEditor.workbench.section." + item.rawValue), systemImage: item.icon)
                .font(.subheadline)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 10)
                .padding(.vertical, 9)
                .background(
                    section == item ? theme.mutedFill : Color.clear,
                    in: RoundedRectangle(cornerRadius: theme.compactCornerRadius)
                )
        }
        .buttonStyle(.plain)
        .disabled(model.busy || model.profile.isEmpty)
    }

    private var resultList: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 10) {
                HStack(spacing: 7) {
                    Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
                    TextField(
                        text("hades2.saveEditor.workbench.search"),
                        text: $model.search
                    )
                    .textFieldStyle(.plain)
                    .onSubmit {
                        selectedEntityID = nil
                        model.submitSearch()
                    }
                    if !model.search.isEmpty {
                        Button {
                            model.search = ""
                            selectedEntityID = nil
                            model.submitSearch()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
                .background(theme.subtleFill, in: RoundedRectangle(cornerRadius: 8))

                if section == .story {
                    Picker(
                        text("hades2.saveEditor.workbench.section.story"),
                        selection: Binding(
                            get: { model.selectedDomain },
                            set: { newDomain in
                                selectedEntityID = nil
                                model.selectDomain(newDomain)
                            }
                        )
                    ) {
                        Text(text("hades2.saveEditor.workbench.story.scenes"))
                            .tag(Hades2SaveEditorDomain.investigate)
                        Text(text("hades2.saveEditor.workbench.story.quests"))
                            .tag(Hades2SaveEditorDomain.progression)
                        Text(text("hades2.saveEditor.workbench.story.flags"))
                            .tag(Hades2SaveEditorDomain.flags)
                        Text(text("hades2.saveEditor.workbench.story.dialogue"))
                            .tag(Hades2SaveEditorDomain.dialogue)
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(14)
            Divider()

            if section == .advanced && !model.advancedPath.isEmpty {
                Button {
                    selectedEntityID = nil
                    model.leaveAdvanced()
                } label: {
                    Label(text("hades2.saveEditor.up"), systemImage: "chevron.left")
                        .lineLimit(1)
                }
                .buttonStyle(.plain)
                .padding(12)
            }

            if model.profile.isEmpty || (model.busy && model.items.isEmpty) {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if model.items.isEmpty {
                TrainerEmptyState(text: text("hades2.saveEditor.empty"))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: 2) {
                        ForEach(entities) { entity in
                            Button {
                                selectEntity(entity)
                            } label: {
                                HStack {
                                    Text(entity.title)
                                        .font(.subheadline)
                                        .lineLimit(2)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                    if selectedEntityID == entity.id {
                                        Image(systemName: "chevron.right")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 11)
                                .background(
                                    selectedEntityID == entity.id
                                        ? theme.mutedFill : Color.clear,
                                    in: RoundedRectangle(cornerRadius: 8)
                                )
                            }
                            .buttonStyle(.plain)
                            .help(entity.entries.first?.rawID ?? entity.title)
                        }
                    }
                    .padding(8)
                }
            }
            Divider()
            pagingControls
                .padding(12)
        }
    }

    private func selectEntity(_ entity: Hades2SaveEditorEntity) {
        selectedEntityID = entity.id
        if entity.entries.count == 1,
           let entry = entity.entries.first,
           entry.domain == "investigate" {
            model.inspect(entry)
        }
    }

    private var pagingControls: some View {
        HStack(spacing: 7) {
            Text(pageSummary)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer()
            Button {
                selectedEntityID = nil
                model.previousPage()
            } label: {
                Image(systemName: "chevron.left")
            }
            .disabled(model.busy || model.offset == 0)
            Button {
                selectedEntityID = nil
                model.nextPage()
            } label: {
                Image(systemName: "chevron.right")
            }
            .disabled(model.busy || model.offset + Hades2SaveEditorModel.pageSize >= model.total)
        }
        .buttonStyle(.borderless)
    }

    private var pageSummary: String {
        guard model.total > 0 else {
            return text("hades2.saveEditor.pageSummary", arguments: ["0", "0", "0"])
        }
        return text(
            "hades2.saveEditor.pageSummary",
            arguments: [
                String(model.offset + 1),
                String(min(model.offset + model.items.count, model.total)),
                String(model.total)
            ]
        )
    }

    private var inspector: some View {
        ScrollView {
            if let entity = selectedEntity {
                VStack(alignment: .leading, spacing: 16) {
                    Text(entity.title)
                        .font(.title2.weight(.semibold))
                        .textSelection(.enabled)
                    ForEach(entity.entries.filter { $0.domain != "investigate" }) { entry in
                        inspectorEntry(entry, entity: entity)
                    }
                    let scenes = entity.entries.filter { $0.domain == "investigate" }
                    if scenes.count == 1, let scene = scenes.first {
                        investigationEntry(scene)
                    } else if !scenes.isEmpty {
                        investigationCollection(scenes)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(22)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "cursorarrow.click.2")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text(text("hades2.saveEditor.workbench.select"))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 320)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func inspectorEntry(
        _ entry: Hades2SaveEditorEntry,
        entity: Hades2SaveEditorEntity
    ) -> some View {
        if entry.domain == "advanced" {
            advancedEntry(entry)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                Text(fieldTitle(entry, in: entity))
                    .font(.subheadline.weight(.medium))
                if entry.editable && !entry.mutationKinds.isEmpty {
                    editorControl(entry)
                    HStack {
                        Button(text("hades2.saveEditor.workbench.addChange")) {
                            stageDraft(for: entry)
                        }
                        .disabled(model.busy || parsedDraft(for: entry) == nil)
                        if model.pendingChanges.contains(where: { $0.entryID == entry.id }) {
                            Text(text("hades2.saveEditor.workbench.staged"))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                } else {
                    if entry.valueType != "table" {
                        Text(valueText(entry.value))
                            .font(.callout.monospacedDigit())
                            .textSelection(.enabled)
                    }
                    if entry.discoveryReasonCode != nil || entry.discoveryReason != nil {
                        DisclosureGroup(text("hades2.saveEditor.workbench.limitation")) {
                            Text(discoveryReason(
                                entry,
                                fallback: entry.discoveryReason ?? text("hades2.saveEditor.discovery.reason.readOnly")
                            ))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.caption)
                    }
                }
                DisclosureGroup(text("hades2.saveEditor.workbench.technical")) {
                    Text(entry.rawID)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .font(.caption)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(theme.subtleFill, in: RoundedRectangle(cornerRadius: 10))
        }
    }

    private func fieldTitle(
        _ entry: Hades2SaveEditorEntry,
        in entity: Hades2SaveEditorEntity
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
    private func editorControl(_ entry: Hades2SaveEditorEntry) -> some View {
        if entry.valueType == "boolean" {
            Toggle(
                booleanTitle(for: entry),
                isOn: Binding(
                    get: { draftBinding(for: entry).wrappedValue == "true" },
                    set: { draftBinding(for: entry).wrappedValue = $0 ? "true" : "false" }
                )
            )
            .toggleStyle(.switch)
        } else if entry.valueType == "enum" && !entry.choices.isEmpty {
            Picker(
                text("hades2.saveEditor.value"),
                selection: draftBinding(for: entry)
            ) {
                ForEach(entry.choices, id: \.self) { choice in
                    Text(entry.choiceNames[choice] ?? enumTitle(choice)).tag(choice)
                }
            }
            .labelsHidden()
            .frame(maxWidth: 240, alignment: .leading)
        } else {
            TextField(
                text("hades2.saveEditor.value"),
                text: draftBinding(for: entry)
            )
            .textFieldStyle(.roundedBorder)
            .frame(maxWidth: 240, alignment: .leading)
            .onSubmit { stageDraft(for: entry) }
        }
    }

    @ViewBuilder
    private func advancedEntry(_ entry: Hades2SaveEditorEntry) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(entry.rawID).font(.headline.monospaced()).textSelection(.enabled)
            if let count = entry.childCount {
                Text(text("hades2.saveEditor.childCount", arguments: [String(count)]))
                    .foregroundStyle(.secondary)
                if !entry.pathAmbiguous {
                    Button(text("hades2.saveEditor.workbench.browse")) {
                        selectedEntityID = nil
                        if model.selectedDomain == .discover {
                            section = .advanced
                            model.openDiscoveryEntry(entry)
                        } else {
                            model.enterAdvanced(entry)
                        }
                    }
                    .disabled(model.busy)
                }
            } else {
                Text(valueText(entry.value))
                    .font(.callout.monospaced())
                    .textSelection(.enabled)
                if model.selectedDomain == .discover && !entry.pathAmbiguous {
                    Button(text("hades2.saveEditor.workbench.browse")) {
                        section = .advanced
                        selectedEntityID = nil
                        model.openDiscoveryEntry(entry)
                    }
                    .disabled(model.busy)
                }
            }
            if entry.pathAmbiguous {
                Text(text("hades2.saveEditor.ambiguousPath"))
                    .foregroundStyle(theme.warning)
                    .font(.caption)
            }
        }
    }

    private func investigationCollection(_ scenes: [Hades2SaveEditorEntry]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(text("hades2.saveEditor.workbench.story.scenes"))
                .font(.headline)
            ForEach(scenes) { scene in
                Button {
                    model.inspect(scene)
                } label: {
                    HStack(alignment: .top, spacing: 8) {
                        Text(scene.investigationSnippet.flatMap {
                            $0.isEmpty ? nil : $0
                        } ?? scene.rawID)
                            .font(.callout)
                            .lineLimit(2)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        if model.selectedInvestigationID == scene.rawID {
                            Image(systemName: "chevron.down")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(10)
                    .background(
                        model.selectedInvestigationID == scene.rawID
                            ? theme.mutedFill : theme.subtleFill,
                        in: RoundedRectangle(cornerRadius: 8)
                    )
                }
                .buttonStyle(.plain)
                .help(scene.rawID)
            }
            if let detail = model.investigationDetail,
               scenes.contains(where: { $0.rawID == detail.scene }) {
                Divider()
                investigationDetailView(detail)
            }
        }
    }

    @ViewBuilder
    private func investigationEntry(_ entry: Hades2SaveEditorEntry) -> some View {
        if let detail = model.investigationDetail, detail.scene == entry.rawID {
            investigationDetailView(detail)
        } else if model.busy {
            ProgressView()
        } else {
            Button(text("hades2.saveEditor.investigate.details")) {
                model.inspect(entry)
            }
        }
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
        HStack(spacing: 10) {
            if model.pendingCount > 0 {
                Button {
                    reviewExpanded.toggle()
                    if reviewExpanded { model.review() }
                } label: {
                    Label(
                        text("hades2.saveEditor.workbench.changes", arguments: [String(model.pendingCount)]),
                        systemImage: "square.stack.3d.up"
                    )
                }
                .buttonStyle(.bordered)
                Spacer()
                Button(text("hades2.saveEditor.workbench.reviewApply")) {
                    reviewExpanded = true
                    model.review()
                }
                .disabled(model.busy)
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
    }

    private var reviewDrawer: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text(text("hades2.saveEditor.review"))
                    .font(.headline)
                Spacer()
                Button(text("hades2.saveEditor.cancelChanges")) {
                    model.cancel()
                }
                .disabled(model.busy)
                Button(text("hades2.saveEditor.apply")) {
                    confirmingApply = true
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.busy)
            }
            Text(text("hades2.saveEditor.workbench.target", arguments: [model.relativePath]))
                .font(.caption)
                .foregroundStyle(.secondary)
            ScrollView {
                LazyVStack(spacing: 7) {
                    ForEach(model.pendingChanges) { change in
                        HStack(spacing: 9) {
                            Text(model.displayName(for: change))
                                .font(.callout.weight(.medium))
                                .lineLimit(1)
                            Spacer()
                            Text(reviewValue(change.before, for: change))
                                .foregroundStyle(.secondary)
                            Image(systemName: "arrow.right")
                                .foregroundStyle(.secondary)
                            Text(reviewValue(change.after, for: change))
                        }
                        .font(.caption.monospacedDigit())
                    }
                }
            }
            Text(text("hades2.saveEditor.coldApplyNotice"))
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .background(theme.panel)
    }

    private func reviewValue(
        _ value: AnyHashable?, for change: Hades2SaveEditorChange
    ) -> String {
        if change.operation == "setEnum", let raw = value?.base as? String {
            return enumTitle(raw)
        }
        if let bool = value?.base as? Bool {
            if change.domain == "dialogue" || change.domain == "flags" {
                return text(bool ? "hades2.saveEditor.true" : "hades2.saveEditor.false")
            }
            return text(bool
                        ? "hades2.saveEditor.workbench.yes"
                        : "hades2.saveEditor.workbench.no")
        }
        return valueText(value)
    }

    private func booleanTitle(for entry: Hades2SaveEditorEntry) -> String {
        if entry.id.hasPrefix("weapon:")
            || entry.id.hasPrefix("familiar:")
            || entry.id.hasSuffix(":Unlocked") {
            return text("hades2.saveEditor.workbench.unlocked")
        }
        if entry.domain == "dialogue" || entry.domain == "flags" {
            return text("hades2.saveEditor.workbench.recorded")
        }
        return text("hades2.saveEditor.workbench.enabled")
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
        if entry.valueType == "string" { return trimmed }
        return nil
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
