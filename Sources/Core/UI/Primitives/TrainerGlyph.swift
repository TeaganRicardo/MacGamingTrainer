import SwiftUI

/// Small type-erased glyph used by shared rows. Modules may supply a custom
/// vector shape without teaching Core about game-specific icon identities.
struct TrainerGlyph: View {
    let identifier: String
    private let content: AnyView

    init<Content: View>(identifier: String, @ViewBuilder content: () -> Content) {
        self.identifier = identifier
        self.content = AnyView(content())
    }

    static func system(_ name: String) -> TrainerGlyph {
        TrainerGlyph(identifier: "system.\(name)") {
            Image(systemName: name)
        }
    }

    var body: some View { content }
}
