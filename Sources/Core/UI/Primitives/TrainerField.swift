import SwiftUI

struct TrainerNumberField: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore
    @Binding var text: String
    let placeholder: String
    let width: CGFloat
    let enabled: Bool
    let alignment: TextAlignment

    init(text: Binding<String>, placeholder: String = "host.value", width: CGFloat = 90, enabled: Bool = true, alignment: TextAlignment = .center) {
        self._text = text
        self.placeholder = placeholder
        self.width = width
        self.enabled = enabled
        self.alignment = alignment
    }

    var body: some View {
        TextField(localization.presentation(placeholder), text: $text)
            .textFieldStyle(.roundedBorder)
            .multilineTextAlignment(alignment)
            .frame(width: width)
            .disabled(!enabled)
    }
}
