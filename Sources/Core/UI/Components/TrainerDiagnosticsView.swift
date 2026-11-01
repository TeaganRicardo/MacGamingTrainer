import SwiftUI

enum TrainerDiagnosticStatus: String {
    case passed, warning, failed, unknown

    var icon: String {
        switch self {
        case .passed: "checkmark.circle.fill"
        case .warning: "exclamationmark.circle.fill"
        case .failed: "xmark.circle.fill"
        case .unknown: "questionmark.circle.fill"
        }
    }
}

struct TrainerDiagnosticEntry: Identifiable {
    let id: String
    let name: String
    let detail: String
    let status: TrainerDiagnosticStatus
}

struct TrainerDiagnosticsLabels {
    let title: String
    let explanation: String
    let refresh: String
    let export: String
}

struct TrainerDiagnosticsActions {
    let refresh: () -> Void
    let export: () -> Void
    let dismiss: () -> Void
}

/// Generic diagnostic presentation. Check collection, safety, names and export
/// contents belong to the caller; the summary counts the results actually shown.
struct TrainerDiagnosticsView: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Environment(\.trainerTheme) private var theme

    let labels: TrainerDiagnosticsLabels
    let checks: [TrainerDiagnosticEntry]
    let busy: Bool
    let canRefresh: Bool
    let canExport: Bool
    var error = ""
    let actions: TrainerDiagnosticsActions

    private var passed: Int { checks.filter { $0.status == .passed }.count }

    var body: some View {
        TrainerSheetScaffold(title: labels.title, icon: TrainerSemanticIcon.Tool.diagnostics, width: 700) {
            Text("\(passed)/\(checks.count)").font(.headline).monospacedDigit()
                .accessibilityLabel(localization.localized("host.diagnostics.summary",
                    arguments: [String(passed), String(checks.count)]))
            if busy {
                ProgressView().controlSize(.small)
                    .accessibilityLabel(localization.localized("host.operation.inProgress"))
            }
            Button(action: actions.export) {
                Label(labels.export, systemImage: TrainerSemanticIcon.Tool.exportDiagnostics)
            }.disabled(busy || !canExport)
            Button(action: actions.refresh) {
                Label(labels.refresh, systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(busy || !canRefresh)
        } content: {
            Text(labels.explanation).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(spacing: 8) {
                    if checks.isEmpty && !busy {
                        TrainerEmptyState(text: localization.localized("host.diagnostics.empty"))
                    }
                    ForEach(checks) { check in
                        TrainerListCard {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: check.status.icon)
                                    .foregroundStyle(check.status == .passed ? theme.success : theme.warning)
                                    .accessibilityLabel(localization.localized("host.diagnostics." + check.status.rawValue))
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
            }.frame(minHeight: 260, maxHeight: 430)
            if !error.isEmpty {
                Text(error).foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done"), action: actions.dismiss).keyboardShortcut(.cancelAction)
            }
        }
    }
}
