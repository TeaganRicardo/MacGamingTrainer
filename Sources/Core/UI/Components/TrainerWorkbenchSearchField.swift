import SwiftUI

/// Shared discovery presentation. Entries, names, icons and reveal/navigation
/// semantics stay with the module; this view does not receive a backend session.
struct TrainerWorkbenchSearchField<Entry: Identifiable>: View {
    @Environment(\.trainerGamePageVisible) private var pageVisible
    @Binding var text: String
    let placeholder: String
    let clearLabel: String
    let emptyLabel: String
    let search: (String) -> [Entry]
    let title: (Entry) -> String
    let detail: (Entry) -> String
    let icon: (Entry) -> String
    let onNavigate: (Entry) -> Void
    @State private var presentation = TrainerWorkbenchSearchPresentation()
    @FocusState private var searchFocused: Bool

    private var results: [Entry] { search(text) }

    private func locate(_ entry: Entry) {
        if presentation.select(entry, pageVisible: pageVisible, navigate: onNavigate) {
            searchFocused = false
        }
    }

    private func submitSearch() {
        if presentation.submit(query: text, pageVisible: pageVisible, search: search, navigate: onNavigate) {
            searchFocused = false
        }
    }

    var body: some View {
        TrainerSearchField(
            text: $text, placeholder: placeholder, clearLabel: clearLabel,
            focus: $searchFocused, onSubmit: submitSearch
        )
        .popover(isPresented: $presentation.resultsPresented, arrowEdge: .bottom) {
            Group {
                if results.isEmpty {
                    TrainerEmptyState(text: emptyLabel)
                } else {
                    ScrollView {
                        VStack(spacing: 0) {
                            ForEach(results) { entry in
                                TrainerSectionButton(
                                    title: title(entry), detail: detail(entry), systemImage: icon(entry)
                                ) { locate(entry) }
                                .accessibilityIdentifier("trainer.workbench.result.\(entry.id)")
                            }
                        }
                    }
                    .frame(height: min(CGFloat(results.count) * 52, 312))
                }
            }
            .frame(width: 420)
            .padding(8)
        }
        .onChange(of: text) { _, query in
            presentation.queryChanged(query, pageVisible: pageVisible)
        }
        .onChange(of: pageVisible) { _, visible in
            presentation.pageVisibilityChanged(visible)
            if !visible { searchFocused = false }
        }
        .onExitCommand { presentation.dismiss() }
        .onDisappear {
            presentation.dismiss()
            searchFocused = false
        }
    }
}
