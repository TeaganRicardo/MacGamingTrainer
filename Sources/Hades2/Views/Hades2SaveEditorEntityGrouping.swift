import Foundation

/// Presentation-only grouping. Mutation authority remains with each save descriptor.
struct Hades2SaveEditorEntity: Identifiable {
    let id: String
    let title: String
    let entries: [Hades2SaveEditorEntry]
}

enum Hades2SaveEditorEntityGrouping {
    static func entities(from entries: [Hades2SaveEditorEntry]) -> [Hades2SaveEditorEntity] {
        var order: [String] = []
        var titles: [String: String] = [:]
        var buckets: [String: [Hades2SaveEditorEntry]] = [:]
        for entry in entries {
            let (key, title) = identity(for: entry)
            if buckets[key] == nil {
                order.append(key)
                titles[key] = title
            }
            buckets[key, default: []].append(entry)
        }
        return order.map { key in
            Hades2SaveEditorEntity(
                id: key,
                title: titles[key] ?? key,
                entries: buckets[key] ?? []
            )
        }
    }

    private static func identity(for entry: Hades2SaveEditorEntry) -> (String, String) {
        let parts = entry.displayName.components(separatedBy: " · ")
        switch entry.domain {
        case "relationships":
            if entry.id.hasPrefix("interaction:") || entry.id.hasPrefix("specialInteraction:") {
                return ("person:" + entry.rawID, parts.last ?? entry.displayName)
            }
            if entry.id.hasPrefix("gift:") {
                let identity = String(entry.id.dropFirst("gift:".count))
                let person = identity.split(separator: ":", maxSplits: 1).first.map(String.init) ?? identity
                return ("person:" + person, parts.first ?? entry.displayName)
            }
        case "investigate":
            if let identity = entry.entityID,
               let name = entry.entityName,
               !identity.isEmpty, !name.isEmpty {
                return (identity, name)
            }
        case "progression":
            if entry.id.hasPrefix("card:") {
                let name = parts.count > 1
                    ? parts.dropLast().joined(separator: " · ") : entry.displayName
                return ("arcana:" + entry.rawID, name)
            }
        case "weapons":
            if entry.id.hasPrefix("weapon:")
                || entry.id.hasPrefix("aspect:")
                || entry.id.hasPrefix("aspectSelection:") {
                let name = parts.first ?? entry.displayName
                return ("weaponName:" + name, name)
            }
        default:
            break
        }
        return ("entry:" + entry.id, entry.displayName)
    }
}
