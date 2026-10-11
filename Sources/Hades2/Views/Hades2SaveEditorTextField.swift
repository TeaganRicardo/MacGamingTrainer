import SwiftUI

struct Hades2SaveEditorTextField: View {
    @ObservedObject var model: Hades2SaveEditorModel
    let entry: Hades2SaveEditorEntry
    @Binding var text: String
    let title: String

    var body: some View {
        TrainerTextField(title: title, text: $text, onCommit: { draft in
            model.completeTextEdit(entry, text: draft)
        })
        .id(entry.id)
        .disabled(model.busy)
    }
}
