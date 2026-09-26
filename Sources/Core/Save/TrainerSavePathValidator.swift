import Foundation

enum TrainerSavePathValidator {
    /// Mirrors Backend/core/protocol.py's default Core data root.
    static var trainerDataRoot: URL {
        let home = ProcessInfo.processInfo.environment["HOME"]
            .flatMap { $0.hasPrefix("/") ? URL(fileURLWithPath: $0, isDirectory: true) : nil }
            ?? FileManager.default.homeDirectoryForCurrentUser
        return home
            .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
            .standardizedFileURL
    }

    static func validatedDirectoryURL(for value: String, under root: URL = trainerDataRoot) -> URL? {
        validatedLocalURL(for: value, under: root, requireDirectory: true)
    }

    static func validatedLocalURL(for value: String, under root: URL = trainerDataRoot) -> URL? {
        validatedLocalURL(for: value, under: root, requireDirectory: false)
    }

    private static func validatedLocalURL(
        for value: String,
        under root: URL,
        requireDirectory: Bool
    ) -> URL? {
        guard !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }

        let candidate: URL
        if let parsed = URL(string: value), let scheme = parsed.scheme {
            guard scheme.caseInsensitiveCompare("file") == .orderedSame,
                  parsed.isFileURL,
                  parsed.host == nil || parsed.host?.caseInsensitiveCompare("localhost") == .orderedSame,
                  parsed.path.hasPrefix("/") else { return nil }
            candidate = parsed
        } else {
            guard value.hasPrefix("/") else { return nil }
            candidate = URL(fileURLWithPath: value)
        }
        guard candidate.isFileURL else { return nil }

        let fileManager = FileManager.default
        let resolvedRoot = root.standardizedFileURL.resolvingSymlinksInPath().standardizedFileURL
        let resolvedCandidate = candidate.standardizedFileURL.resolvingSymlinksInPath().standardizedFileURL
        let rootComponents = resolvedRoot.pathComponents
        let candidateComponents = resolvedCandidate.pathComponents
        guard candidateComponents.count >= rootComponents.count,
              Array(candidateComponents.prefix(rootComponents.count)) == rootComponents,
              fileManager.fileExists(atPath: resolvedRoot.path),
              fileManager.fileExists(atPath: resolvedCandidate.path),
              let rootValues = try? resolvedRoot.resourceValues(forKeys: [.isDirectoryKey]),
              rootValues.isDirectory == true,
              let candidateValues = try? resolvedCandidate.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey]) else {
            return nil
        }

        if requireDirectory {
            guard candidateValues.isDirectory == true else { return nil }
        } else {
            guard candidateValues.isDirectory == true || candidateValues.isRegularFile == true else { return nil }
        }
        return resolvedCandidate
    }
}
