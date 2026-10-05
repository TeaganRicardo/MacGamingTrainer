import SwiftUI

struct Hades2OperationFeedback: View {
    @ObservedObject var model: Hades2TrainerModel

    var body: some View {
        TrainerFeedbackOverlay(notice: model.feedbackNotice, onDismiss: model.dismissFeedback)
    }
}
