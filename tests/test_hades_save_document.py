"""Exact native-format synthetic fixtures, typed keys, raw bits and shared LZ4."""
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import Entries, RawNumber, build_save, container, lua
from games.hades.save_document import HadesSaveDocument, LuaTable, SaveFormatError, AmbiguousKeyError, encode_lua, decode_lua
from games.hades import save_values as values
from games.hades2.save_document import Hades2SaveDocument, _compress_lz4_block, _decompress_lz4_block, HadesSaveFormatError
from core import lz4_block


def rejects(action, kind=ValueError):
    try: action()
    except kind: return
    raise AssertionError('Malformed native bytes/value were accepted')


key_table = Entries([('Key', b'\xff\x00')])
physical = Entries([('Duplicate', 1), ('Duplicate', 2), (True, 'bool'), (1, 'number'),
                    (1.0, 'numeric-alias'), (b'\xff\x00', b'\xfe\x00'), (key_table, 'table-key'),
                    ('NegativeZero', RawNumber('0000000000000080')),
                    ('SignalingNaN', RawNumber('010000000000f07f'))])
raw = build_save(state=Entries([('Physical', physical), ('Other', 12)]), extra=(b'\x81\x00',))
document = HadesSaveDocument.from_bytes(raw)
assert document.to_bytes() == raw, 'Unchanged native bytes were rewritten'
assert document.header.location.encode('utf-8', errors='surrogateescape') == b'RoomPreRun\xff'
assert document.header.notable_lua_data[1].encode('utf-8', errors='surrogateescape') == b'Trait\xfe'
assert document.lua_values[1].encode('utf-8', errors='surrogateescape') == b'\x81\x00'
table = document.lua_state['Physical']
assert table[True] == 'bool'
rejects(lambda: table['Duplicate'], AmbiguousKeyError)
rejects(lambda: table[1], AmbiguousKeyError)
assert isinstance(table.entries()[6][0], LuaTable)
original_lua = encode_lua(document.lua_values)
document.lua_state['Other'] = 44
changed = document.to_bytes()
parsed = HadesSaveDocument.from_bytes(changed)
assert parsed.lua_state['Other'] == 44
for name in ('NegativeZero', 'SignalingNaN'):
    assert parsed.lua_state['Physical'][name].raw == table[name].raw
assert encode_lua([parsed.lua_state['Physical']]) == encode_lua([table])
assert original_lua != encode_lua(parsed.lua_values)

# Physical paths distinguish duplicate/typed keys and permit table-key content repair.
cloned = HadesSaveDocument.from_bytes(raw)
values.mutate(cloned, (0, 1, 3), 'set', {'luaType': 'number', 'value': 17})
assert cloned.lua_state['Physical'].entries()[:2] == (('Duplicate', 1), ('Duplicate', 17))
values.mutate(cloned, (0, 1, 12, 1), 'set', {'luaType': 'string', 'encoding': 'base64', 'value': '/wE='})
reparsed = HadesSaveDocument.from_bytes(cloned.to_bytes())
assert reparsed.lua_state['Physical'].entries()[6][0]['Key'].encode('utf-8', errors='surrogateescape') == b'\xff\x01'
for node in (None, True, 1.5, b'\xff', physical):
    decoded = decode_lua(b'\x01' + lua(node))[0]
    assert encode_lua([values.from_typed(values.typed(decoded))]) == encode_lua([decoded])
rejects(lambda: values.from_typed({'luaType': 'number', 'value': True}))
rejects(lambda: values.from_typed({'luaType': 'string', 'encoding': 'base64', 'value': '!!'}))
rejects(lambda: values.from_typed({'luaType': 'table', 'entries': [{'key': {'luaType': 'nil'}, 'value': {'luaType': 'nil'}}]}))

# Current native writer has 250 table levels, and the native loader caps top values at250.
nested = 1
for _ in range(250): nested = Entries([('child', nested)])
deep = container(b'\x01' + lua(nested))
assert HadesSaveDocument.from_bytes(deep).to_bytes() == deep
nested = Entries([('tooDeep', nested)])
rejects(lambda: HadesSaveDocument.from_bytes(container(b'\x01' + lua(nested))))
rejects(lambda: decode_lua(bytes([251]) + b'-' * 251))
rejects(lambda: HadesSaveDocument.from_bytes(container(b'\x01T' + struct.pack('<Ii', 0x4000001, 0))))
rejects(lambda: HadesSaveDocument.from_bytes(raw[:-1]))
corrupt = bytearray(raw); corrupt[-1] ^= 1
rejects(lambda: HadesSaveDocument.from_bytes(corrupt), SaveFormatError)
rejects(lambda: HadesSaveDocument.from_bytes(container(b'\x01' + lua({}), version=17)))
rejects(lambda: HadesSaveDocument.from_bytes(container(b'\x01' + lua({}), compressed=b'\x00\x00\x00')))
rejects(lambda: Hades2SaveDocument.from_bytes(raw), HadesSaveFormatError)

# Both game-owned wrappers share raw blocks without sharing container schemas/limits.
payload = (b'Hades-compatible LZ4 primitive\x00' * 300) + bytes(range(256))
shared = lz4_block.compress(payload, len(payload))
assert lz4_block.decompress(shared, len(payload)) == payload
assert _decompress_lz4_block(shared) == payload
assert lz4_block.decompress(_compress_lz4_block(payload), len(payload)) == payload
rejects(lambda: lz4_block.decompress(shared, len(payload) - 1), lz4_block.LZ4BlockError)
rejects(lambda: lz4_block.compress(payload, len(payload) - 1), lz4_block.LZ4BlockError)
print('hades_native_save_document_lossless_typed_keys_and_shared_lz4_ok')
