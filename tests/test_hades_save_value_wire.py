"""Hades typed values retain native bits through actual Swift JSON wire output."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from games.hades.save_document import encode_lua
from games.hades.save_values import from_typed

SWIFTC = shutil.which('swiftc')
if not SWIFTC:
    raise SystemExit('swiftc required')

HARNESS = r'''
import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

let large = Double(sign: .plus, exponent: 100, significand: 1)
let exactLarge = "1267650600228229401496703205376"
check(HadesSaveValue.number(large).scalarText == exactLarge, "scalar prefill rounded an exact large integer")
let scalarPrefill = TrainerJSONNumericInput.number(HadesSaveValue.number(large).scalarText!)!
check(scalarPrefill.bitPattern == large.bitPattern, "scalar prefill could not be submitted unchanged")
let typedLarge = HadesSaveValue.inputJSON("{\"luaType\":\"number\",\"value\":\(exactLarge)}")!
check((typedLarge.object["value"] as! NSNumber).doubleValue.bitPattern == large.bitPattern,
      "typed input lost its validated large integer before wire output")
let prefilledLarge = HadesSaveValue.inputJSON(HadesSaveValue.number(large).json)!
let typedZero = HadesSaveValue.inputJSON(#"{"luaType":"number","value":-0.0}"#)!

let table = HadesSaveValue.table(arraySize: 0, hashSize: 6, entries: [
    .init(key: .string("big"), value: .number(large)),
    .init(key: .string("zero"), value: .number(-0.0)),
    .init(key: .string("raw"), value: .rawNumber("010000000000f07f")),
    .init(key: .rawString("/wA="), value: .rawString("/gA=")),
    .init(key: .number(large), value: .string("large numeric key")),
    .init(key: .string("other"), value: .boolean(true))])
let prefilledTable = HadesSaveValue.inputJSON(table.json)!
let changedTable = HadesSaveValue.inputJSON(table.json.replacingOccurrences(of: "\"other\"", with: "\"changed\""))!
for invalid in [#"{"luaType":"number","value":9007199254740993}"#,
                #"{"luaType":"number","value":1.2676506002282294e30}"#,
                #"{"luaType":"number","value":true}"#,
                #"{"luaType":"boolean","value":1}"#,
                #"{"luaType":"number","encoding":1,"value":1}"#,
                #"{"luaType":"table","arraySize":false,"hashSize":0,"entries":[]}"#,
                #"{"luaType":"table","arraySize":0.5,"hashSize":0,"entries":[]}"#,
                #"{"luaType":"table","arraySize":0,"entries":[]}"#,
                #"{"luaType":"table","arraySize":0,"hashSize":1,"entries":[{"key":{"luaType":"nil"}}]}"#] {
    check(HadesSaveValue.inputJSON(invalid) == nil, "typed input accepted a rounded number or mismatched Codable shape")
}
let samples: [[String: Any]] = [
    ["name": "direct", "value": HadesSaveValue.number(large).object],
    ["name": "scalar-prefill", "value": HadesSaveValue.number(scalarPrefill).object],
    ["name": "typed-input", "value": typedLarge.object],
    ["name": "typed-prefill", "value": prefilledLarge.object],
    ["name": "negative-zero", "value": HadesSaveValue.number(-0.0).object],
    ["name": "typed-negative-zero", "value": typedZero.object],
    ["name": "table", "value": table.object],
    ["name": "table-prefill", "value": prefilledTable.object],
    ["name": "table-edited", "value": changedTable.object]]
let wire = try JSONSerialization.data(withJSONObject: samples, options: [.sortedKeys])
print(String(data: wire, encoding: .utf8)!)
'''

with tempfile.TemporaryDirectory(prefix='mgt-hades-save-value-wire-') as temporary:
    base = Path(temporary)
    # Compile the owning representation unchanged, without the unrelated
    # AppKit/Combine editor model on portable runners.
    source = (ROOT / 'Sources/Hades/HadesSaveEditorModel.swift').read_text()
    value_source = source.split('\nenum HadesSaveEditorDomain', 1)[0].replace('import Combine\n', '')
    values_file, main, binary = base / 'HadesSaveValue.swift', base / 'main.swift', base / 'wire'
    values_file.write_text(value_source)
    main.write_text(HARNESS)
    subprocess.run([SWIFTC, str(ROOT / 'Sources/Core/Input/TrainerJSONNumericInput.swift'),
                    str(values_file), str(main), '-o', str(binary)], check=True)
    wire = subprocess.check_output([str(binary)], text=True)

samples = {item['name']: item['value'] for item in json.loads(wire)}
large_bytes = struct.pack('<d', float(2 ** 100))
for name in ('direct', 'scalar-prefill', 'typed-input', 'typed-prefill'):
    assert struct.pack('<d', from_typed(samples[name])) == large_bytes, name
for name in ('negative-zero', 'typed-negative-zero'):
    assert struct.pack('<d', from_typed(samples[name])) == bytes.fromhex('0000000000000080'), name

table = from_typed(samples['table'])
assert table.array_size == 0 and table.hash_size == 6
assert [key for key, _ in table.entries()] == ['big', 'zero', 'raw', '\udcff\x00', float(2 ** 100), 'other']
assert struct.pack('<d', table['big']) == large_bytes
assert table['zero'].raw == bytes.fromhex('0000000000000080')
assert table['raw'].raw == bytes.fromhex('010000000000f07f')
assert table['\udcff\x00'].encode('utf-8', errors='surrogateescape') == b'\xfe\x00'
assert table[float(2 ** 100)] == 'large numeric key'
assert table['other'] is True
assert encode_lua([from_typed(samples['table-prefill'])]) == encode_lua([table])
changed = from_typed(samples['table-edited'])
assert [key for key, _ in changed.entries()[:-1]] == [key for key, _ in table.entries()[:-1]]
assert encode_lua([value for _, value in changed.entries()[:-1]]) == encode_lua([value for _, value in table.entries()[:-1]])
assert changed.entries()[-1] == ('changed', True)
assert changed.array_size == table.array_size and changed.hash_size == table.hash_size
print('hades_save_value_wire_precision_and_prefill_ok')
