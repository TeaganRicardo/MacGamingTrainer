import Foundation

/// Safe lookup for per-module packaged resources under `Modules/<moduleID>/`.
///
/// Production builds copy each module's `appResources` under
/// `Contents/Resources/Modules/<moduleID>/`; test harnesses may stage the same
/// layout beside the test binary or set `MGT_MODULE_RESOURCES_ROOT`.
package enum TrainerModuleResources {
    package static let rootEnvironmentKey = "MGT_MODULE_RESOURCES_ROOT"

    package static func url(
        moduleID: String,
        relativePath: String,
        extraRoots: [URL] = [],
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> URL? {
        guard isSafeSegment(moduleID), isSafeRelativePath(relativePath) else { return nil }
        for root in searchRoots(extraRoots: extraRoots, bundle: bundle, environment: environment) {
            let moduleRoot = root.appendingPathComponent("Modules", isDirectory: true)
                .appendingPathComponent(moduleID, isDirectory: true)
                .standardizedFileURL
                .resolvingSymlinksInPath()
            let candidate = moduleRoot.appendingPathComponent(relativePath, isDirectory: false)
                .standardizedFileURL
                .resolvingSymlinksInPath()
            let prefix = moduleRoot.path.hasSuffix("/") ? moduleRoot.path : moduleRoot.path + "/"
            guard candidate.path.hasPrefix(prefix) else { continue }
            if FileManager.default.isReadableFile(atPath: candidate.path) {
                return candidate
            }
        }
        return nil
    }

    package static func data(
        moduleID: String,
        relativePath: String,
        extraRoots: [URL] = [],
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Data? {
        guard let resourceURL = url(
            moduleID: moduleID,
            relativePath: relativePath,
            extraRoots: extraRoots,
            bundle: bundle,
            environment: environment
        ) else {
            return nil
        }
        return try? Data(contentsOf: resourceURL)
    }

    package static func jsonObject(
        moduleID: String,
        relativePath: String,
        extraRoots: [URL] = [],
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> [String: Any]? {
        guard let payload = data(
            moduleID: moduleID,
            relativePath: relativePath,
            extraRoots: extraRoots,
            bundle: bundle,
            environment: environment
        ) else {
            return nil
        }
        return try? JSONSerialization.jsonObject(with: payload) as? [String: Any]
    }

    private static func searchRoots(
        extraRoots: [URL],
        bundle: Bundle,
        environment: [String: String]
    ) -> [URL] {
        var roots: [URL] = []
        roots.append(contentsOf: extraRoots)
        if let rawOverride = environment[rootEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !rawOverride.isEmpty
        {
            roots.append(URL(fileURLWithPath: rawOverride, isDirectory: true))
        }
        if let resourceURL = bundle.resourceURL {
            roots.append(resourceURL)
        }
        roots.append(bundle.bundleURL)
        return roots
    }

    private static func isSafeSegment(_ value: String) -> Bool {
        guard !value.isEmpty,
              value != ".",
              value != "..",
              !value.contains("/"),
              !value.contains("\\")
        else {
            return false
        }
        return true
    }

    private static func isSafeRelativePath(_ value: String) -> Bool {
        guard !value.isEmpty,
              !value.hasPrefix("/"),
              !value.contains("\\")
        else {
            return false
        }
        let components = value.split(separator: "/", omittingEmptySubsequences: false)
        return !components.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." })
    }
}

/// Core JSON localization table loader and `{n}` placeholder formatter for game modules.
package struct TrainerModuleStringTable {
    private let tables: [TrainerPresentationLanguage: [String: String]]
    private let resolveArgumentKeys: Bool
    private let transform: (String, TrainerPresentationLanguage) -> String

    package init(
        tables: [TrainerPresentationLanguage: [String: String]],
        resolveArgumentKeys: Bool = true,
        transform: @escaping (String, TrainerPresentationLanguage) -> String = { text, _ in text }
    ) {
        self.tables = tables
        self.resolveArgumentKeys = resolveArgumentKeys
        self.transform = transform
    }

    package init(
        moduleID: String,
        tablePrefix: String? = nil,
        extraRoots: [URL] = [],
        bundle: Bundle = .main,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        resolveArgumentKeys: Bool = true,
        transform: @escaping (String, TrainerPresentationLanguage) -> String = { text, _ in text }
    ) {
        let stem = tablePrefix ?? moduleID
        var loaded: [TrainerPresentationLanguage: [String: String]] = [:]
        for language in TrainerPresentationLanguage.allCases {
            let filename = "\(stem).\(language.rawValue).json"
            guard let data = TrainerModuleResources.data(
                moduleID: moduleID,
                relativePath: filename,
                extraRoots: extraRoots,
                bundle: bundle,
                environment: environment
            ),
            let entries = Self.decodeTable(data) else {
                continue
            }
            loaded[language] = entries
        }
        self.init(tables: loaded, resolveArgumentKeys: resolveArgumentKeys, transform: transform)
    }

    package func string(
        _ key: String,
        language: TrainerPresentationLanguage,
        arguments: [String] = []
    ) -> String {
        let template = tables[language]?[key] ?? key
        let transformed = transform(template, language)
        let rendered = Self.substitute(transformed, arguments: arguments) { _, argument in
            if resolveArgumentKeys, hasKey(argument) {
                return string(argument, language: language)
            }
            return argument
        }
        return Self.dropUnfilledPlaceholders(rendered)
    }

    package func hasKey(_ key: String) -> Bool {
        TrainerPresentationLanguage.allCases.allSatisfy { tables[$0]?[key] != nil }
    }

    package static func decodeTable(_ data: Data) -> [String: String]? {
        guard let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return payload["entries"] as? [String: String]
    }

    package static func substitute(
        _ template: String,
        arguments: [String],
        map: (Int, String) -> String = { _, value in value }
    ) -> String {
        var result = template
        for index in arguments.indices.reversed() {
            result = result.replacingOccurrences(of: "{\(index)}", with: map(index, arguments[index]))
        }
        return result
    }

    package static func dropUnfilledPlaceholders(_ text: String) -> String {
        var result = text
        for index in stride(from: 32, through: 0, by: -1) {
            result = result.replacingOccurrences(of: "{\(index)}", with: "")
        }
        return result
    }
}
