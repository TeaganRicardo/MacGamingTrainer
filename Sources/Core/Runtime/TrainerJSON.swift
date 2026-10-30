import Foundation

/// Foundation validates JSON structure and strings while numeric tokens retain
/// their integer identity or directly decoded IEEE value.
enum TrainerJSON {
    static func object(with data: Data) throws -> Any {
        try object(with: data, number: wireNumber)
    }

    static func object(with data: Data, number: (String) -> NSNumber?) throws -> Any {
        let bytes = Array(data)
        var result: [UInt8] = []
        var numbers: [NSNumber] = []
        var index = 0
        var inString = false
        while index < bytes.count {
            let byte = bytes[index]
            if inString {
                result.append(byte)
                index += 1
                if byte == 92, index < bytes.count {
                    result.append(bytes[index]); index += 1
                } else if byte == 34 { inString = false }
            } else if byte == 34 {
                // Every original string/key gets a prefix, so the unprefixed
                // numeric witness key cannot collide with user content.
                inString = true; result.append(contentsOf: [34, 115, 58]); index += 1
            } else if byte == 45 || (48...57).contains(byte) {
                let start = index
                while index < bytes.count {
                    let byte = bytes[index]
                    guard [UInt8(45), 43, 46, 69, 101].contains(byte) || (48...57).contains(byte) else { break }
                    index += 1
                }
                let token = String(decoding: bytes[start..<index], as: UTF8.self)
                guard token.range(of: #"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"#,
                                  options: .regularExpression) != nil,
                      let value = number(token) else {
                    throw NSError(domain: NSCocoaErrorDomain, code: 3840,
                                  userInfo: [NSLocalizedDescriptionKey: "Invalid JSON number."])
                }
                result.append(contentsOf: "{\"n\":\"\(numbers.count)\"}".utf8)
                numbers.append(value)
            } else {
                result.append(byte); index += 1
            }
        }
        let object = try JSONSerialization.jsonObject(with: Data(result), options: [.fragmentsAllowed])
        func restore(_ value: Any) -> Any {
            if let text = value as? String {
                return String(decoding: text.utf8.dropFirst(2), as: UTF8.self)
            }
            if let items = value as? [Any] { return items.map(restore) }
            if let fields = value as? [String: Any] {
                if let index = fields["n"] as? String { return numbers[Int(index)!] }
                return Dictionary(uniqueKeysWithValues: fields.map {
                    (String(decoding: $0.key.utf8.dropFirst(2), as: UTF8.self), restore($0.value))
                })
            }
            return value
        }
        return restore(object)
    }

    private static func wireNumber(_ token: String) -> NSNumber? {
        if token == "-0" { return NSNumber(value: -0.0) }
        if let value = Int64(token) { return NSNumber(value: value) }
        if let value = UInt64(token) { return NSNumber(value: value) }
        guard let value = Double(token), value.isFinite else { return nil }
        return NSNumber(value: value)
    }
}
