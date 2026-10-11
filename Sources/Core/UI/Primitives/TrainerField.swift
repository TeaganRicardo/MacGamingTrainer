import SwiftUI

struct TrainerNumberField: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Binding var text: String
    let placeholder: String
    let width: CGFloat
    let enabled: Bool
    let alignment: TextAlignment
    let onCommit: (String) -> String
    let onEditingChanged: (Bool) -> Void

    init(text: Binding<String>, placeholder: String = "host.value", width: CGFloat = 90, enabled: Bool = true, alignment: TextAlignment = .center, onEditingChanged: @escaping (Bool) -> Void = { _ in }, onCommit: @escaping (String) -> String = { $0 }) {
        self._text = text
        self.placeholder = placeholder
        self.width = width
        self.enabled = enabled
        self.alignment = alignment
        self.onCommit = onCommit
        self.onEditingChanged = onEditingChanged
    }

    var body: some View {
        TrainerTextField(title: localization.presentation(placeholder), text: $text,
            onEditingChanged: onEditingChanged, onCommit: onCommit,
            alignment: alignment == .leading ? .left : (alignment == .trailing ? .right : .center))
            .frame(width: width)
            .disabled(!enabled)
    }
}
