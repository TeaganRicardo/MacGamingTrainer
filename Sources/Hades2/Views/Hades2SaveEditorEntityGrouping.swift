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
        // The game-owned index supplies stable identity and localized title.
        // No display string, group label, or positional field name may
        // determine an entity's identity across language changes.
        if let id = entry.entityID, !id.isEmpty,
           let name = entry.entityName, !name.isEmpty {
            return (id, name)
        }
        return ("entry:" + entry.id, entry.displayName)
    }
}
