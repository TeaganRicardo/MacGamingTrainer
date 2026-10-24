import SwiftUI

/// Hades II's conditional occurrence setting: Native is absence of an override,
/// while 0% and 100% are explicit desired values. A one-shot Generate action
/// can share a row without sharing the preference's lifecycle.
struct Hades2OccurrenceSetting: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    @Binding var input: String
    let hasOverride: Bool
    let enabled: Bool
    let probabilityLabel: String
    let nativeLabel: String
    let resetLabel: String
    let probabilityHelp: String
    let onEditingChanged: (Bool) -> Void
    let onCommit: (TrainerTextField.Completion) -> String
    let onReset: () -> Void
    var generateLabel: String? = nil
    var generateShortcutText: String? = nil
    var generateHelp: String = ""
    var canGenerate: Bool = false
    var onGenerate: (() -> Void)? = nil

    var body: some View {
        TrainerLabeledControlRow(
            title: title, icon: icon,
            tint: hasOverride ? theme.accent : theme.inactive,
            emphasized: hasOverride, helpText: probabilityHelp
        ) {
            TrainerTextField(
                title: nativeLabel,
                text: $input,
                accessibilityLabel: title + " " + probabilityLabel,
                onEditingChanged: onEditingChanged,
                onCommit: onCommit,
                alignment: .center
            )
            .frame(width: 82)
            .disabled(!enabled)
            .help(probabilityHelp)
            Text(input.isEmpty ? "" : "%")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .frame(width: 14)
            if hasOverride {
                TrainerResetButton(title: resetLabel, enabled: enabled, action: onReset)
            } else {
                Color.clear.frame(width: 26, height: 24)
            }
            if let onGenerate, let generateLabel {
                TrainerShortcutBadgeSlot(text: generateShortcutText)
                TrainerSecondaryActionButton(
                    title: generateLabel,
                    enabled: canGenerate,
                    width: theme.compactActionWidth,
                    helpText: generateHelp,
                    accessibilityLabel: title + " " + generateLabel,
                    action: onGenerate
                )
            }
        }
    }
}
