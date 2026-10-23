import CoreFoundation
import Foundation

/// An unfinished member request belongs to its table in the open document,
/// including its correction when the structure sheet is temporarily closed.
struct Hades2SaveAdvancedMembershipDraft {
    var keyType = "string"
    var key = ""
    var value = "{\"luaType\":\"string\",\"value\":\"\"}"
    var failure: TrainerTextToken?
}

/// The Save codec's tagged Lua value. JSON objects are transport structure;
/// explicit tags preserve Lua booleans/numbers/strings, table keys and nil.
struct Hades2SaveTypedValue: Hashable {
    let object: [String: Any]
    let json: String
    var kind: String { object["luaType"] as! String }

    init?(_ value: Any) {
        guard let object = value as? [String: Any], Self.valid(object),
              let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .fragmentsAllowed]),
              let json = String(data: data, encoding: .utf8) else { return nil }
        self.object = object
        self.json = json
    }

    init?(text: String) {
        guard let object = try? JSONSerialization.jsonObject(with: Data(text.utf8)) else { return nil }
        self.init(object)
    }

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.json == rhs.json }
    func hash(into hasher: inout Hasher) { hasher.combine(json) }

    private static func valid(_ node: [String: Any]) -> Bool {
        switch node["luaType"] as? String {
        case "nil": return node["value"] == nil || node["value"] is NSNull
        case "boolean":
            guard let number = node["value"] as? NSNumber else { return false }
            return CFGetTypeID(number) == CFBooleanGetTypeID()
        case "number":
            if let encoding = node["encoding"] as? String {
                return encoding == "nonfinite" && ["nan", "inf", "-inf"].contains(node["value"] as? String ?? "")
            }
            guard let number = node["value"] as? NSNumber,
                  CFGetTypeID(number) != CFBooleanGetTypeID() else { return false }
            return number.doubleValue.isFinite
        case "string":
            guard let text = node["value"] as? String else { return false }
            if let encoding = node["encoding"] as? String {
                return encoding == "base64" && Data(base64Encoded: text) != nil
            }
            return true
        case "table":
            guard let entries = node["entries"] as? [[String: Any]] else { return false }
            return entries.allSatisfy { entry in
                guard let key = entry["key"] as? [String: Any],
                      let kind = key["luaType"] as? String,
                      ["boolean", "number", "string"].contains(kind),
                      let value = entry["value"] as? [String: Any] else { return false }
                return valid(key) && valid(value)
            }
        default: return false
        }
    }
}

struct Hades2SaveAdvancedDetail {
    let entryID: String
    let value: Hades2SaveTypedValue
    let warning: String?
    let editable: Bool
    let mutationKinds: [String]
    let readOnlyReason: String?

    init?(_ result: [String: Any]) {
        guard result["domain"] as? String == "advanced",
              let entryID = result["entryId"] as? String,
              let raw = result["typedValue"], let value = Hades2SaveTypedValue(raw),
              let editable = result["editable"] as? Bool,
              let mutations = result["mutationKinds"] as? [String] else { return nil }
        self.entryID = entryID
        self.value = value
        self.warning = result["warning"] as? String
        self.editable = editable
        self.mutationKinds = mutations
        self.readOnlyReason = result["readOnlyReason"] as? String
    }
}
