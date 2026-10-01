import Foundation

/// A `UserDefaults` surface backed by memory only, for harnesses that exercise
/// persistence logic without touching the real user tree.
///
/// Writing anything to a real `UserDefaults(suiteName:)` materializes
/// `~/Library/Preferences/<suite>.plist`. `removePersistentDomain(forName:)`
/// empties that domain but never unlinks the file, and cfprefsd re-materializes
/// the plist after a direct file removal, so no cleanup can undo it: every run
/// of such a harness leaves another preference domain behind in the user's
/// preferences directory.
///
/// The stores under test depend only on the UserDefaults surface, so injecting
/// this type keeps them real while keeping the filesystem clean.
final class InMemoryDefaults: UserDefaults {
    private var storage: [String: Any] = [:]

    override func object(forKey defaultName: String) -> Any? { storage[defaultName] }
    override func string(forKey defaultName: String) -> String? { storage[defaultName] as? String }
    override func integer(forKey defaultName: String) -> Int { storage[defaultName] as? Int ?? 0 }
    override func set(_ value: Any?, forKey defaultName: String) { storage[defaultName] = value }
    override func removeObject(forKey defaultName: String) { storage.removeValue(forKey: defaultName) }
}
