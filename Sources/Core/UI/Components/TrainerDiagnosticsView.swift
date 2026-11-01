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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var lifetime = TrainerSheetLifetime()

    let labels: TrainerDiagnosticsLabels
    let checks: [TrainerDiagnosticEntry]
    let busy: Bool
    let canRefresh: Bool
    let canExport: Bool
    var error = ""
    let actions: TrainerDiagnosticsActions

    private var passed: Int { checks.filter { $0.status == .passed }.count }

    var body: some View {
        let presentationID = lifetime.id
        TrainerSheetScaffold(title: labels.title, icon: TrainerSemanticIcon.Tool.diagnostics, width: 700, minimumWidth: 360) {
            Text("\(passed)/\(checks.count)").font(.headline).monospacedDigit()
                .accessibilityLabel(localization.localized("host.diagnostics.summary",
                    arguments: [String(passed), String(checks.count)]))
                .contentTransition(.opacity)
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: "\(passed)/\(checks.count)")
            ProgressView().controlSize(.small).frame(width: 16, height: 16)
                .opacity(busy ? 1 : 0).accessibilityHidden(!busy)
                .accessibilityLabel(localization.localized("host.operation.inProgress"))
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: busy)
            Button {
                guard lifetime.accepts(presentationID), !busy, canExport else { return }
                actions.export()
            } label: {
                Label(labels.export, systemImage: TrainerSemanticIcon.Tool.exportDiagnostics)
            }.disabled(!lifetime.isActive || busy || !canExport)
            Button {
                guard lifetime.accepts(presentationID), !busy, canRefresh else { return }
                actions.refresh()
            } label: {
                Label(labels.refresh, systemImage: TrainerSemanticIcon.Concept.refresh)
            }.disabled(!lifetime.isActive || busy || !canRefresh)
        } content: {
            Text(labels.explanation).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            ScrollView {
                LazyVStack(spacing: 8) {
                    if checks.isEmpty && !busy {
                        TrainerEmptyState(text: localization.localized("host.diagnostics.empty"))
                            .transition(.opacity)
                    }
                    ForEach(checks) { check in
                        TrainerListCard {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: check.status.icon)
                                    .foregroundStyle(check.status == .passed ? theme.success : theme.warning)
                                    .accessibilityLabel(localization.localized("host.diagnostics." + check.status.rawValue))
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(check.name).font(.subheadline.weight(.semibold))
                                        .contentTransition(.opacity)
                                        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: check.name)
                                    if !check.detail.isEmpty {
                                        Text(check.detail).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                                            .contentTransition(.opacity)
                                            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: check.detail)
                                    }
                                }
                                Spacer()
                            }
                        }
                    }
                }
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: checks.isEmpty && !busy)
            }.frame(minHeight: 260, maxHeight: 430)
            Text(error).foregroundStyle(theme.warning).fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
                .frame(minHeight: 18, alignment: .leading)
                .accessibilityHidden(error.isEmpty)
                .contentTransition(.opacity)
                .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: error)
        } footer: {
            HStack {
                Spacer()
                Button(localization.localized("host.done")) {
                    guard lifetime.accepts(presentationID) else { return }
                    lifetime.invalidate()
                    actions.dismiss()
                }.keyboardShortcut(.cancelAction)
            }
        }
        .onAppear { lifetime.appear() }
        .onDisappear { lifetime.invalidate() }
    }
}
