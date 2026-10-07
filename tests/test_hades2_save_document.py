import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import (  # noqa: E402
    Hades2SaveDocument,
    HadesSaveChecksumError,
    HadesSaveFormatError,
    LuaTable,
    read_hades2_save_header,
    UnsupportedHadesSaveVersionError,
)


def _u32(out, value):
    out += struct.pack("<I", value)


def _string(out, value):
    data = value.encode("utf-8")
    _u32(out, len(data))
    out += data


def _lua_value(out, value):
    if value is None:
        out += b"-"
    elif value is False:
        out += b"0"
    elif value is True:
        out += b"1"
    elif isinstance(value, (int, float)):
        out += b"N" + struct.pack("<d", float(value))
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        out += b"S" + struct.pack("<i", len(encoded)) + encoded
    elif isinstance(value, list):
        out += b"T" + struct.pack("<ii", len(value), 0)
        for index, item in enumerate(value, 1):
            _lua_value(out, index)
            _lua_value(out, item)
    elif isinstance(value, dict):
        out += b"T" + struct.pack("<ii", 0, len(value))
        for key, item in value.items():
            _lua_value(out, key)
            _lua_value(out, item)
    else:
        raise TypeError(type(value))


def _literal_lz4(payload):
    out = bytearray()
    length = len(payload)
    if length < 15:
        out.append(length << 4)
    else:
        out.append(0xF0)
        remaining = length - 15
        while remaining >= 255:
            out.append(255)
            remaining -= 255
        out.append(remaining)
    out += payload
    return bytes(out)


def build_save(*, version=0x12, lua_state=None):
    lua_state = lua_state or {
        "GameState": {
            "MetaPoints": 123.0,
            "UnknownFutureField": {"KeepMe": "yes"},
            "OrderedFlags": {"First": True, "Second": False},
        },
        "CurrentRun": {"RunDepthCache": 7.0},
    }
    luabins = bytearray([1])
    _lua_value(luabins, lua_state)
    compressed = _literal_lz4(luabins)

    body = bytearray()
    body += struct.pack("<HHQ", version, 3, 0x0102030405060708)
    _string(body, "Crossroads")
    body += struct.pack("<III", 42, 314, 9)
    if version in (0x11, 0x12):
        body += struct.pack("<I", 30)
    if version == 0x12:
        body += struct.pack("<I", 17)
    body += bytes([0, 1])
    body += struct.pack("<I", 2)
    _string(body, "GameState")
    _string(body, "CurrentRun")
    _string(body, "Hub_Main")
    _string(body, "F_Opening01")
    _u32(body, len(compressed))
    body += compressed

    data = bytearray(b"SGB1\0\0\0\0") + body
    struct.pack_into("<I", data, 4, zlib.adler32(data[8:]) & 0xFFFFFFFF)
    return bytes(data)


fixture = build_save()
doc = Hades2SaveDocument.from_bytes(fixture)
assert doc.header.game_version == 0x12
assert doc.header.location == "Crossroads"
assert doc.header.completed_runs == 42
assert doc.header.meta_upgrade_level == 30
assert doc.header.cosmetics_points == 17
assert doc.header.hard_mode == 1
assert doc.header.notable_lua_data == ("GameState", "CurrentRun")
assert doc.header.map_name == "Hub_Main"
assert doc.header.next_map_name == "F_Opening01"
assert isinstance(doc.lua_state, LuaTable)
game_state = doc.lua_state["GameState"]
assert isinstance(game_state, LuaTable)
assert game_state["MetaPoints"] == 123.0
assert game_state["UnknownFutureField"]["KeepMe"] == "yes"
assert list(game_state["OrderedFlags"].keys()) == ["First", "Second"]

# LuaTable mutations preserve the physical array/hash allocation partition.
mixed_table = LuaTable(2, 1, [(1.0, "a"), (2.0, "b"), ("named", "c")])
del mixed_table[1.0]
assert mixed_table.array_size == 1
assert mixed_table.hash_size == 1
del mixed_table["named"]
assert mixed_table.array_size == 1
assert mixed_table.hash_size == 0

# The primary #398 invariant: untouched saves round-trip byte-for-byte.
assert doc.to_bytes() == fixture

# Structured mutation rewrites a valid save while preserving unknown data.
game_state["MetaPoints"] = 999.0
mutated = doc.to_bytes()
assert mutated != fixture
assert struct.unpack_from("<I", mutated, 4)[0] == zlib.adler32(mutated[8:]) & 0xFFFFFFFF
reopened = Hades2SaveDocument.from_bytes(mutated)
assert reopened.lua_state["GameState"]["MetaPoints"] == 999.0
assert reopened.lua_state["GameState"]["UnknownFutureField"]["KeepMe"] == "yes"
assert list(reopened.lua_state["GameState"]["OrderedFlags"].keys()) == ["First", "Second"]

# Structured writes retain normal LZ4 compression instead of expanding the
# entire Lua payload as a literal-only block.
large_fixture = build_save(lua_state={"Blob": "ABCD" * 20000, "Keep": 7.0})
large_doc = Hades2SaveDocument.from_bytes(large_fixture)
large_doc.lua_state["Keep"] = 8.0
large_encoded = large_doc.to_bytes()
assert len(large_encoded) < 10_000, len(large_encoded)
assert Hades2SaveDocument.from_bytes(large_encoded).lua_state["Blob"] == "ABCD" * 20000

# File interface uses a caller-selected temporary path; it never resolves the real save tree.
with tempfile.TemporaryDirectory(prefix="mgt-hades-save-doc-") as td:
    path = Path(td) / "Profile1.sav"
    path.write_bytes(fixture)
    from_file = Hades2SaveDocument.load(path)
    assert from_file.to_bytes() == fixture
    header_only = read_hades2_save_header(path)
    assert header_only.completed_runs == 42
    assert header_only.map_name == "Hub_Main"

bad_checksum = bytearray(fixture)
bad_checksum[-1] ^= 0x01
try:
    Hades2SaveDocument.from_bytes(bad_checksum)
except HadesSaveChecksumError:
    pass
else:
    raise AssertionError("checksum mismatch must fail closed")

for truncated in (fixture[:3], fixture[:12], fixture[:-1]):
    try:
        Hades2SaveDocument.from_bytes(truncated)
    except HadesSaveFormatError:
        pass
    else:
        raise AssertionError("truncated save must fail closed")

unsupported = bytearray(build_save(version=0x12))
struct.pack_into("<H", unsupported, 8, 0x13)
struct.pack_into("<I", unsupported, 4, zlib.adler32(unsupported[8:]) & 0xFFFFFFFF)
try:
    Hades2SaveDocument.from_bytes(unsupported)
except UnsupportedHadesSaveVersionError:
    pass
else:
    raise AssertionError("unknown save version must fail closed")

# Exercise the public document parser with an LZ4 block that actually uses a
# back-reference instead of the literal-only synthetic fixture.
def build_save_with_compressed_payload(compressed, version=0x12):
    body = bytearray()
    body += struct.pack("<HHQ", version, 0, 0)
    _string(body, "")
    body += struct.pack("<III", 0, 0, 0)
    body += struct.pack("<I", 0)
    body += struct.pack("<I", 0)
    body += bytes([0, 0])
    body += struct.pack("<I", 0)
    _string(body, "")
    _string(body, "")
    _u32(body, len(compressed))
    body += compressed
    data = bytearray(b"SGB1\0\0\0\0") + body
    struct.pack_into("<I", data, 4, zlib.adler32(data[8:]) & 0xFFFFFFFF)
    return bytes(data)

# Luabins root table {"X": "ABABABABABAB"}. The first LZ4 sequence emits the
# whole luabins prefix and the first "AB", then an offset-2 match emits eight
# bytes; a final literal-only sequence contributes the last "AB".
raw = bytearray([1, ord("T")])
raw += struct.pack("<ii", 0, 1)
_lua_value(raw, "X")
_lua_value(raw, "ABABABABABAB")
prefix_len = len(raw) - 10
assert prefix_len == 23
compressed_with_match = bytes([0xF4, prefix_len - 15]) + bytes(raw[:prefix_len]) + b"\x02\x00" + bytes([0x20]) + b"AB"
matched_doc = Hades2SaveDocument.from_bytes(build_save_with_compressed_payload(compressed_with_match))
assert matched_doc.lua_state["X"] == "ABABABABABAB"
assert matched_doc.to_bytes() == build_save_with_compressed_payload(compressed_with_match)

# A malformed LZ4 offset with a valid outer checksum is corruption, not a
# partially readable save.
corrupt_lz4 = build_save_with_compressed_payload(b"\x00\x05\x00")
try:
    Hades2SaveDocument.from_bytes(corrupt_lz4)
except HadesSaveFormatError:
    pass
else:
    raise AssertionError("invalid LZ4 back-reference must fail closed")

# Luabins itself rejects NaN table keys; malformed saves must fail closed rather
# than entering a structured state Python cannot address reliably.
nan_key = build_save(lua_state={float("nan"): True})
try:
    Hades2SaveDocument.from_bytes(nan_key)
except HadesSaveFormatError:
    pass
else:
    raise AssertionError("NaN luabins table key must fail closed")

# Older Hades II v0x11 remains readable while the current v0x12-only field is absent.
v11 = Hades2SaveDocument.from_bytes(build_save(version=0x11))
assert v11.header.cosmetics_points is None
assert v11.to_bytes() == build_save(version=0x11)

print("hades2_save_document_ok")
