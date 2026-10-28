"""Supported native Hades I version-16 SGB1 documents.

Layout evidence and native bounds are recorded in docs/reference/hades/save_editor.md.
Lua nodes preserve physical entries and original double bytes, independently of
the semantic domains that edit them. No user path resolution happens here.
"""
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
import math
import struct
import zlib

from core import lz4_block


VERSION = 0x10
MAX_COMPRESSED = 0x2fc000
MAX_LUA_BYTES = 0x8f4000
MAX_HEADER = 0x4000
MAX_TABLE_DEPTH = 249


class SaveFormatError(ValueError):
    pass


class AmbiguousKeyError(ValueError):
    pass


class LuaNumber(float):
    def __new__(cls, raw):
        value = super().__new__(cls, struct.unpack('<d', raw)[0])
        value.raw = bytes(raw)
        return value


def same_key(left, right):
    if isinstance(left, LuaTable) or isinstance(right, LuaTable):
        return left is right
    if type(left) is bool or type(right) is bool:
        return type(left) is type(right) and left == right
    return left == right


def validate_key(key):
    if key is None or isinstance(key, (int, float)) and math.isnan(key):
        raise SaveFormatError('Lua table keys cannot be nil or NaN.')


class LuaTable(MutableMapping):
    def __init__(self, array_size=0, hash_size=0, entries=()):
        self.array_size, self.hash_size = array_size, hash_size
        self._entries = list(entries)
        if min(array_size, hash_size) < 0 or array_size + hash_size != len(self._entries):
            raise SaveFormatError('Lua table counts do not match its physical entries.')

    def entries(self):
        return tuple(self._entries)

    def _index(self, key):
        matches = [i for i, (candidate, _) in enumerate(self._entries) if same_key(candidate, key)]
        if len(matches) > 1:
            raise AmbiguousKeyError('Multiple physical entries own this Lua key; select an occurrence in Advanced.')
        return matches[0] if matches else None

    def __getitem__(self, key):
        index = self._index(key)
        if index is None:
            raise KeyError(key)
        return self._entries[index][1]

    def __setitem__(self, key, value):
        validate_key(key)
        index = self._index(key)
        if index is None:
            self._entries.append((key, value))
            self.hash_size += 1
        else:
            self._entries[index] = (self._entries[index][0], value)

    def __delitem__(self, key):
        index = self._index(key)
        if index is None:
            raise KeyError(key)
        self.remove(index)

    def replace(self, index, value):
        key, _ = self._entries[index]
        self._entries[index] = (key, value)

    def remove(self, index):
        del self._entries[index]
        if index < self.array_size:
            self.array_size -= 1
        else:
            self.hash_size -= 1

    def __iter__(self):
        return (key for key, _ in self._entries)

    def __len__(self):
        return len(self._entries)


class Reader:
    def __init__(self, data):
        self.data, self.pos = memoryview(data), 0

    @property
    def remaining(self):
        return len(self.data) - self.pos

    def take(self, size):
        if size < 0 or size > self.remaining:
            raise SaveFormatError('Truncated native save field.')
        start, self.pos = self.pos, self.pos + size
        return bytes(self.data[start:self.pos])

    def number(self, code):
        return struct.unpack('<' + code, self.take(struct.calcsize(code)))[0]

    def sized(self):
        return self.take(self.number('I'))

    def text(self):
        return self.sized().decode('utf-8', errors='surrogateescape')


def decode_lua(data):
    reader = Reader(data)

    def value(depth):
        tag = reader.take(1)
        if tag == b'-': return None
        if tag == b'0': return False
        if tag == b'1': return True
        if tag == b'N': return LuaNumber(reader.take(8))
        if tag == b'S': return reader.text()
        if tag != b'T':
            raise SaveFormatError('Unknown luabins type tag.')
        if depth > MAX_TABLE_DEPTH:
            raise SaveFormatError('Lua table exceeds the native nesting limit.')
        array, hashed = reader.number('I'), reader.number('i')
        total = array + hashed
        if array > 0x4000000 or hashed < 0 or hashed > 0x4000000 or total * 2 > reader.remaining:
            raise SaveFormatError('Invalid native luabins table counts.')
        entries = []
        for _ in range(total):
            key = value(depth + 1)
            validate_key(key)
            entries.append((key, value(depth + 1)))
        return LuaTable(array, hashed, entries)

    count = reader.number('B')
    if not 1 <= count <= 250:
        raise SaveFormatError('Native luabins requires 1 to 250 top-level values.')
    values = [value(0) for _ in range(count)]
    if reader.remaining:
        raise SaveFormatError('Unexpected bytes after native luabins values.')
    return values


def encode_lua(values):
    if not 1 <= len(values) <= 250:
        raise SaveFormatError('Native luabins requires 1 to 250 top-level values.')
    output = bytearray([len(values)])

    def value(node, depth):
        if node is None: output.extend(b'-')
        elif node is False: output.extend(b'0')
        elif node is True: output.extend(b'1')
        elif isinstance(node, (int, float)):
            output.extend(b'N')
            output.extend(node.raw if isinstance(node, LuaNumber) else struct.pack('<d', float(node)))
        elif isinstance(node, str):
            raw = node.encode('utf-8', errors='surrogateescape')
            output.extend(b'S' + struct.pack('<I', len(raw)) + raw)
        elif isinstance(node, LuaTable):
            if depth > MAX_TABLE_DEPTH:
                raise SaveFormatError('Lua table exceeds the native nesting limit.')
            if node.array_size + node.hash_size != len(node):
                raise SaveFormatError('Lua table counts do not match its entries.')
            output.extend(b'T' + struct.pack('<Ii', node.array_size, node.hash_size))
            for key, item in node.entries():
                validate_key(key)
                value(key, depth + 1)
                value(item, depth + 1)
        else:
            raise SaveFormatError('Unsupported Lua value type: ' + type(node).__name__)
        if len(output) >= MAX_LUA_BYTES:
            raise SaveFormatError('Lua bytes exceed the supported native buffer.')

    for node in values:
        value(node, 0)
    return bytes(output)


@dataclass
class HadesSaveHeader:
    timestamp: int = 0
    location: str = ''
    completed_runs: int = 0
    accumulated_meta_points: int = 0
    active_shrine_points: int = 0
    easy_mode: int = 0
    hard_mode: int = 0
    notable_lua_data: tuple = ()
    map_name: str = ''
    next_map_name: str = ''


class HadesSaveDocument:
    def __init__(self, header, lua_values, *, original_lua=None, original_compressed=None):
        if not lua_values or not isinstance(lua_values[0], LuaTable):
            raise SaveFormatError('Native Hades Save must begin with a root Lua table.')
        self.header, self.lua_values = header, list(lua_values)
        self._original_lua, self._original_compressed = original_lua, original_compressed

    @property
    def lua_state(self):
        return self.lua_values[0]

    @classmethod
    def from_bytes(cls, data):
        if len(data) > MAX_HEADER + MAX_COMPRESSED + 4:
            raise SaveFormatError('Save exceeds native header/compressed bounds.')
        reader = Reader(data)
        if reader.take(4) != b'SGB1':
            raise SaveFormatError('Native Hades Save magic is missing.')
        if reader.number('I') != zlib.adler32(data[8:]) & 0xffffffff:
            raise SaveFormatError('Native Hades Save checksum does not match.')
        if reader.number('I') != VERSION:
            raise SaveFormatError('This Hades Save version is unsupported; version 16 is required.')
        header = HadesSaveHeader(reader.number('Q'), reader.text(), reader.number('I'),
            reader.number('I'), reader.number('I'), reader.number('B'), reader.number('B'))
        count = reader.number('I')
        if count * 4 > reader.remaining:
            raise SaveFormatError('Invalid native notable-string count.')
        header.notable_lua_data = tuple(reader.text() for _ in range(count))
        header.map_name, header.next_map_name = reader.text(), reader.text()
        if reader.pos >= MAX_HEADER:
            raise SaveFormatError('Save header exceeds the native bound.')
        compressed = reader.sized()
        if reader.remaining or not 1 <= len(compressed) <= MAX_COMPRESSED:
            raise SaveFormatError('Invalid native compressed field or trailing bytes.')
        try:
            lua = lz4_block.decompress(compressed, MAX_LUA_BYTES - 1)
        except lz4_block.LZ4BlockError as error:
            raise SaveFormatError(str(error)) from error
        return cls(header, decode_lua(lua), original_lua=lua, original_compressed=compressed)

    @classmethod
    def load(cls, path):
        return cls.from_bytes(Path(path).read_bytes())

    def to_bytes(self):
        lua = encode_lua(self.lua_values)
        compressed = (self._original_compressed if lua == self._original_lua else
                      lz4_block.compress(lua, MAX_LUA_BYTES - 1))
        if not 1 <= len(compressed) <= MAX_COMPRESSED:
            raise SaveFormatError('Edited save exceeds the native compressed bound.')
        body = bytearray(struct.pack('<IQ', VERSION, self.header.timestamp))

        def text(value):
            raw = value.encode('utf-8', errors='surrogateescape')
            body.extend(struct.pack('<I', len(raw)) + raw)

        text(self.header.location)
        try:
            body.extend(struct.pack('<IIIBBI', self.header.completed_runs,
                self.header.accumulated_meta_points, self.header.active_shrine_points,
                self.header.easy_mode, self.header.hard_mode, len(self.header.notable_lua_data)))
        except struct.error as error:
            raise SaveFormatError('Edited native header value is outside its encoded integer range.') from error
        for item in self.header.notable_lua_data: text(item)
        text(self.header.map_name)
        text(self.header.next_map_name)
        if len(body) + 8 >= MAX_HEADER:
            raise SaveFormatError('Edited save header exceeds the native bound.')
        body.extend(struct.pack('<I', len(compressed)) + compressed)
        return b'SGB1' + struct.pack('<I', zlib.adler32(body) & 0xffffffff) + body

    def clone(self):
        return self.from_bytes(self.to_bytes())
