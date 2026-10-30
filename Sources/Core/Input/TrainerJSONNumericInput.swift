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
    static func jsonObject(from text: String) -> Any? {
        try? TrainerJSON.object(with: Data(text.utf8)) { token in
            number(token).map { NSNumber(value: $0) }
        }
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
