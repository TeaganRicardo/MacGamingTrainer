import SwiftUI
import AppKit

struct Hades2ProfileManagerView: View {
    @ObservedObject var model: Hades2TrainerModel
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Binding var isPresented: Bool
    @State private var profileName = ""
    @State private var selectedProfile = ""

    /// Resolve one Hades presentation key against the live Host language.
    private func text(_ key: String) -> String {
        Hades2GameModule.presentationText(key: key, arguments: [], language: localization.language)
    }

    var body: some View {
        TrainerSheetScaffold(title: text("hades2.manage.profiles"), icon: "slider.horizontal.3", width: 620) {
            Button(localization.localized("host.refresh")) { model.listProfiles() }.disabled(model.busy)
        } content: {
            Text(text("hades2.profile.explanation"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                TextField(text("hades2.profile.namePlaceholder"), text: $profileName).textFieldStyle(.roundedBorder)
                Button(text("hades2.profile.saveCurrent")) {
                    model.saveProfile(profileName)
                    selectedProfile = profileName.trimmingCharacters(in: .whitespacesAndNewlines)
                }
                .disabled(model.busy || profileName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
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
                HStack {
                    TrainerPrimaryActionButton(
                        title: text("hades2.profile.load"),
                        enabled: !model.busy && !selectedProfile.isEmpty,
                        action: { model.loadProfile(selectedProfile) }
                    )
                    Button(role: .destructive) { model.deleteProfile(selectedProfile) } label: {
                        Label(localization.localized("host.delete"), systemImage: "trash")
                    }
                        .disabled(model.busy || selectedProfile.isEmpty)
                    Spacer()
                }
            }
        } footer: {
            HStack { Spacer(); Button(localization.localized("host.done")) { isPresented = false } }
        }
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
        Hades2GameModule.presentationText(key: key, arguments: [], language: localization.language)
    }

    var body: some View {
        TrainerSheetScaffold(title: text("hades2.diagnostics.title"), icon: "stethoscope", width: 700) {
            Text("\(model.diagnosticsPassed)/\(model.diagnosticsTotal)").font(.headline).monospacedDigit()
            Button { model.exportDiagnostics() } label: {
                Label(text("hades2.diagnostics.export"), systemImage: "square.and.arrow.up")
            }
                .disabled(model.busy || !model.backendAvailable)
            Button(text("hades2.diagnostics.rerun")) { model.runDiagnostics() }.disabled(model.busy)
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
    private func text(_ key: String) -> String {
        Hades2GameModule.presentationText(key: key, arguments: [], language: localization.language)
    }

    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.shortcutSettings"), width: 560) {
            EmptyView()
        } content: {
            Text(localization.localized("host.hotkeys.help"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(ShortcutAction.uiOrder) { action in
                HStack {
                    Text(text(action.presentationKey))
                    Spacer()
                    Button {
                        beginCapture(action)
                    } label: {
                        Text(capturing == action ? localization.localized("host.hotkeys.pressNew") : model.shortcutText(action))
                            .font(.system(.body, design: .monospaced))
                            .frame(minWidth: 110)
                    }
                    .buttonStyle(.bordered)
                }
            }
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