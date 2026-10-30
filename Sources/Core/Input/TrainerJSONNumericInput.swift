import Foundation
import CoreFoundation

/// Parses user-authored JSON numbers before Foundation can round integer input.
enum TrainerJSONNumericInput {
    /// User-editable numbers must satisfy the same integer precision policy
    /// when submitted again, including integers beyond decimal formatter limits.
    static func numberText(_ value: Double) -> String {
        if value == 0, value.sign == .minus { return "-0" }
        if let integer = exactIntegerDecimal(value) { return integer }
        return String(value)
    }

    /// Writes the finite JSON values produced by typed Save owners without
    /// decimal reparsing or rounding the numbers in editable prefills.
    static func jsonText(from object: Any) -> String {
        func string(_ value: String) -> String {
            String(data: try! JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]), encoding: .utf8)!
        }
        func write(_ value: Any, depth: Int) -> String {
            if let text = value as? String { return string(text) }
            if let number = value as? NSNumber {
                if CFGetTypeID(number) == CFBooleanGetTypeID() { return number.boolValue ? "true" : "false" }
                let type = String(cString: number.objCType)
                return type == "f" || type == "d" ? numberText(number.doubleValue) : number.stringValue
            }
            if value is NSNull { return "null" }
            let indent = String(repeating: "  ", count: depth)
            let childIndent = indent + "  "
            if let items = value as? [Any] {
                if items.isEmpty { return "[]" }
                return "[\n" + items.map { childIndent + write($0, depth: depth + 1) }.joined(separator: ",\n") + "\n" + indent + "]"
            }
            if let fields = value as? [String: Any] {
                if fields.isEmpty { return "{}" }
                return "{\n" + fields.keys.sorted().map {
                    childIndent + string($0) + " : " + write(fields[$0]!, depth: depth + 1)
                }.joined(separator: ",\n") + "\n" + indent + "}"
            }
            preconditionFailure("Unsupported typed JSON value")
        }
        return write(object, depth: 0)
    }

    static func number(_ text: String, allowsInfinity: Bool = false) -> Double? {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if allowsInfinity {
            if ["inf", "+inf"].contains(text.lowercased()) { return .infinity }
            if text.lowercased() == "-inf" { return -.infinity }
        }
        guard text.range(of: #"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"#,
                         options: .regularExpression) != nil,
              let value = Double(text), value.isFinite else { return nil }
        let mantissa = text.lowercased().split(separator: "e")[0]
        if value == 0, mantissa.utf8.contains(where: { (49...57).contains($0) }) { return nil }
        if let integer = integralDecimal(text) {
            guard integer == exactIntegerDecimal(value) else { return nil }
        }
        return value
    }

    /// Builds the integer from IEEE bits; decimal formatters can round large
    /// integers even when asked for zero fractional digits.
    private static func exactIntegerDecimal(_ value: Double) -> String? {
        if value == 0 { return "0" }
        let bits = value.bitPattern
        let exponentBits = Int((bits >> 52) & 0x7ff)
        guard exponentBits != 0 else { return nil }
        var significand = (bits & 0x000f_ffff_ffff_ffff) | (UInt64(1) << 52)
        let exponent = exponentBits - 1023 - 52
        if exponent < 0 {
            let shift = -exponent
            guard shift <= 52 else { return nil }
            let divisor = UInt64(1) << shift
            guard significand % divisor == 0 else { return nil }
            significand /= divisor
        }
        // At most 971 doublings and 309 decimal digits for a finite Double.
        var digits = String(significand).utf8.reversed().map { $0 - 48 }
        for _ in 0..<max(0, exponent) {
            var carry: UInt8 = 0
            for index in digits.indices {
                let next = digits[index] * 2 + carry
                digits[index] = next % 10
                carry = next / 10
            }
            if carry != 0 { digits.append(carry) }
        }
        let decimal = String(bytes: digits.reversed().map { $0 + 48 }, encoding: .utf8)!
        return value.sign == .minus ? "-" + decimal : decimal
    }

    /// Validates every numeric token, including nested typed table keys/values.
    /// Foundation parses structure and strings; validated numeric bits are
    /// restored directly without passing through its decimal number decoder.
    static func jsonObject(from text: String) -> Any? {
        let bytes = Array(text.utf8)
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
                // JSON's grammar is narrower than standalone numeric input.
                guard token.range(of: #"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"#,
                                  options: .regularExpression) != nil,
                      let value = number(token) else { return nil }
                result.append(contentsOf: "{\"n\":\"\(numbers.count)\"}".utf8)
                numbers.append(NSNumber(value: value))
            } else {
                result.append(byte); index += 1
            }
        }
        guard let object = try? JSONSerialization.jsonObject(with: Data(result), options: [.fragmentsAllowed])
        else { return nil }
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

    /// Nil denotes a mathematically fractional decimal, which may use IEEE rounding.
    private static func integralDecimal(_ text: String) -> String? {
        var body = text.lowercased()
        let negative = body.first == "-"
        if body.first == "-" || body.first == "+" { body.removeFirst() }
        let parts = body.split(separator: "e", omittingEmptySubsequences: false)
        let mantissa = String(parts[0])
        let limit = text.utf8.count + 1024
        var exponent = 0
        if parts.count == 2 {
            var exponentText = parts[1]
            let minus = exponentText.first == "-"
            if exponentText.first == "-" || exponentText.first == "+" { exponentText = exponentText.dropFirst() }
            for digit in exponentText.utf8 {
                exponent = min(limit, exponent * 10 + Int(digit - 48))
            }
            if minus { exponent = -exponent }
        }
        let fractionCount = mantissa.firstIndex(of: ".").map { mantissa.distance(from: mantissa.index(after: $0), to: mantissa.endIndex) } ?? 0
        var digits = mantissa.filter { $0 != "." }
        while digits.first == "0" { digits.removeFirst() }
        if digits.isEmpty { return "0" }
        let scale = exponent - fractionCount
        if scale < 0 {
            let count = -scale
            guard count <= digits.count, digits.suffix(count).allSatisfy({ $0 == "0" }) else { return nil }
            digits.removeLast(count)
        } else {
            digits += String(repeating: "0", count: scale)
        }
        return negative ? "-" + digits : digits
    }
}
