import SwiftUI

/// Small type-erased glyph used by shared rows. Modules may supply a custom
/// vector shape without teaching Core about game-specific icon identities.
struct TrainerGlyph: View {
    private let content: AnyView

    init<Content: View>(@ViewBuilder content: () -> Content) {
        self.content = AnyView(content())
    }

    static func system(_ name: String) -> TrainerGlyph {
        TrainerGlyph {
            Image(systemName: name)
        }
    }

    var body: some View { content }
}
