import SwiftUI

struct TrainerSaveRetentionSettings: View {
    @ObservedObject var model: TrainerSaveManagerModel
    let onClose: () -> Void
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @State private var count = ""
    @State private var mebibytes = ""
    @State private var editing: Set<String> = []
    // Inventory refresh must not resign a focused native editor and its draft.
    @State private var saving = false

    private var values: (Int, Int)? {
        guard let count = Int(count), (1...10000).contains(count),
              let mib = Int(mebibytes), (1...8_589_934_591).contains(mib) else { return nil }
        return (count, mib * 1024 * 1024)
    }

    var body: some View {
        TrainerSheetScaffold(title: localization.localized("host.save.retention.title"), icon: "clock.badge.checkmark", width: 500) {
            EmptyView()
        } content: {
            VStack(alignment: .leading, spacing: 16) {
                Text(localization.localized("host.save.retention.rule"))
                    .font(.callout)
                HStack {
                    Text(localization.localized("host.save.retention.count"))
                    Spacer()
                    TrainerNumberField(text: $count, placeholder: "host.save.retention.count", width: 110,
                        enabled: !saving, onEditingChanged: { setEditing("count", $0) })
                }
                HStack {
                    Text(localization.localized("host.save.retention.bytes"))
                    Spacer()
                    TrainerNumberField(text: $mebibytes, placeholder: "host.save.retention.bytes", width: 110,
                        enabled: !saving, onEditingChanged: { setEditing("bytes", $0) })
                }
                Text(localization.localized("host.save.retention.floor"))
                    .font(.caption).foregroundStyle(.secondary)
                if values == nil {
                    Text(localization.localized("host.save.retention.invalid"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                if !model.error.isEmpty {
                    Text(localization.presentation(model.error, arguments: model.errorArguments))
                        .font(.caption)
                }
            }
        } footer: {
            HStack {
                Button(localization.localized("host.cancel"), action: onClose).disabled(model.busy)
                Spacer()
                TrainerPrimaryActionButton(title: localization.localized("host.save.retention.save"), enabled: !model.busy && values != nil) {
                    guard let values else { return }
                    saving = true
                    model.configureRetention(maxCount: values.0, maxBytes: values.1) { success in
                        saving = false
                        if success { onClose() }
                    }
                }
            }
        }
        .onAppear(perform: refreshDrafts)
        .onChange(of: model.retention) { _, _ in refreshDrafts() }
        .interactiveDismissDisabled(model.busy)
    }

    private func setEditing(_ field: String, _ active: Bool) {
        if active { editing.insert(field) } else { editing.remove(field) }
    }

    private func refreshDrafts() {
        guard let policy = model.retention else { return }
        if !editing.contains("count") { count = String(policy.maxCount) }
        if !editing.contains("bytes") { mebibytes = String(max(1, (policy.maxBytes + 1024 * 1024 - 1) / (1024 * 1024))) }
    }
}
