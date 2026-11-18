import SwiftUI

/// Small type-erased glyph used by shared rows. Modules may supply a custom
/// vector shape without teaching Core about game-specific icon identities.
package struct TrainerGlyph: View {
    private let content: AnyView

    package init<Content: View>(@ViewBuilder content: () -> Content) {
        self.content = AnyView(content())
    }

    package static func system(_ name: String) -> TrainerGlyph {
        TrainerGlyph {
            Image(systemName: name)
        }
    }

    package var body: some View { content }
}
