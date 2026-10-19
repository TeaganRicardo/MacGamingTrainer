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
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label(title, systemImage: icon)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(theme.accent)
                Spacer()
                TrainerSearchField(
                    text: $search,
                    placeholder: localization.presentation(searchPlaceholder),
                    clearLabel: localization.localized("host.search.clear")
                )
                .frame(maxWidth: 260)
            }
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
            .frame(maxWidth: .infinity)
            .disabled(!enabled || sections.allSatisfy({ $0.items.isEmpty }))

            HStack(spacing: 12) {
                Spacer()
                TrainerNumberField(text: $amount, placeholder: "host.amount", width: 100, enabled: enabled && !selection.isEmpty, alignment: .leading, onEditingChanged: onEditingChanged, onCommit: onCommit)
                    .id(selection)
                TrainerLockButton(
                    locked: locked,
                    enabled: enabled && !selection.isEmpty,
                    action: onLock
                )
                .accessibilityLabel(localization.localized(locked ? "host.unlock" : "host.lock"))
                .help(localization.localized(locked ? "host.unlock" : "host.lock"))
            }
        }
    }
}

struct TrainerGroupedOptionPicker<Item: Identifiable>: View where Item.ID == String {
    let title: String?
    let icon: String?
    let pickerLabel: String
    @Binding var selection: String
    let sections: [TrainerPickerSection<Item>]
    let enabled: Bool
    let emptyLabel: String
    let actionTitle: String
    let shortcutText: String?
    let itemLabel: (Item) -> String
    let onAction: (String) -> Void

    private var allItems: [Item] { sections.flatMap(\.items) }

    var body: some View {
        let selectedID = selection
        let hasSelection = allItems.contains { $0.id == selectedID }
        return VStack(alignment: .leading, spacing: title == nil ? 0 : 10) {
            if let title, let icon {
                Label(title, systemImage: icon).font(.subheadline.weight(.medium))
            }
            HStack(spacing: 12) {
                Picker(pickerLabel, selection: $selection) {
                    if selectedID.isEmpty || allItems.isEmpty {
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
                .frame(maxWidth: .infinity)
                .disabled(!enabled || allItems.isEmpty)

                TrainerShortcutBadgeSlot(text: shortcutText)
                Button(actionTitle) {
                    guard hasSelection else { return }
                    onAction(selectedID)
                }
                .disabled(!enabled || !hasSelection)
            }
        }
    }
}
