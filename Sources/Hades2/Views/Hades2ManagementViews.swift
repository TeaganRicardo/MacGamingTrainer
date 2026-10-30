import SwiftUI
import AppKit

struct Hades2ProfileManagerView: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme
    @Binding var isPresented: Bool
    @State private var profileName = ""
    @State private var selectedProfile = ""

    /// Resolve one Hades presentation key against the live Host language.
    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerSheetScaffold(title: text("hades2.manage.profiles"), icon: TrainerSemanticIcon.Tool.profiles, width: 620) {
            Button { model.listProfiles() } label: {
                Label(localization.localized("host.refresh"), systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(model.busy)
        } content: {
            Text(text("hades2.profile.explanation"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let warning = model.profileShortcutWarning {
                Text(localization.string(warning))
                    .foregroundStyle(theme.warning)
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                TrainerTextField(
                    title: text("hades2.profile.namePlaceholder"),
                    text: $profileName
                )
                .frame(maxWidth: .infinity)
                TrainerPrimaryActionButton(
                    title: text("hades2.profile.saveCurrent"),
                    systemImage: TrainerSemanticIcon.Action.save,
                    enabled: !model.busy && !profileName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ) {
                    model.saveProfile(profileName)
                    selectedProfile = profileName.trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            Divider()
            if model.profiles.isEmpty {
                TrainerEmptyState(text: text("hades2.profile.empty"))
            } else {
                Picker(text("hades2.profile.picker"), selection: $selectedProfile) {
                    ForEach(model.profiles) { profile in
                        Text(profile.updatedAt.isEmpty ? profile.name : "\(profile.name) · \(profile.updatedAt)").tag(profile.name)
                    }
                }
                .trainerPickerWidth(.wide)
                HStack {
                    TrainerPrimaryActionButton(
                        title: text("hades2.profile.load"),
                        systemImage: TrainerSemanticIcon.Action.load,
                        enabled: !model.busy && !selectedProfile.isEmpty,
                        action: { model.loadProfile(selectedProfile) }
                    )
                    Button(role: .destructive) { model.deleteProfile(selectedProfile) } label: {
                        Label(localization.localized("host.delete"), systemImage: TrainerSemanticIcon.Action.remove)
                    }
                        .disabled(model.busy || selectedProfile.isEmpty)
                    Spacer()
                }
            }
        } footer: {
            HStack { Spacer(); Button(localization.localized("host.done")) { isPresented = false } }
        }
        .onDisappear { model.clearProfileShortcutWarning() }
        .onChange(of: model.profiles.map(\.name), initial: true) { _, names in
            if !names.contains(selectedProfile) {
                selectedProfile = names.first ?? ""
            }
        }
    }
}

struct Hades2DiagnosticsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Binding var isPresented: Bool
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore

    /// Resolve one Hades presentation key against the live Host language.
    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerSheetScaffold(title: text("hades2.diagnostics.title"), icon: TrainerSemanticIcon.Tool.diagnostics, width: 700) {
            Text("\(model.diagnosticsPassed)/\(model.diagnosticsTotal)").font(.headline).monospacedDigit()
            Button { model.exportDiagnostics() } label: {
                Label(text("hades2.diagnostics.export"), systemImage: TrainerSemanticIcon.Tool.exportDiagnostics)
            }
                .disabled(model.busy || !model.backendAvailable)
            Button { model.runDiagnostics() } label: {
                Label(text("hades2.diagnostics.rerun"), systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(model.busy)
        } content: {
            Text(text("hades2.diagnostics.explanation"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(model.diagnostics) { check in
                        TrainerListCard {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: check.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                    .foregroundStyle(check.ok ? theme.success : theme.warning)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(check.name).font(.subheadline.weight(.semibold))
                                    if !check.detail.isEmpty {
                                        Text(check.detail).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                    }
                                }
                                Spacer()
                            }
                        }
                    }
                }
            }
            .frame(minHeight: 260, maxHeight: 430)
        } footer: {
            HStack { Spacer(); Button(localization.localized("host.done")) { isPresented = false } }
        }
    }
}

struct Hades2ShortcutSettingsView: View {
    @ObservedObject var model: Hades2TrainerModel
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var capturing: ShortcutAction?
    @State private var keyMonitor: Any?

    /// Resolve one Hades presentation key against the live Host language.
    ///
    /// Some shell actions the module hosts (Disable All) deliberately keep their
    /// Host key and Host resource, so a non-Hades prefix must resolve through the
    /// Host table rather than being looked up as a Hades key.
    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.shortcutSettings"), icon: TrainerSemanticIcon.Tool.shortcuts, width: 560) {
            EmptyView()
        } content: {
            Text(localization.localized("host.hotkeys.help"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: theme.sheetSpacing) {
                    ForEach(Hades2WorkbenchCatalog.orderedShortcutActions) { action in
                        HStack {
                            Label(text(action.presentationKey), systemImage: action.icon)
                            Spacer()
                            Button {
                                beginCapture(action)
                            } label: {
                                Text(capturing == action ? localization.localized("host.hotkeys.pressNew") : model.shortcutText(action))
                                    .font(.system(.body, design: .monospaced))
                                    .frame(width: theme.shortcutCaptureWidth, alignment: .center)
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
            .frame(maxHeight: 560)
            if let issue = model.shortcutIssue {
                Text(shortcutIssueText(issue))
                    .foregroundStyle(theme.warning)
                    .font(.caption)
            }
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done")) {
                    stopCapture()
                    model.shortcutSettingsPresented = false
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .onDisappear { stopCapture() }
    }

    private func beginCapture(_ action: ShortcutAction) {
        stopCapture()
        capturing = action
        model.clearShortcutIssue()
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                DispatchQueue.main.async { stopCapture() }
                return nil
            }
            guard let chord = HotkeyChord.capture(event) else {
                model.setUnrecognizedShortcutIssue()
                return nil
            }
            DispatchQueue.main.async {
                model.setShortcut(action: action, chord: chord)
                stopCapture()
            }
            return nil
        }
    }

    private func shortcutIssueText(_ issue: Hades2ShortcutIssue) -> String {
        switch issue {
        case .unrecognized:
            return localization.localized("host.hotkeys.unrecognized")
        case let .conflict(chordText, action):
            return localization.localized(
                "host.hotkeys.conflict",
                arguments: [chordText, text(action.presentationKey)]
            )
        case let .registration(.listenerInitialization(status)):
            return localization.localized("host.hotkeys.listenerFailed", arguments: [String(status)])
        case let .registration(.registrationConflicts(conflicts)):
            let details = conflicts.map { conflict in
                let title = ShortcutAction(rawValue: conflict.actionID).map { text($0.presentationKey) } ?? conflict.actionID
                return "\(conflict.chordText) \(title) (\(conflict.status))"
            }.joined(separator: ", ")
            return localization.localized("host.hotkeys.registrationFailed", arguments: [details])
        }
    }

    private func stopCapture() {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
            self.keyMonitor = nil
        }
        capturing = nil
    }
}

struct Hades2ManagementUtilities: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerManagementActions) private var managementActions
    @Environment(\.trainerTheme) private var theme
    let openProfiles: () -> Void
    let openSaveEditor: () -> Void
    let openDiagnostics: () -> Void

    private func text(_ key: String) -> String {
        Hades2GameModule.resolveText(key: key, localization: localization)
    }

    private var canUseBackend: Bool {
        model.backendAvailable && model.protocolCompatible && !model.exiting
    }

    private var canStartBackendAction: Bool { canUseBackend && !model.busy }

    private var canChangeSignature: Bool {
        canStartBackendAction && !model.connected && model.pid == nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sheetSpacing) {
            managementGroup("hades2.manage.daily") {
                actionButtons {
                    TrainerSecondaryActionButton(
                        title: text("hades2.saveEditor.title"),
                        systemImage: TrainerSemanticIcon.Tool.saveEditor,
                        enabled: canUseBackend,
                        action: openSaveEditor
                    )
                    if let openSaveManagement = managementActions.openSaveManagement {
                        TrainerSecondaryActionButton(
                            title: localization.localized("host.saveManagement"),
                            systemImage: TrainerSemanticIcon.Tool.saveManagement,
                            enabled: canUseBackend,
                            action: openSaveManagement
                        )
                    }
                    TrainerSecondaryActionButton(
                        title: localization.localized("host.disableAll"),
                        systemImage: TrainerSemanticIcon.Tool.disableAll,
                        enabled: model.connected && canUseBackend && model.canAcceptRuntimeAction,
                        action: model.disableAll
                    )
                }
            }
            Divider()
            managementGroup("hades2.manage.settings") {
                actionButtons {
                    TrainerSecondaryActionButton(
                        title: text("hades2.manage.profiles"),
                        systemImage: TrainerSemanticIcon.Tool.profiles,
                        enabled: canStartBackendAction,
                        action: openProfiles
                    )
                    TrainerSecondaryActionButton(
                        title: localization.localized("host.shortcutSettings"),
                        systemImage: TrainerSemanticIcon.Tool.shortcuts,
                        enabled: !model.exiting,
                        action: { model.shortcutSettingsPresented = true }
                    )
                }
            }
            Divider()
            managementGroup("hades2.manage.maintenance") {
                actionButtons {
                    TrainerSecondaryActionButton(
                        title: localization.localized("host.viewLog"),
                        systemImage: TrainerSemanticIcon.Tool.log,
                        action: model.openLog
                    )
                    TrainerSecondaryActionButton(
                        title: text("hades2.manage.diagnostics"),
                        systemImage: TrainerSemanticIcon.Tool.diagnostics,
                        enabled: canStartBackendAction,
                        action: openDiagnostics
                    )
                }
                Text(text("hades2.manage.signatureExplanation"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                actionButtons {
                    TrainerSecondaryActionButton(
                        title: text("hades2.manage.prepareSigning"),
                        systemImage: Hades2WorkbenchIcon.prepareSigning,
                        enabled: canChangeSignature,
                        action: model.prepareDebugging
                    )
                    TrainerSecondaryActionButton(
                        title: text("hades2.manage.restoreSigning"),
                        systemImage: Hades2WorkbenchIcon.restoreSigning,
                        enabled: canChangeSignature,
                        action: model.restoreOriginalSignature
                    )
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .trainerPanel()
    }

    private func managementGroup<Content: View>(
        _ titleKey: String, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: theme.controlPadding) {
            Text(text(titleKey))
                .font(.subheadline.weight(.semibold))
                .accessibilityAddTraits(.isHeader)
            content()
        }
    }

    private func actionButtons<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: theme.controlPadding) { content() }
            VStack(alignment: .leading, spacing: theme.controlPadding) { content() }
        }
    }
}
