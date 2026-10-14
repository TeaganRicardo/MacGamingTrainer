import SwiftUI

struct Hades2OperationFeedback: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        TrainerFeedbackOverlay(
            notice: model.feedbackNotice,
            onDismiss: model.dismissFeedback,
            onDetails: model.feedbackNotice?.tone == .warning && !model.currentIssues.isEmpty
                ? { model.showFeedbackDetails(for: $0) } : nil,
            detailsNoticeID: model.feedbackDetailsNoticeID
        )
    }
}
