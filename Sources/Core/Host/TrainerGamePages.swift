import AppKit
import SwiftUI

struct TrainerGamePages: View {
    @ObservedObject var application: TrainerApplicationCoordinator
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        HStack(spacing: 0) {
            TrainerSidebar {
                ForEach(application.contexts) { context in
                    context.makeSidebarCard(selected: context.id == application.selectedGameID) {
                        application.selectedGameID = context.id
                    }
                }
            }
            Rectangle()
                .fill(theme.boundaryColor(for: contrast))
                .frame(width: 1)
                .accessibilityHidden(true)
            ZStack(alignment: .topLeading) {
                ForEach(application.contexts) { context in
                    context.content
                        .opacity(context.id == application.selectedGameID ? 1 : 0)
                        .allowsHitTesting(context.id == application.selectedGameID)
                        .accessibilityHidden(context.id != application.selectedGameID)
                        .zIndex(context.id == application.selectedGameID ? 1 : 0)
                }
            }
        }
        .trainerSurface(.canvas)
        .background(TrainerGameSelectionFocus(gameID: application.selectedGameID)
            .allowsHitTesting(false).accessibilityHidden(true))
        .trainerDismissTextEditingOnClickAway()
        .disabled(application.terminationRequested)
    }
}

/// End the old page's native edit in this window only. Keep keyboard focus on
/// the sidebar selection, and never resign an independent tool window's editor.
private struct TrainerGameSelectionFocus: NSViewRepresentable {
    let gameID: String
    final class Observer: NSView { var gameID: String? }
    func makeNSView(context: Context) -> Observer { Observer() }
    func updateNSView(_ view: Observer, context: Context) {
        let previous = view.gameID
        view.gameID = gameID
        guard let previous, previous != gameID, let window = view.window,
              let editor = window.firstResponder as? NSTextView, editor.isFieldEditor,
              let field = editor.delegate as? NSTextField else { return }
        DispatchQueue.main.async { [weak window, weak editor, weak field] in
            guard let window, let editor, let field, window.firstResponder === editor,
                  editor.delegate as? NSTextField === field else { return }
            window.makeFirstResponder(nil)
        }
    }
}
