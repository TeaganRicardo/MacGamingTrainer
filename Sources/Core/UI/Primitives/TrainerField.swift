import SwiftUI

struct TrainerNumberField: View {
    @Binding var text: String
    let placeholder: String
    let width: CGFloat
    let enabled: Bool
    let alignment: TextAlignment

    init(text: Binding<String>, placeholder: String = "数值", width: CGFloat = 90, enabled: Bool = true, alignment: TextAlignment = .center) {
        self._text = text
        self.placeholder = placeholder
        self.width = width
        self.enabled = enabled
        self.alignment = alignment
    }

    var body: some View {
        TextField(placeholder, text: $text)
            .textFieldStyle(.roundedBorder)
            .multilineTextAlignment(alignment)
            .frame(width: width)
            .disabled(!enabled)
    }
}
