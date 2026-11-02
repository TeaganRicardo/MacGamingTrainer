import SwiftUI

/// Game modules supply their own ordered actions, translated labels, icon
/// semantics, live chord values and storage callbacks. This view knows none of
/// their action identities, validation rules or persistence formats.
struct TrainerShortcutSettingsEntry: Identifiable {
    let id: String
    let title: String
    let icon: String
    let chordText: String
    let isEditable: Bool
}

struct TrainerShortcutSettingsView: View {
    @Binding private var isPresented: Bool
    let entries: [TrainerShortcutSettingsEntry]
    let registrationFailure: TrainerHotkeyRegistrationFailure?
    let resetTitle: String?
    let onReset: (() -> Void)?
    let onAssign: (String, HotkeyChord) -> TrainerShortcutAssignmentResult

    @Environment(\.trainerTheme) private var theme
    @Environment(\.trainerGamePageVisibility) private var pageVisibility
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @StateObject private var capture = TrainerShortcutCaptureController()
    @State private var lifetime = TrainerSheetLifetime()

    init(
        isPresented: Binding<Bool>,
        entries: [TrainerShortcutSettingsEntry],
        registrationFailure: TrainerHotkeyRegistrationFailure? = nil,
        resetTitle: String? = nil,
        onReset: (() -> Void)? = nil,
        onAssign: @escaping (String, HotkeyChord) -> TrainerShortcutAssignmentResult
    ) {
        _isPresented = isPresented
        self.entries = entries
        self.registrationFailure = registrationFailure
        self.resetTitle = resetTitle
        self.onReset = onReset
        self.onAssign = onAssign
    }

    var body: some View {
        let presentationID = lifetime.id
        TrainerSheetScaffold(
            title: localization.localized("host.shortcutSettings"),
            icon: TrainerSemanticIcon.Tool.shortcuts, width: 560, minimumWidth: 360
        ) {
            if let resetTitle, let onReset {
                Button(resetTitle) {
                    guard lifetime.accepts(presentationID), isPresented, pageVisibility?.isVisible ?? true else { return }
                    capture.cancel()
                    onReset()
                }
            }
        } content: {
            Text(localization.localized("host.hotkeys.help"))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: theme.sheetSpacing) {
                    ForEach(entries) { entry in
                        HStack {
                            Label(entry.title, systemImage: entry.icon)
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer()
                            if entry.isEditable {
                                Button {
                                    guard lifetime.accepts(presentationID), isPresented, pageVisibility?.isVisible ?? true else { return }
                                    capture.begin(actionID: entry.id, onAssign: onAssign)
                                } label: {
                                    shortcutLabel(
                                        capture.capturingActionID == entry.id
                                        ? localization.localized("host.hotkeys.pressNew") : entry.chordText
                                    )
                                    .contentTransition(.opacity)
                                    .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion),
                                               value: capture.capturingActionID == entry.id)
                                }
                                .buttonStyle(.bordered)
                                .accessibilityIdentifier("trainer.shortcut.capture." + entry.id)
                            } else {
                                // Fixed panic bindings are displayed, not clickable.
                                shortcutLabel(entry.chordText)
                                    .foregroundStyle(.secondary)
                                    .accessibilityIdentifier("trainer.shortcut.fixed." + entry.id)
                            }
                        }
                    }
                }
            }
            .frame(maxHeight: 560)
            if let message = issueText {
                Text(message)
                    .foregroundStyle(theme.warning)
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
                    .contentTransition(.opacity)
                    .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: message)
            }
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done")) {
                    guard lifetime.accepts(presentationID) else { return }
                    lifetime.invalidate()
                    capture.cancel()
                    isPresented = false
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .onAppear { lifetime.appear() }
        .onDisappear { lifetime.invalidate(); capture.cancel() }
        .onExitCommand {
            if capture.capturingActionID != nil { capture.cancel() }
            else if lifetime.accepts(presentationID) {
                lifetime.invalidate()
                isPresented = false
            }
        }
        .onChange(of: isPresented) { _, visible in
            if visible { lifetime.appear() }
            else { lifetime.invalidate(); capture.cancel() }
        }
        .background {
            TrainerGamePageVisibilityObserver { visible in
                if !visible {
                    lifetime.invalidate()
                    capture.cancel()
                    isPresented = false
                }
            }
        }
        .onChange(of: entries.map(\.id)) { _, ids in
            if let selected = capture.capturingActionID, !ids.contains(selected) {
                capture.cancel()
            }
        }
    }

    private func shortcutLabel(_ value: String) -> some View {
        Text(value)
            .font(.system(.body, design: .monospaced))
            .frame(width: theme.shortcutCaptureWidth, alignment: .center)
    }

    private var issueText: String? {
        if let issue = capture.issue {
            switch issue {
            case .unrecognized:
                return localization.localized("host.hotkeys.unrecognized")
            case .conflict(let chord, let actionID):
                let title = entries.first(where: { $0.id == actionID })?.title ?? actionID
                return localization.localized("host.hotkeys.conflict", arguments: [chord, title])
            case .rejected(let key):
                return localization.string(key)
            }
        }
        guard let failure = registrationFailure else { return nil }
        switch failure {
        case .listenerInitialization(let status):
            return localization.localized("host.hotkeys.listenerFailed", arguments: [String(status)])
        case .registrationConflicts(let conflicts):
            let details = conflicts.map { conflict in
                let title = entries.first(where: { $0.id == conflict.actionID })?.title ?? conflict.actionID
                return "\(conflict.chordText) \(title) (\(conflict.status))"
            }.joined(separator: ", ")
            return localization.localized("host.hotkeys.registrationFailed", arguments: [details])
        }
    }
}
