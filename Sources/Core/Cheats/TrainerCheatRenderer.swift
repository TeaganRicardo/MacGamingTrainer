import SwiftUI

extension TrainerCheatLabel {
    @MainActor
    package func resolve(using localization: TrainerLocalizationStore) -> String {
        switch self {
        case .key(let key):
            return localization.string(key)
        case .bilingual(let text):
            return localization.language == .en ? text.en : text.zhCN
        }
    }
}

package struct TrainerCheatToggleRow: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let definition: TrainerCheatDefinition
    let state: TrainerFeatureControlState
    let shortcutText: String?
    let action: () -> Void

    package init(
        definition: TrainerCheatDefinition,
        state: TrainerFeatureControlState,
        shortcutText: String? = nil,
        action: @escaping () -> Void
    ) {
        self.definition = definition
        self.state = state
        self.shortcutText = shortcutText
        self.action = action
    }

    package var body: some View {
        TrainerFeatureToggleRow(
            title: definition.label.resolve(using: localization),
            icon: definition.icon,
            state: state,
            helpText: definition.help?.resolve(using: localization) ?? "",
            shortcutText: shortcutText,
            action: action
        )
    }
}

package struct TrainerCheatMultiplierRow: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let definition: TrainerCheatDefinition
    let state: TrainerFeatureControlState
    @Binding var text: String
    let onCommit: (TrainerTextField.Completion) -> String
    let onEditingChanged: (Bool) -> Void
    let shortcutText: String?
    let action: () -> Void

    package init(
        definition: TrainerCheatDefinition,
        state: TrainerFeatureControlState,
        text: Binding<String>,
        onCommit: @escaping (TrainerTextField.Completion) -> String,
        onEditingChanged: @escaping (Bool) -> Void = { _ in },
        shortcutText: String? = nil,
        action: @escaping () -> Void
    ) {
        self.definition = definition
        self.state = state
        self._text = text
        self.onCommit = onCommit
        self.onEditingChanged = onEditingChanged
        self.shortcutText = shortcutText
        self.action = action
    }

    package var body: some View {
        TrainerFeatureMultiplierRow(
            title: definition.label.resolve(using: localization),
            icon: definition.icon,
            state: state,
            text: $text,
            onCommit: onCommit,
            onEditingChanged: onEditingChanged,
            shortcutText: shortcutText,
            action: action
        )
    }
}

package struct TrainerCheatValueFieldRow<Trailing: View>: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let definition: TrainerCheatDefinition
    let tint: Color
    let emphasized: Bool
    let opacity: Double
    let enabled: Bool
    @Binding var text: String
    let placeholder: String
    let fieldWidth: CGFloat
    let accessibilityIdentifier: String?
    let onEditingChanged: (Bool) -> Void
    let onCommit: (TrainerTextField.Completion) -> String
    let trailing: Trailing

    package init(
        definition: TrainerCheatDefinition,
        tint: Color,
        emphasized: Bool = false,
        opacity: Double = 1,
        enabled: Bool = true,
        text: Binding<String>,
        placeholder: String = "host.value",
        fieldWidth: CGFloat = 90,
        accessibilityIdentifier: String? = nil,
        onEditingChanged: @escaping (Bool) -> Void = { _ in },
        onCommit: @escaping (TrainerTextField.Completion) -> String = { $0.text },
        @ViewBuilder trailing: () -> Trailing
    ) {
        self.definition = definition
        self.tint = tint
        self.emphasized = emphasized
        self.opacity = opacity
        self.enabled = enabled
        self._text = text
        self.placeholder = placeholder
        self.fieldWidth = fieldWidth
        self.accessibilityIdentifier = accessibilityIdentifier
        self.onEditingChanged = onEditingChanged
        self.onCommit = onCommit
        self.trailing = trailing()
    }

    package var body: some View {
        let title = definition.label.resolve(using: localization)
        TrainerLabeledControlRow(
            title: title,
            icon: definition.icon,
            tint: tint,
            emphasized: emphasized,
            opacity: opacity,
            helpText: definition.help?.resolve(using: localization) ?? ""
        ) {
            TrainerNumberField(
                text: $text,
                placeholder: placeholder,
                accessibilityLabel: title,
                accessibilityIdentifier: accessibilityIdentifier,
                width: fieldWidth,
                enabled: enabled,
                alignment: .trailing,
                onEditingChanged: onEditingChanged,
                onCommit: onCommit
            )
            trailing
        }
    }
}

package struct TrainerCheatOneShotRow<Badge: View, ActionButton: View>: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let definition: TrainerCheatDefinition
    let tint: Color
    let emphasized: Bool
    let opacity: Double
    let badge: Badge
    let actionButton: ActionButton

    package init(
        definition: TrainerCheatDefinition,
        tint: Color,
        emphasized: Bool = false,
        opacity: Double = 1,
        @ViewBuilder badge: () -> Badge,
        @ViewBuilder actionButton: () -> ActionButton
    ) {
        self.definition = definition
        self.tint = tint
        self.emphasized = emphasized
        self.opacity = opacity
        self.badge = badge()
        self.actionButton = actionButton()
    }

    package var body: some View {
        TrainerLabeledControlRow(
            title: definition.label.resolve(using: localization),
            icon: definition.icon,
            tint: tint,
            emphasized: emphasized,
            opacity: opacity,
            helpText: definition.help?.resolve(using: localization) ?? ""
        ) {
            badge
            actionButton
        }
    }
}
