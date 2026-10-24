import Foundation

/// Presentation-only grouping. Mutation authority remains with each save descriptor.
struct Hades2SaveEditorEntity: Identifiable {
    let id: String
    let title: String
    let entries: [Hades2SaveEditorEntry]
}

struct Hades2SaveEditorFieldGroup: Identifiable {
    let id: String
    let title: String?
    let entries: [Hades2SaveEditorEntry]
}

struct Hades2SaveEditorResultSection: Identifiable {
    let id: String
    let entities: [Hades2SaveEditorEntity]

    var titleKey: String { "hades2.saveEditor.group." + id }
    var icon: String {
        switch id {
        case "characters": return "person.2.fill"
        case "quests": return "list.bullet.clipboard"
        case "resources": return "shippingbox.fill"
        case "arcana": return "rectangle.stack.fill"
        case "weapons": return "bolt.shield.fill"
        case "tools": return "hammer.fill"
        case "familiars": return "pawprint.fill"
        case "runs": return "clock.arrow.circlepath"
        case "statistics": return "chart.bar.fill"
        case "objectives": return "checkmark.circle"
        case "world": return "building.2.fill"
        case "advanced": return "square.stack.3d.up"
        default: return "text.book.closed.fill"
        }
    }
}

enum Hades2SaveEditorEntityGrouping {
    static func fields(in entity: Hades2SaveEditorEntity) -> [Hades2SaveEditorFieldGroup] {
        var order: [String] = []
        var groups: [String: [Hades2SaveEditorEntry]] = [:]
        for entry in entity.entries {
            // The domain is a stable owner; translated headings never own drafts.
            let owner = entry.id.hasPrefix("gift:") ? "gifts" : entry.domain + (entry.hostID.map { ":" + $0 } ?? "")
            if groups[owner] == nil { order.append(owner) }
            groups[owner, default: []].append(entry)
        }
        return order.map { owner in
            let entries = groups[owner]!
            return Hades2SaveEditorFieldGroup(
                id: owner, title: entries.first?.hostName ?? (order.count > 1 ? entries.first?.group : nil), entries: entries
            )
        }
    }

    static func sections(from entities: [Hades2SaveEditorEntity]) -> [Hades2SaveEditorResultSection] {
        let order = ["characters", "quests", "story", "resources", "arcana", "weapons",
                     "tools", "familiars", "world", "runs", "statistics", "objectives", "advanced"]
        let grouped = Dictionary(grouping: entities, by: sectionID)
        return order.compactMap { id in
            grouped[id].map { Hades2SaveEditorResultSection(id: id, entities: $0) }
        }
    }

    private static func sectionID(_ entity: Hades2SaveEditorEntity) -> String {
        let id = entity.id
        if id.hasPrefix("person:") { return "characters" }
        if id.hasPrefix("quest:") { return "quests" }
        if id.hasPrefix("familiar:") { return "familiars" }
        if id.hasPrefix("arcana:") { return "arcana" }
        if id.hasPrefix("weapon:") || id.hasPrefix("aspect:") { return "weapons" }
        if id.hasPrefix("tool:") { return "tools" }
        if id.hasPrefix("object:") { return "world" }
        if id.hasPrefix("history:run:") { return "runs" }
        guard let entry = entity.entries.first else { return "advanced" }
        if entry.id.hasPrefix("objective:") { return "objectives" }
        switch entry.domain {
        case "resources": return "resources"
        case "playerStats", "history": return "statistics"
        case "advanced": return "advanced"
        case "weapons": return "weapons"
        default: return "story"
        }
    }

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
