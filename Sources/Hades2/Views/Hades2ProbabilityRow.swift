import SwiftUI

/// Hades II's conditional occurrence setting: Native is absence of an override,
/// while 0% and 100% are explicit desired values. A one-shot Generate action
/// can share a row without sharing the preference's lifecycle.
struct Hades2ProbabilityRow: View {
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
    var generateHelp: String = ""
    var canGenerate: Bool = false
    var onGenerate: (() -> Void)? = nil

    var body: some View {
        TrainerRow {
            HStack(spacing: 12) {
                TrainerIconLabel(title: title, icon: icon)
                    .help(probabilityHelp)
                Spacer(minLength: 8)
                TrainerTextField(
                    title: nativeLabel,
                    text: $input,
                    onEditingChanged: onEditingChanged,
                    onCommit: onCommit,
                    alignment: .center
                )
                .frame(width: 82)
                .disabled(!enabled)
                .accessibilityLabel(title + " " + probabilityLabel)
                .help(probabilityHelp)
                Text(input.isEmpty ? "" : "%")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 14)
                if hasOverride {
                    Button(action: onReset) {
                        Image(systemName: "arrow.uturn.backward")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(theme.accent)
                            .frame(width: 26, height: 24)
                            .background(theme.subtleFill, in: RoundedRectangle(cornerRadius: theme.compactCornerRadius))
                    }
                    .buttonStyle(.plain)
                    .disabled(!enabled)
                    .help(resetLabel)
                    .accessibilityLabel(resetLabel)
                } else {
                    Color.clear.frame(width: 26, height: 24)
                }
                if let onGenerate, let generateLabel {
                    Button(generateLabel, action: onGenerate)
                        .buttonStyle(.bordered)
                        .lineLimit(1)
                        .disabled(!canGenerate)
                        .help(generateHelp)
                        .accessibilityLabel(title + " " + generateLabel)
                }
            }
        }
    }
}
