import SwiftUI

/// A bounded projection of a module's current owner state, never a
/// notification history. The module decides what is current; Core presents it.
struct TrainerCurrentIssue: Identifiable, Equatable {
    let id: String
    let text: TrainerTextToken
    let title: TrainerTextToken?

    init(id: String, text: TrainerTextToken, title: TrainerTextToken? = nil) {
        self.id = id
        self.text = text
        self.title = title
    }
}

/// The operation toast of a module page. A warning offers its details while
/// the module still reports current issues; a routine notice only dismisses.
struct TrainerOperationFeedback: View {
    let notice: TrainerFeedbackNotice?
    let hasCurrentIssues: Bool
    let detailsNoticeID: UUID?
    let onDismiss: (UUID) -> Void
    let onShowDetails: (UUID) -> Void

    var body: some View {
        TrainerFeedbackOverlay(
            notice: notice,
            onDismiss: onDismiss,
            onDetails: notice?.tone == .warning && hasCurrentIssues ? onShowDetails : nil,
            detailsNoticeID: detailsNoticeID
        )
    }
}

/// The sidebar entry for a module's current issues. It exists only while the
/// module reports an issue; the module owns whether its details are presented,
/// and resolution or a hidden page retires that presentation.
struct TrainerCurrentIssuesEntry: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let issues: [TrainerCurrentIssue]
    let detailsPresented: Bool
    let onShowDetails: () -> Void
    let onCloseDetails: () -> Void
    let onOpenLog: () -> Void

    var body: some View {
        // A transparent group takes no stack spacing while empty and still
        // observes the issues resolving.
        Group {
            if !issues.isEmpty {
                Button(action: onShowDetails) {
                    Label(localization.localized("host.feedback.currentIssues"), systemImage: "exclamationmark.circle")
                        .font(.callout)
                }
                .popover(isPresented: Binding(
                    get: { detailsPresented },
                    set: { if !$0 { onCloseDetails() } }
                )) {
                    TrainerFeedbackDetails(issues: issues, onOpenLog: onOpenLog, onClose: onCloseDetails)
                }
                .background {
                    TrainerGamePageVisibilityObserver { visible in
                        if !visible { onCloseDetails() }
                    }
                }
            }
        }
        .onChange(of: issues) { _, issues in
            if issues.isEmpty { onCloseDetails() }
        }
    }
}

struct TrainerFeedbackDetails: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let issues: [TrainerCurrentIssue]
    let onOpenLog: () -> Void
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(localization.localized("host.feedback.currentIssues")).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(issues) { issue in
                        VStack(alignment: .leading, spacing: 4) {
                            if let title = issue.title { Text(localization.string(title)).font(.subheadline.weight(.medium)) }
                            Text(localization.string(issue.text))
                                .fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .frame(maxHeight: 320)
            HStack {
                Button(localization.localized("host.viewLog"), action: onOpenLog)
                Spacer()
                Button(localization.localized("host.feedback.closeDetails"), action: onClose)
            }
        }
        .padding(20)
        .frame(width: 360)
        .trainerSurface(.canvas)
    }
}
