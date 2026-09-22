import Foundation

/// Owns delayed Hades mutations. Each scheduled key has a token, while global
/// barriers advance the generation. Together they prevent both replaced work
/// and pre-barrier work from executing after a state-resetting operation.
final class Hades2MutationScheduler {
    private struct Entry {
        let token: UUID
        let sequence: UInt64
        let workItem: DispatchWorkItem
        let action: () -> Void
    }

    private let queue: DispatchQueue
    private var generation: UInt64 = 0
    private var nextSequence: UInt64 = 0
    private var entries: [String: Entry] = [:]

    init(queue: DispatchQueue = .main) {
        self.queue = queue
    }

    var pendingCount: Int { entries.count }

    func schedule(key: String, delay: TimeInterval, action: @escaping () -> Void) {
        entries[key]?.workItem.cancel()

        let token = UUID()
        let scheduledGeneration = generation
        let sequence = nextSequence
        nextSequence &+= 1
        var work: DispatchWorkItem!
        work = DispatchWorkItem { [weak self] in
            guard let self,
                  self.generation == scheduledGeneration,
                  self.entries[key]?.token == token,
                  work.isCancelled == false else { return }
            self.entries[key] = nil
            action()
        }
        entries[key] = Entry(token: token, sequence: sequence, workItem: work, action: action)
        queue.asyncAfter(deadline: .now() + max(0, delay), execute: work)
    }

    func cancel(key: String) {
        guard let entry = entries.removeValue(forKey: key) else { return }
        entry.workItem.cancel()
    }

    /// Executes the latest pending mutation for each key immediately, preserving
    /// their submission order. Used before operations such as saving a profile,
    /// where silently discarding the user's most recent edits would be wrong.
    func flushAll() {
        generation &+= 1
        let pending = entries.values.sorted { $0.sequence < $1.sequence }
        entries.removeAll()
        pending.forEach { $0.workItem.cancel() }
        pending.forEach { $0.action() }
    }

    /// Discards all delayed mutations. Used by state barriers such as disable
    /// all, profile load, save restore, disconnect and backend termination.
    func invalidateAll() {
        generation &+= 1
        let pending = entries.values
        entries.removeAll()
        pending.forEach { $0.workItem.cancel() }
    }
}
