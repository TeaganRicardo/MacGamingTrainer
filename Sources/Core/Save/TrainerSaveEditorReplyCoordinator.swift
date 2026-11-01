import Foundation

/// Main-thread request ownership for one structured Save Editor tool window.
///
/// This models only document/reply identity. Games still own their search terms,
/// draft text, page navigation, native edit semantics and backend transport.
/// Retiring a window or replacing a document invalidates every outstanding
/// reply even if the backend reuses a workspace ID or a baseline string.
final class TrainerSaveEditorReplyCoordinator {
    enum Lane: Hashable {
        case inventory
        case open
        case query
        case detail
        case advancedDetail
        case review
    }

    struct Ticket {
        fileprivate let epoch: UUID
        fileprivate let lane: Lane?
        fileprivate let revision: UInt64
        fileprivate let bindsDocument: Bool
        fileprivate let workspaceID: String?
        fileprivate let baselineGeneration: String?
    }

    private var epoch = UUID()
    private var revisions: [Lane: UInt64] = [:]
    private(set) var workspaceID: String?
    private(set) var baselineGeneration: String?

    /// A new explicit source read supersedes old queries and older source
    /// reads before either response arrives; the loaded document remains
    /// available until the new read is confirmed.
    func beginNewDocumentRead() -> Ticket {
        invalidateAllReplies()
        return capture(.open, bindsDocument: false)
    }

    /// Capture a request that either belongs to the current document or is
    /// independent of it (inventory and open). One lane accepts only its most
    /// recently issued request, regardless of callback arrival order.
    func capture(_ lane: Lane? = nil, bindsDocument: Bool = true) -> Ticket {
        if let lane { revisions[lane, default: 0] &+= 1 }
        return Ticket(
            epoch: epoch,
            lane: lane,
            revision: lane.map { revisions[$0]! } ?? 0,
            bindsDocument: bindsDocument,
            workspaceID: bindsDocument ? workspaceID : nil,
            baselineGeneration: bindsDocument ? baselineGeneration : nil
        )
    }

    func accepts(_ ticket: Ticket) -> Bool {
        guard ticket.epoch == epoch else { return false }
        if ticket.bindsDocument {
            guard let workspaceID, let baselineGeneration,
                  ticket.workspaceID == workspaceID,
                  ticket.baselineGeneration == baselineGeneration else { return false }
        }
        if let lane = ticket.lane {
            return revisions[lane] == ticket.revision
        }
        return true
    }

    /// Cancel a pending query/detail without touching staged edits or the
    /// current document. Debounce timers remain game-owned.
    func invalidate(_ lane: Lane) {
        revisions[lane, default: 0] &+= 1
    }

    func owns(workspaceID: String?, baselineGeneration: String?) -> Bool {
        guard let workspaceID, let baselineGeneration else { return false }
        return self.workspaceID == workspaceID && self.baselineGeneration == baselineGeneration
    }

    /// Called only after validating a successful open, target change or
    /// post-Apply baseline. A target change invalidates pending replies even
    /// when the backend workspace and generation strings stay unchanged.
    func bind(workspaceID: String, baselineGeneration: String) {
        invalidateAllReplies()
        self.workspaceID = workspaceID
        self.baselineGeneration = baselineGeneration
    }

    /// Tool close/reopen must not resurrect a reply from the retired window.
    func retire() {
        invalidateAllReplies()
        workspaceID = nil
        baselineGeneration = nil
    }

    private func invalidateAllReplies() {
        epoch = UUID()
        revisions.removeAll()
    }
}
