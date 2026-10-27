"""Typed wire values and physical luabins occurrence paths for Hades I."""
import base64
import math
import struct

from .save_document import LuaTable, LuaNumber, SaveFormatError, MAX_TABLE_DEPTH, encode_lua, validate_key


def typed(value):
    if value is None: return {'luaType': 'nil'}
    if type(value) is bool: return {'luaType': 'boolean', 'value': value}
    if isinstance(value, (int, float)):
        raw = value.raw if isinstance(value, LuaNumber) else struct.pack('<d', float(value))
        if not math.isfinite(value) or value == 0 and math.copysign(1, value) < 0:
            return {'luaType': 'number', 'encoding': 'ieee754', 'value': raw.hex()}
        return {'luaType': 'number', 'value': float(value)}
    if isinstance(value, str):
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            return {'luaType': 'string', 'encoding': 'base64',
                    'value': base64.b64encode(value.encode('utf-8', errors='surrogateescape')).decode('ascii')}
        return {'luaType': 'string', 'value': value}
    if isinstance(value, LuaTable):
        return {'luaType': 'table', 'arraySize': value.array_size, 'hashSize': value.hash_size,
                'entries': [{'key': typed(key), 'value': typed(item)} for key, item in value.entries()]}
    raise SaveFormatError('Unsupported typed Lua value.')


def from_typed(node, depth=0):
    if not isinstance(node, dict) or depth > MAX_TABLE_DEPTH + 1:
        raise ValueError('Invalid or excessively nested typed Lua value.')
    kind, encoding = node.get('luaType'), node.get('encoding')
    value = node.get('value')
    if kind == 'nil' and encoding is None:
        return None
    if kind == 'boolean' and type(value) is bool and encoding is None:
        return value
    if kind == 'number':
        if encoding == 'ieee754':
            if not isinstance(value, str) or len(value) != 16:
                raise ValueError('An IEEE-754 value requires exactly eight hexadecimal bytes.')
            try:
                return LuaNumber(bytes.fromhex(value))
            except (ValueError, struct.error) as error:
                raise ValueError('Invalid IEEE-754 bytes.') from error
        if encoding is None and type(value) in (int, float):
            try:
                if math.isfinite(value) and (type(value) is not int or int(float(value)) == value):
                    return float(value)
            except OverflowError:
                pass
        raise ValueError('Enter an exactly representable finite number, or explicit IEEE-754 bytes.')
    if kind == 'string' and isinstance(value, str):
        if encoding == 'base64':
            try:
                return base64.b64decode(value, validate=True).decode('utf-8', errors='surrogateescape')
            except ValueError as error:
                raise ValueError('Invalid Lua byte-string base64.') from error
        if encoding is None:
            value.encode('utf-8', errors='surrogateescape')
            return value
    if kind == 'table' and encoding is None:
        entries = node.get('entries')
        array = node.get('arraySize', 0)
        hashed = node.get('hashSize', len(entries) - array if isinstance(entries, list) and type(array) is int else -1)
        if (not isinstance(entries, list) or type(array) is not int or type(hashed) is not int
                or min(array, hashed) < 0 or array + hashed != len(entries)):
            raise ValueError('Typed Lua tables require ordered entries and matching allocation counts.')
        result = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'key', 'value'}:
                raise ValueError('A typed Lua entry requires key and value nodes.')
            key = from_typed(entry['key'], depth + 1)
            validate_key(key)
            result.append((key, from_typed(entry['value'], depth + 1)))
        return LuaTable(array, hashed, result)
    raise ValueError('Value does not match its declared Lua type.')


def display(value):
    if isinstance(value, LuaTable): return str(len(value)) + ' entries'
    node = typed(value)
    if node.get('encoding') == 'base64': return 'base64:' + node['value']
    if node.get('encoding') == 'ieee754': return 'IEEE754:' + node['value']
    if value is None: return 'nil'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, (int, float)): return format(value, '.15g')
    return value


def identifier(path):
    return 'p:' + '/'.join(str(index) for index in path)


def parse_id(value):
    if not isinstance(value, str) or not value.startswith('p:'):
        raise ValueError('Invalid physical Lua entry identity.')
    parts = value[2:].split('/')
    if not parts or len(parts) > MAX_TABLE_DEPTH + 2 or any(not part.isdigit() for part in parts):
        raise ValueError('Invalid physical Lua occurrence path.')
    return tuple(int(part) for part in parts)


def resolve(document, path):
    try:
        value = document.lua_values[path[0]]
        for token in path[1:]:
            if not isinstance(value, LuaTable):
                raise ValueError('The Lua path crosses a scalar value.')
            value = value.entries()[token // 2][token % 2]
        return value
    except IndexError as error:
        raise ValueError('The physical Lua entry no longer exists.') from error


def mutate(document, path, operation, node=None):
    if operation == 'append':
        owner = resolve(document, path)
        if not isinstance(owner, LuaTable) or not isinstance(node, dict) or set(node) != {'key', 'value'}:
            raise ValueError('Adding a field requires a table and typed key/value nodes.')
        key, value = from_typed(node['key']), from_typed(node['value'])
        validate_key(key)
        owner._entries.append((key, value))
        owner.hash_size += 1
        return
    if operation not in ('set', 'unset'):
        raise ValueError('Unsupported Lua mutation operation.')
    if len(path) == 1:
        if operation == 'unset':
            if path[0] == 0:
                raise ValueError('Replace the main root table instead of deleting it.')
            del document.lua_values[path[0]]
        else:
            document.lua_values[path[0]] = from_typed(node)
        return
    owner = resolve(document, path[:-1])
    if not isinstance(owner, LuaTable):
        raise ValueError('A physical entry requires a table owner.')
    token = path[-1]
    index, part = token // 2, token % 2
    if operation == 'unset':
        owner.remove(index)
    elif part == 1:
        owner.replace(index, from_typed(node))
    else:
        key = from_typed(node)
        validate_key(key)
        _, value = owner.entries()[index]
        owner._entries[index] = (key, value)


def equal(left, right):
    return encode_lua([left]) == encode_lua([right])
