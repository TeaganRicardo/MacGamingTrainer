import Combine

/// One retained workbench owns its section selection and pending scroll request.
/// A newer request replaces the previous one. Hiding a page retires pending
/// work and finishes an active jump before its viewport becomes hidden.
@MainActor
final class TrainerSectionNavigation: ObservableObject {
    struct Request: Equatable {
        let destination: String
        let generation: UInt
    }

    @Published private(set) var selection: String?
    @Published private(set) var request: Request?
    private(set) var isVisible = true
    private var generation: UInt = 0
    private var activeScroll: (request: Request, finish: () -> Void)?

    func navigate(to destination: String) {
        guard isVisible else { return }
        generation &+= 1
        request = Request(destination: destination, generation: generation)
    }

    func consume(_ candidate: Request, finishScroll: (() -> Void)? = nil) -> Bool {
        guard isVisible, candidate == request else { return false }
        selection = candidate.destination
        request = nil
        activeScroll = finishScroll.map { (candidate, $0) }
        return true
    }

    func didFinishScroll(_ candidate: Request) {
        guard activeScroll?.request == candidate else { return }
        activeScroll = nil
    }

    func cancelRequest(_ candidate: Request) {
        guard candidate == request else { return }
        request = nil
    }

    func setVisible(_ visible: Bool) {
        if !visible {
            request = nil
            let finish = activeScroll?.finish
            activeScroll = nil
            // The context calls this before changing page presentation. Resolve
            // the current jump to its selected destination without animation,
            // rather than retaining a location between two sections.
            finish?()
        }
        isVisible = visible
    }
}
