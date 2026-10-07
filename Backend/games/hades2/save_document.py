"""Structured Hades II SGB1 save documents.

The SGB1 container / LZ4 block / luabins format implementation is derived from
format knowledge published by TheNormalnij/Hades-SavesExtractor (MIT).

This module owns only Hades save bytes and their structured representation. It
does not resolve the user's real save path and does not perform destructive
replace/rollback transactions; Core Save owns those responsibilities.
"""

from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib


SGB1_MAGIC = b"SGB1"
HADES2_SAVE_VERSION = 0x11
HADES2_PATCH11_SAVE_VERSION = 0x12
SUPPORTED_HADES2_SAVE_VERSIONS = frozenset({
    HADES2_SAVE_VERSION,
    HADES2_PATCH11_SAVE_VERSION,
})

_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_HEADER_STRING_BYTES = 1024 * 1024
_MAX_NOTABLE_LUA_ITEMS = 1_000_000
_MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024
_MAX_LUABINS_DEPTH = 128
_MAX_LUABINS_TABLE_ENTRIES = 10_000_000

_LUABINS_NIL = ord("-")
_LUABINS_FALSE = ord("0")
_LUABINS_TRUE = ord("1")
_LUABINS_NUMBER = ord("N")
_LUABINS_STRING = ord("S")
_LUABINS_TABLE = ord("T")


class HadesSaveError(ValueError):
    """Base class for a save that cannot be represented safely."""


class HadesSaveFormatError(HadesSaveError):
    """The save is truncated or violates the supported SGB1/luabins format."""


class HadesSaveChecksumError(HadesSaveFormatError):
    """The stored SGB1 Adler-32 checksum does not match the payload."""


class UnsupportedHadesSaveVersionError(HadesSaveFormatError):
    """The save is not a supported Hades II SGB1 schema version."""


def _same_lua_key(left, right):
    # Lua booleans and numbers are distinct keys, unlike Python's True == 1.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    return type(left) is type(right) and left == right


class LuaTable(MutableMapping):
    """Ordered luabins table preserving allocation hints and unknown entries.

    ``array_size`` and ``hash_size`` are luabins allocation hints, not a second
    semantic schema. Existing entries retain their serialized order. New keys
    are counted as hash entries so later editor domains can add a supported
    field without rebuilding or classifying the rest of the table.
    """

    __slots__ = ("array_size", "hash_size", "_entries")

    def __init__(self, array_size=0, hash_size=0, entries=()):
        if array_size < 0 or hash_size < 0:
            raise HadesSaveFormatError("negative luabins table size")
        self.array_size = int(array_size)
        self.hash_size = int(hash_size)
        self._entries = list(entries)
        if self.array_size + self.hash_size != len(self._entries):
            raise HadesSaveFormatError("luabins table size does not match entry count")

    def __getitem__(self, key):
        for entry_key, value in self._entries:
            if _same_lua_key(entry_key, key):
                return value
        raise KeyError(key)

    def __setitem__(self, key, value):
        if key is None:
            raise TypeError("Lua table keys cannot be nil")
        for index, (entry_key, _old_value) in enumerate(self._entries):
            if _same_lua_key(entry_key, key):
                self._entries[index] = (entry_key, value)
                return
        self._entries.append((key, value))
        self.hash_size += 1

    def __delitem__(self, key):
        for index, (entry_key, _value) in enumerate(self._entries):
            if _same_lua_key(entry_key, key):
                del self._entries[index]
                # The counts are allocation hints. Prefer shrinking the hash
                # hint for editor-added/deleted fields; fall back to array.
                if self.hash_size:
                    self.hash_size -= 1
                elif self.array_size:
                    self.array_size -= 1
                return
        raise KeyError(key)

    def __iter__(self) -> Iterator:
        return (key for key, _value in self._entries)

    def __len__(self):
        return len(self._entries)

    def entries(self):
        return tuple(self._entries)

    def __repr__(self):
        return "LuaTable(array_size={!r}, hash_size={!r}, entries={!r})".format(
            self.array_size,
            self.hash_size,
            self._entries,
        )


@dataclass
class Hades2SaveHeader:
    game_version: int
    save_flags: int
    timestamp: int
    location: str
    completed_runs: int
    accumulated_meta_points: int
    active_shrine_points: int
    meta_upgrade_level: int
    cosmetics_points: int | None
    easy_mode: int
    hard_mode: int
    notable_lua_data: tuple[str, ...]
    map_name: str
    next_map_name: str


class _Reader:
    __slots__ = ("_data", "pos")

    def __init__(self, data):
        self._data = memoryview(data)
        self.pos = 0

    @property
    def remaining(self):
        return len(self._data) - self.pos

    def take(self, size, field="data"):
        if size < 0 or size > self.remaining:
            raise HadesSaveFormatError("truncated {}".format(field))
        start = self.pos
        self.pos += size
        return bytes(self._data[start:self.pos])

    def u8(self, field="u8"):
        return self.take(1, field)[0]

    def u16(self, field="u16"):
        return struct.unpack("<H", self.take(2, field))[0]

    def u32(self, field="u32"):
        return struct.unpack("<I", self.take(4, field))[0]

    def i32(self, field="i32"):
        return struct.unpack("<i", self.take(4, field))[0]

    def u64(self, field="u64"):
        return struct.unpack("<Q", self.take(8, field))[0]

    def f64(self, field="number"):
        return struct.unpack("<d", self.take(8, field))[0]

    def sized_bytes(self, field, *, signed=False, max_size=None):
        size = self.i32(field + " length") if signed else self.u32(field + " length")
        if size < 0:
            raise HadesSaveFormatError("negative {} length".format(field))
        if max_size is not None and size > max_size:
            raise HadesSaveFormatError("{} exceeds size limit".format(field))
        return self.take(size, field)

    def string(self, field):
        raw = self.sized_bytes(field, max_size=_MAX_HEADER_STRING_BYTES)
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise HadesSaveFormatError("{} is not valid UTF-8".format(field)) from error


class _Writer:
    __slots__ = ("data",)

    def __init__(self):
        self.data = bytearray()

    def u8(self, value):
        self.data += struct.pack("<B", value)

    def u16(self, value):
        self.data += struct.pack("<H", value)

    def u32(self, value):
        self.data += struct.pack("<I", value)

    def i32(self, value):
        self.data += struct.pack("<i", value)

    def u64(self, value):
        self.data += struct.pack("<Q", value)

    def f64(self, value):
        self.data += struct.pack("<d", float(value))

    def bytes(self, value):
        self.data += value

    def sized_bytes(self, value):
        self.u32(len(value))
        self.bytes(value)

    def string(self, value):
        self.sized_bytes(value.encode("utf-8", errors="strict"))


def _decompress_lz4_block(data):
    """Decode one raw LZ4 block with strict bounds and no external runtime."""

    source = memoryview(data)
    output = bytearray()
    pos = 0

    def read_extension(label):
        nonlocal pos
        total = 0
        while True:
            if pos >= len(source):
                raise HadesSaveFormatError("truncated LZ4 {} extension".format(label))
            value = source[pos]
            pos += 1
            total += value
            if value != 255:
                return total

    def ensure_output(extra):
        if extra < 0 or len(output) + extra > _MAX_DECOMPRESSED_BYTES:
            raise HadesSaveFormatError("decompressed save exceeds size limit")

    while pos < len(source):
        token = source[pos]
        pos += 1
        literal_length = token >> 4
        match_length = token & 0x0F

        if literal_length == 15:
            literal_length += read_extension("literal length")
        if literal_length > len(source) - pos:
            raise HadesSaveFormatError("truncated LZ4 literal run")
        ensure_output(literal_length)
        output += source[pos:pos + literal_length]
        pos += literal_length

        if pos == len(source):
            break
        if len(source) - pos < 2:
            raise HadesSaveFormatError("truncated LZ4 match offset")

        offset = source[pos] | (source[pos + 1] << 8)
        pos += 2
        if offset == 0 or offset > len(output):
            raise HadesSaveFormatError("invalid LZ4 match offset")

        if match_length == 15:
            match_length += read_extension("match length")
        match_length += 4
        ensure_output(match_length)

        # LZ4 overlapping match copy is periodic with ``offset``. Expanding the
        # currently available window avoids a byte-at-a-time Python loop for
        # large real saves while preserving overlap semantics.
        pattern = bytes(output[-offset:])
        repeats = (match_length + len(pattern) - 1) // len(pattern)
        output += (pattern * repeats)[:match_length]

    return bytes(output)


def _literal_lz4_block(payload):
    """Encode a valid raw LZ4 block as one final literal-only sequence.

    Untouched documents reuse the game's original compressed bytes exactly.
    This dependency-free encoder is therefore only used after a structured
    mutation. It favors deterministic correctness over compression ratio; a
    later optimization may replace it without changing the document interface.
    """

    if len(payload) > _MAX_DECOMPRESSED_BYTES:
        raise HadesSaveFormatError("luabins payload exceeds size limit")
    output = bytearray()
    length = len(payload)
    if length < 15:
        output.append(length << 4)
    else:
        output.append(0xF0)
        remaining = length - 15
        while remaining >= 255:
            output.append(255)
            remaining -= 255
        output.append(remaining)
    output += payload
    return bytes(output)


def _decode_luabins(data):
    reader = _Reader(data)

    def read_value(type_byte, depth):
        if depth > _MAX_LUABINS_DEPTH:
            raise HadesSaveFormatError("luabins table nesting too deep")
        if type_byte == _LUABINS_NIL:
            return None
        if type_byte == _LUABINS_FALSE:
            return False
        if type_byte == _LUABINS_TRUE:
            return True
        if type_byte == _LUABINS_NUMBER:
            return reader.f64("luabins number")
        if type_byte == _LUABINS_STRING:
            raw = reader.sized_bytes(
                "luabins string",
                signed=True,
                max_size=_MAX_DECOMPRESSED_BYTES,
            )
            # Lua strings are byte strings. Surrogateescape keeps arbitrary
            # bytes lossless while ordinary game text remains a normal str.
            return raw.decode("utf-8", errors="surrogateescape")
        if type_byte == _LUABINS_TABLE:
            array_size = reader.i32("luabins array size")
            hash_size = reader.i32("luabins hash size")
            if array_size < 0 or hash_size < 0:
                raise HadesSaveFormatError("negative luabins table size")
            total = array_size + hash_size
            if total > _MAX_LUABINS_TABLE_ENTRIES:
                raise HadesSaveFormatError("luabins table exceeds entry limit")
            entries = []
            for _index in range(total):
                key_type = reader.u8("luabins key type")
                key = read_value(key_type, depth + 1)
                if key is None or isinstance(key, LuaTable):
                    raise HadesSaveFormatError("unsupported luabins table key")
                value_type = reader.u8("luabins value type")
                value = read_value(value_type, depth + 1)
                entries.append((key, value))
            return LuaTable(array_size, hash_size, entries)
        raise HadesSaveFormatError(
            "unknown luabins type 0x{:02x}".format(type_byte)
        )

    count = reader.u8("luabins top-level value count")
    if count == 0:
        raise HadesSaveFormatError("luabins payload has no top-level values")
    values = []
    for _index in range(count):
        values.append(read_value(reader.u8("luabins value type"), 0))
    if reader.remaining:
        raise HadesSaveFormatError("unexpected trailing luabins bytes")
    return values


def _encode_luabins(values):
    if not values or len(values) > 255:
        raise HadesSaveFormatError("invalid luabins top-level value count")
    writer = _Writer()
    writer.u8(len(values))

    def write_value(value, depth):
        if depth > _MAX_LUABINS_DEPTH:
            raise HadesSaveFormatError("luabins table nesting too deep")
        if value is None:
            writer.u8(_LUABINS_NIL)
            return
        if value is False:
            writer.u8(_LUABINS_FALSE)
            return
        if value is True:
            writer.u8(_LUABINS_TRUE)
            return
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            writer.u8(_LUABINS_NUMBER)
            writer.f64(value)
            return
        if isinstance(value, str):
            raw = value.encode("utf-8", errors="surrogateescape")
            if len(raw) > 0x7FFFFFFF:
                raise HadesSaveFormatError("luabins string exceeds size limit")
            writer.u8(_LUABINS_STRING)
            writer.i32(len(raw))
            writer.bytes(raw)
            return
        if isinstance(value, LuaTable):
            entries = value.entries()
            if value.array_size + value.hash_size != len(entries):
                raise HadesSaveFormatError("luabins table size does not match entry count")
            writer.u8(_LUABINS_TABLE)
            writer.i32(value.array_size)
            writer.i32(value.hash_size)
            for key, item in entries:
                if key is None or isinstance(key, LuaTable):
                    raise HadesSaveFormatError("unsupported luabins table key")
                write_value(key, depth + 1)
                write_value(item, depth + 1)
            return
        raise HadesSaveFormatError(
            "unsupported structured save value: {}".format(type(value).__name__)
        )

    for value in values:
        write_value(value, 0)
    return bytes(writer.data)


def _parse_header_prefix(data):
    """Validate an SGB1 file and decode the complete Hades header prefix.

    Snapshot presentation only needs this prefix; the document decoder
    continues through the compressed luabins payload below. Both callers share
    this one physical-format owner instead of maintaining parallel header
    layouts.
    """

    if len(data) > _MAX_FILE_BYTES:
        raise HadesSaveFormatError("save file exceeds size limit")
    if len(data) < 12:
        raise HadesSaveFormatError("truncated SGB1 header")
    if data[:4] != SGB1_MAGIC:
        raise HadesSaveFormatError("not an SGB1 save file")

    stored_checksum = struct.unpack_from("<I", data, 4)[0]
    actual_checksum = zlib.adler32(data[8:]) & 0xFFFFFFFF
    if stored_checksum != actual_checksum:
        raise HadesSaveChecksumError(
            "SGB1 checksum mismatch: stored {:08x}, calculated {:08x}".format(
                stored_checksum,
                actual_checksum,
            )
        )

    reader = _Reader(data[8:])
    game_version = reader.u16("game version")
    if game_version not in SUPPORTED_HADES2_SAVE_VERSIONS:
        raise UnsupportedHadesSaveVersionError(
            "unsupported Hades II save version 0x{:02x}".format(game_version)
        )

    save_flags = reader.u16("save flags")
    timestamp = reader.u64("timestamp")
    location = reader.string("location")
    completed_runs = reader.u32("completed runs")
    accumulated_meta_points = reader.u32("accumulated meta points")
    active_shrine_points = reader.u32("active shrine points")
    meta_upgrade_level = reader.u32("meta upgrade level")
    cosmetics_points = None
    if game_version == HADES2_PATCH11_SAVE_VERSION:
        cosmetics_points = reader.u32("cosmetics points")
    easy_mode = reader.u8("easy mode")
    hard_mode = reader.u8("hard mode")

    notable_count = reader.u32("notable Lua data count")
    if notable_count > _MAX_NOTABLE_LUA_ITEMS:
        raise HadesSaveFormatError("notable Lua data count exceeds limit")
    notable_lua_data = tuple(
        reader.string("notable Lua data") for _index in range(notable_count)
    )
    map_name = reader.string("map name")
    next_map_name = reader.string("next map name")

    header = Hades2SaveHeader(
        game_version=game_version,
        save_flags=save_flags,
        timestamp=timestamp,
        location=location,
        completed_runs=completed_runs,
        accumulated_meta_points=accumulated_meta_points,
        active_shrine_points=active_shrine_points,
        meta_upgrade_level=meta_upgrade_level,
        cosmetics_points=cosmetics_points,
        easy_mode=easy_mode,
        hard_mode=hard_mode,
        notable_lua_data=notable_lua_data,
        map_name=map_name,
        next_map_name=next_map_name,
    )
    return header, reader


def read_hades2_save_header(path):
    """Read validated Hades II snapshot metadata without decoding Lua state."""

    header, _reader = _parse_header_prefix(Path(path).read_bytes())
    return header


def _parse_header_and_payload(data):
    header, reader = _parse_header_prefix(data)
    compressed = reader.sized_bytes("compressed luabins", max_size=_MAX_FILE_BYTES)
    if reader.remaining:
        raise HadesSaveFormatError("unexpected trailing SGB1 bytes")
    return header, compressed


def _encode_container(header, compressed):
    if header.game_version not in SUPPORTED_HADES2_SAVE_VERSIONS:
        raise UnsupportedHadesSaveVersionError(
            "unsupported Hades II save version 0x{:02x}".format(header.game_version)
        )
    if (
        header.game_version == HADES2_PATCH11_SAVE_VERSION
        and header.cosmetics_points is None
    ):
        raise HadesSaveFormatError("patch-11 Hades II save requires cosmetics points")

    body = _Writer()
    body.u16(header.game_version)
    body.u16(header.save_flags)
    body.u64(header.timestamp)
    body.string(header.location)
    body.u32(header.completed_runs)
    body.u32(header.accumulated_meta_points)
    body.u32(header.active_shrine_points)
    body.u32(header.meta_upgrade_level)
    if header.game_version == HADES2_PATCH11_SAVE_VERSION:
        body.u32(header.cosmetics_points)
    body.u8(header.easy_mode)
    body.u8(header.hard_mode)
    body.u32(len(header.notable_lua_data))
    for value in header.notable_lua_data:
        body.string(value)
    body.string(header.map_name)
    body.string(header.next_map_name)
    body.sized_bytes(compressed)

    output = bytearray(SGB1_MAGIC + b"\0\0\0\0")
    output += body.data
    struct.pack_into("<I", output, 4, zlib.adler32(output[8:]) & 0xFFFFFFFF)
    if len(output) > _MAX_FILE_BYTES:
        raise HadesSaveFormatError("encoded save file exceeds size limit")
    return bytes(output)


class Hades2SaveDocument:
    """Decoded Hades II save container and complete generic Lua state."""

    __slots__ = (
        "header",
        "lua_values",
        "_original_bytes",
        "_original_luabins",
        "_original_compressed",
    )

    def __init__(
        self,
        header,
        lua_values,
        *,
        original_bytes=None,
        original_luabins=None,
        original_compressed=None,
    ):
        self.header = header
        self.lua_values = list(lua_values)
        if not self.lua_values or not isinstance(self.lua_values[0], LuaTable):
            raise HadesSaveFormatError("Hades II save root must be a Lua table")
        self._original_bytes = original_bytes
        self._original_luabins = original_luabins
        self._original_compressed = original_compressed

    @property
    def lua_state(self):
        return self.lua_values[0]

    @classmethod
    def from_bytes(cls, data):
        raw = bytes(data)
        header, compressed = _parse_header_and_payload(raw)
        luabins = _decompress_lz4_block(compressed)
        values = _decode_luabins(luabins)
        return cls(
            header,
            values,
            original_bytes=raw,
            original_luabins=luabins,
            original_compressed=compressed,
        )

    @classmethod
    def load(cls, path):
        return cls.from_bytes(Path(path).read_bytes())

    def to_bytes(self):
        luabins = _encode_luabins(self.lua_values)
        if self._original_luabins is not None and luabins == self._original_luabins:
            compressed = self._original_compressed
        else:
            compressed = _literal_lz4_block(luabins)
        encoded = _encode_container(self.header, compressed)
        if self._original_bytes is not None and encoded == self._original_bytes:
            return self._original_bytes
        return encoded
