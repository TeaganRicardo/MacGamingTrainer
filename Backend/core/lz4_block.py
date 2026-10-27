"""Bounded raw LZ4 block encoding and decoding.

Container owners supply their native byte bounds.
"""
import struct


class LZ4BlockError(ValueError):
    pass


def decompress(data, max_output_bytes):
    """Decode one raw LZ4 block with strict bounds and no external runtime."""

    source = memoryview(data)
    output = bytearray()
    pos = 0

    def read_extension(label):
        nonlocal pos
        total = 0
        while True:
            if pos >= len(source):
                raise LZ4BlockError("truncated LZ4 {} extension".format(label))
            value = source[pos]
            pos += 1
            total += value
            if value != 255:
                return total

    def ensure_output(extra):
        if extra < 0 or len(output) + extra > max_output_bytes:
            raise LZ4BlockError("decompressed save exceeds size limit")

    while pos < len(source):
        token = source[pos]
        pos += 1
        literal_length = token >> 4
        match_length = token & 0x0F

        if literal_length == 15:
            literal_length += read_extension("literal length")
        if literal_length > len(source) - pos:
            raise LZ4BlockError("truncated LZ4 literal run")
        ensure_output(literal_length)
        output += source[pos:pos + literal_length]
        pos += literal_length

        if pos == len(source):
            break
        if len(source) - pos < 2:
            raise LZ4BlockError("truncated LZ4 match offset")

        offset = source[pos] | (source[pos + 1] << 8)
        pos += 2
        if offset == 0 or offset > len(output):
            raise LZ4BlockError("invalid LZ4 match offset")

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


def compress(payload, max_input_bytes):
    """Encode one standards-compatible raw LZ4 block without a runtime dependency.

    A fixed-size hash table provides ordinary LZ4 greedy matching while keeping
    memory bounded for the caller-supplied input limit. The encoder deliberately
    preserves the block-format end constraints (last five bytes literals; final
    match begins at least twelve bytes before the end) used by reference LZ4
    decoders.
    """

    if len(payload) > max_input_bytes:
        raise LZ4BlockError("luabins payload exceeds size limit")

    output = bytearray()
    size = len(payload)

    def write_extension(length):
        while length >= 255:
            output.append(255)
            length -= 255
        output.append(length)

    def emit(anchor, match_start, match_length=0, offset=0):
        literal_length = match_start - anchor
        match_code = match_length - 4 if match_length else 0
        token = (min(literal_length, 15) << 4) | min(match_code, 15)
        output.append(token)
        if literal_length >= 15:
            write_extension(literal_length - 15)
        output.extend(payload[anchor:match_start])
        if not match_length:
            return
        output.extend(struct.pack("<H", offset))
        if match_code >= 15:
            write_extension(match_code - 15)

    if size < 13:
        emit(0, size)
        return bytes(output)

    last = [-1] * 65536

    def hash_at(position):
        value = int.from_bytes(payload[position:position + 4], "little")
        return ((value * 2654435761) & 0xFFFFFFFF) >> 16

    anchor = 0
    pos = 0
    match_limit = size - 5
    search_limit = size - 12

    while pos <= search_limit:
        slot = hash_at(pos)
        candidate = last[slot]
        last[slot] = pos
        if (
            candidate < 0
            or pos - candidate > 0xFFFF
            or payload[candidate:candidate + 4] != payload[pos:pos + 4]
        ):
            pos += 1
            continue

        match_length = 4
        max_match = match_limit - pos
        while (
            match_length < max_match
            and payload[candidate + match_length] == payload[pos + match_length]
        ):
            match_length += 1

        emit(anchor, pos, match_length, pos - candidate)
        end = pos + match_length
        update = pos + 1
        while update + 4 <= end:
            last[hash_at(update)] = update
            update += 1
        pos = end
        anchor = end

    emit(anchor, size)
    return bytes(output)
