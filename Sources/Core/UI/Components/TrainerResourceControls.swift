import SwiftUI

struct TrainerPickerSection<Item: Identifiable>: Identifiable {
    let id: Int
    let title: String
    let items: [Item]
}

struct TrainerResourceEditor<Item: Identifiable>: View where Item.ID == String {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let title: String
    let icon: String
    @Binding var search: String
    @Binding var selection: String
    @Binding var amount: String
    let sections: [TrainerPickerSection<Item>]
    let enabled: Bool
    let locked: Bool
    let searchPlaceholder: String
    let emptyLabel: String
    let itemLabel: (Item) -> String
    let onLock: () -> Void
    let onCommit: (TrainerTextField.Completion) -> String
    let onEditingChanged: (Bool) -> Void

    init(
        title: String,
        icon: String,
        search: Binding<String>,
        selection: Binding<String>,
        amount: Binding<String>,
        sections: [TrainerPickerSection<Item>],
        enabled: Bool,
        locked: Bool,
        searchPlaceholder: String = "host.resource.searchPlaceholder",
        emptyLabel: String = "host.resource.noMatches",
        itemLabel: @escaping (Item) -> String,
        onLock: @escaping () -> Void,
        onEditingChanged: @escaping (Bool) -> Void = { _ in },
        onCommit: @escaping (TrainerTextField.Completion) -> String = { $0.text }
    ) {
        self.title = title
        self.icon = icon
        self._search = search
        self._selection = selection
        self._amount = amount
        self.sections = sections
        self.enabled = enabled
        self.locked = locked
        self.searchPlaceholder = searchPlaceholder
        self.emptyLabel = emptyLabel
        self.itemLabel = itemLabel
        self.onLock = onLock
        self.onEditingChanged = onEditingChanged
        self.onCommit = onCommit
    }

    var body: some View {
        VStack(alignment: .leading, spacing: theme.sectionSpacing) {
            HStack {
                // Same icon treatment as every other functional row: the icon
                // carries this editor's on/off state instead of a fixed accent.
                TrainerIconLabel(
                    title: title,
                    icon: icon,
                    tint: enabled ? theme.accent : theme.inactive,
                    emphasized: enabled
                )
                Spacer()
                TrainerSearchField(
                    text: $search,
                    placeholder: localization.presentation(searchPlaceholder),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(maxWidth: 260)
            }

            HStack(spacing: 12) {
                Picker(title, selection: $selection) {
                    if selection.isEmpty || sections.allSatisfy({ $0.items.isEmpty }) {
                        Text(localization.presentation(emptyLabel)).tag("")
                    }
                    ForEach(sections) { section in
                        Section(header: Text(section.title)) {
                            ForEach(section.items) { item in
                                Text(itemLabel(item)).tag(item.id)
                            }
                        }
                    }
                }
                .labelsHidden()
                .trainerPickerWidth(.flexible)
                .disabled(!enabled || sections.allSatisfy({ $0.items.isEmpty }))

                TrainerNumberField(
                    text: $amount,
                    placeholder: "host.amount",
                    width: 100,
                    enabled: enabled && !selection.isEmpty,
                    alignment: .leading,
                    onEditingChanged: onEditingChanged,
                    onCommit: onCommit
                )
                .id(selection)

                TrainerLockButton(
                    title: title,
                    locked: locked,
                    enabled: enabled && !selection.isEmpty,
                    action: onLock
                )
            }
        }
    }
}

struct TrainerGroupedOptionPicker<Item: Identifiable>: View where Item.ID == String {
    let title: String?
    let icon: String?
    let pickerLabel: String
    @Environment(\.trainerTheme) private var theme
    @Binding var selection: String
    let sections: [TrainerPickerSection<Item>]
    let enabled: Bool
    var actionEnabled: Bool? = nil
    var inline: Bool = false
    let emptyLabel: String
    let actionTitle: String
    let shortcutText: String?
    let itemLabel: (Item) -> String
    let onAction: (String) -> Void

    private var allItems: [Item] { sections.flatMap(\.items) }
    private var actionAvailable: Bool {
        enabled && (actionEnabled ?? true) && allItems.contains { $0.id == selection }
    }

    /// The row title uses the same on/off treatment as every other feature row:
    /// the icon and its emphasis describe whether this row's action is live.
    private var state: TrainerFeatureControlState {
        TrainerFeatureControlState(
            isOn: actionAvailable,
            isInteractive: actionAvailable,
            canEditValue: actionAvailable,
            opacity: 1,
            indicatorColor: actionAvailable ? theme.accent : theme.inactive,
            helpText: "",
            isWarning: false
        )
    }

    @ViewBuilder
    private var titleLabel: some View {
        if let title, let icon {
            TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)
        }
    }

    @ViewBuilder
    private var optionPicker: some View {
        Picker(pickerLabel, selection: $selection) {
            if selection.isEmpty || allItems.isEmpty {
                Text(emptyLabel).tag("")
            }
            ForEach(sections) { section in
                Section(header: Text(section.title)) {
                    ForEach(section.items) { item in
                        Text(itemLabel(item)).tag(item.id)
                    }
                }
            }
        }
        .labelsHidden()
        .trainerPickerWidth(inline ? .wide : .flexible)
        .disabled(!enabled || allItems.isEmpty)
    }

    @ViewBuilder
    private var actionControls: some View {
        TrainerShortcutBadgeSlot(text: shortcutText)
        TrainerSecondaryActionButton(
            title: actionTitle,
            enabled: actionAvailable,
            width: theme.compactActionWidth
        ) {
            guard actionAvailable else { return }
            onAction(selection)
        }
    }

    var body: some View {
        Group {
            if inline {
                if let title, let icon {
                    TrainerLabeledControlRow(title: title, icon: icon, tint: state.indicatorColor,
                                             emphasized: state.isOn) {
                        optionPicker
                        actionControls
                    }
                } else {
                    TrainerRow {
                        HStack(spacing: 16) {
                            optionPicker
                            actionControls
                        }
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: title == nil ? 0 : 10) {
                    titleLabel
                    HStack(spacing: 12) {
                        optionPicker
                        actionControls
                    }
                }
            }
        }
    }
}
