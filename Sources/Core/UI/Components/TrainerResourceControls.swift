import SwiftUI

struct TrainerPickerSection<Item: Identifiable>: Identifiable {
    let id: Int
    let title: String
    let items: [Item]
}

struct TrainerResourceEditor<Item: Identifiable>: View where Item.ID == String {
    @Environment(\.trainerTheme) private var theme
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

    init(
        title: String,
        icon: String,
        search: Binding<String>,
        selection: Binding<String>,
        amount: Binding<String>,
        sections: [TrainerPickerSection<Item>],
        enabled: Bool,
        locked: Bool,
        searchPlaceholder: String = "搜索名称或资源 ID",
        emptyLabel: String = "没有匹配项目",
        itemLabel: @escaping (Item) -> String,
        onLock: @escaping () -> Void
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
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Label(title, systemImage: icon)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(theme.accent)
                Spacer()
                TextField(searchPlaceholder, text: $search)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 260)
            }
            Picker(title, selection: $selection) {
                if selection.isEmpty || sections.allSatisfy({ $0.items.isEmpty }) {
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
            .disabled(!enabled || sections.allSatisfy({ $0.items.isEmpty }))

            HStack(spacing: 12) {
                Spacer()
                TrainerNumberField(text: $amount, placeholder: "数量", width: 100, enabled: enabled && !selection.isEmpty, alignment: .leading)
                Button(action: onLock) {
                    Label(locked ? "已锁定" : "锁定", systemImage: locked ? "lock.fill" : "lock.open")
                        .foregroundStyle(locked ? theme.accent : .secondary)
                }
                .disabled(!enabled || selection.isEmpty)
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

                Button(actionTitle) {
                    guard hasSelection else { return }
                    onAction(selectedID)
                }
                .disabled(!enabled || !hasSelection)
            }
        }
    }
}
