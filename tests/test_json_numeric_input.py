"""User-authored JSON numeric precision before Foundation decoding."""
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

HARNESS = r'''
import Foundation
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
for text in ["9007199254740993", "9007199254740993.0", "9.007199254740993e15",
             "-9007199254740993", "1267650600228229401496703205375", "1267650600228229401496703205377",
             "1e-10000", "1e10000"] {
    check(TrainerJSONNumericInput.number(text) == nil, "rounded integer/underflow/overflow accepted: \(text)")
}
for text in ["9007199254740992", "9007199254740994", "1267650600228229401496703205376", "-1267650600228229401496703205376", "__GREATEST_FINITE_INTEGER__", "89884656743115795386465259539451236680898848947115328636715040578866337902750481566354238661203768010560056939935696678829394884407208311246423715319737062188883946712432742638151109800623047059726541476042502884419075341171231440736956555270413618581675255342293149119973622969239858152417678164812112068608"] {
    check(TrainerJSONNumericInput.number(text) == Double(text), "exact IEEE integer refused: \(text)")
    let object = TrainerJSONNumericInput.jsonObject(from: "{\"nested\":[\(text)]}") as? [String: Any]
    let nested = object?["nested"] as? [NSNumber]
    check(nested?.first?.doubleValue == Double(text), "JSON restoration changed exact integer: \(text)")
}
check(TrainerJSONNumericInput.number("__GREATEST_FINITE_INTEGER__") == Double.greatestFiniteMagnitude,
      "largest finite IEEE integer refused")
check(TrainerJSONNumericInput.number("0.1") == 0.1, "ordinary fractional rounding refused")
check(TrainerJSONNumericInput.number("4.9406564584124654e-324") == Double.leastNonzeroMagnitude,
      "nonzero subnormal refused")
check(TrainerJSONNumericInput.number("-0.0")?.bitPattern == (-0.0 as Double).bitPattern, "negative zero input lost")
check(TrainerJSONNumericInput.number("inf") == nil, "scalar infinity accepted")
check(TrainerJSONNumericInput.number("-inf", allowsInfinity: true) == -.infinity, "explicit key infinity refused")
check(TrainerJSONNumericInput.jsonObject(from: "{\"entries\":[{\"key\":{\"value\":9007199254740993}}]}") == nil,
      "nested rounded typed key accepted")
check(TrainerJSONNumericInput.jsonObject(from: "[9.007199254740993e15]") == nil,
      "nested rounded exponent accepted")
check(TrainerJSONNumericInput.jsonObject(from: "[01]") == nil, "invalid JSON number grammar accepted")
for text in ["{1:2}", "{-0:2}", "{1.0:2}", "{1e0:2}", "{\"valid\":{1:2}}"] {
    check(TrainerJSONNumericInput.jsonObject(from: text) == nil, "numeric JSON object key accepted: \(text)")
}
let zero = TrainerJSONNumericInput.jsonObject(from: "{\"value\":-0.0}") as! [String: Any]
check((zero["value"] as! NSNumber).doubleValue.bitPattern == (-0.0 as Double).bitPattern,
      "Foundation typed JSON decode lost negative zero")
check(TrainerJSONNumericInput.jsonObject(from: #"{"text":"9007199254740993 \" 1e99999"}"#) != nil,
      "numeric text inside escaped JSON string was parsed as a number")
let collisionText = #"{"n":"0","s:n":{"n":"1"},"s:":"s:","empty":"","escaped\"key":"s:n","\u006eested":{"n":"2"},"\u0301key":"\u0301value","array":[{"n":"0"},"s:","{\"n\":\"0\"}",0.1,true,false,null]}"#
let collision = TrainerJSONNumericInput.jsonObject(from: collisionText) as? [String: Any]
check(collision?["n"] as? String == "0", "user key n collided with a numeric witness")
check((collision?["s:n"] as? [String: String])?["n"] == "1", "prefixed user key was not restored")
check(collision?["s:"] as? String == "s:", "string marker collided with user content")
check(collision?["empty"] as? String == "", "empty string was not restored")
check(collision?["escaped\"key"] as? String == "s:n", "escaped string/key was not restored")
check((collision?["nested"] as? [String: String])?["n"] == "2", "Unicode-escaped user key collided")
check(collision?["\u{0301}key"] as? String == "\u{0301}value",
      "leading combining marks in a string/key were lost")
let collisionArray = collision?["array"] as? [Any]
check((collisionArray?[0] as? [String: String])?["n"] == "0", "nested user witness-shaped object collided")
check(collisionArray?[1] as? String == "s:", "nested string marker changed")
check(collisionArray?[2] as? String == #"{"n":"0"}"#, "witness-shaped string changed")
check((collisionArray?[3] as? NSNumber)?.doubleValue == 0.1, "nested fraction changed")
check(collisionArray?[4] as? Bool == true && collisionArray?[5] as? Bool == false,
      "JSON Boolean values changed")
check(collisionArray?[6] as? NSNull != nil, "JSON null changed")
for text in ["0", "-0.0", "4.9406564584124654e-324", "0.1"] {
    let restored = TrainerJSONNumericInput.jsonObject(from: text) as? NSNumber
    check(restored?.doubleValue.bitPattern == Double(text)?.bitPattern,
          "JSON fragment changed numeric bits: \(text)")
}
for value in [0, -0.0, 25, 0.1, 1.0000000000000002, Double(sign: .plus, exponent: 100, significand: 1),
              Double.leastNonzeroMagnitude, Double.greatestFiniteMagnitude] {
    let text = TrainerJSONNumericInput.numberText(value)
    check(TrainerJSONNumericInput.number(text)?.bitPattern == value.bitPattern,
          "generated numeric prefill could not be submitted unchanged: \(text)")
    let payload: [String: Any] = ["escaped\"key": [value, true, NSNull(), "\u{0301}\\text"] as [Any]]
    let json = TrainerJSONNumericInput.jsonText(from: payload)
    let object = TrainerJSONNumericInput.jsonObject(from: json) as? [String: Any]
    let items = object?["escaped\"key"] as? [Any]
    check((items?[0] as? NSNumber)?.doubleValue.bitPattern == value.bitPattern,
          "generated JSON prefill changed numeric bits: \(json)")
    check(items?[1] as? Bool == true && items?[2] is NSNull && items?[3] as? String == "\u{0301}\\text",
          "JSON writer changed Boolean, null or escaped string content")
}
let integerJSON = TrainerJSONNumericInput.jsonText(from: ["signed": Int64.max, "unsigned": UInt64.max] as [String: Any])
check(integerJSON.contains("9223372036854775807") && integerJSON.contains("18446744073709551615"),
      "JSON writer rounded native integer metadata through Double")
print("json_numeric_input_ok")
'''.replace("__GREATEST_FINITE_INTEGER__", str(int(float.fromhex("0x1.fffffffffffffp+1023"))))

with tempfile.TemporaryDirectory(prefix="mgt-json-numeric-input-") as temporary:
    base = Path(temporary)
    main, binary = base / "main.swift", base / "numeric-input"
    main.write_text(HARNESS)
    subprocess.run([SWIFTC, str(ROOT / "Sources/Core/Input/TrainerJSONNumericInput.swift"),
                    str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
