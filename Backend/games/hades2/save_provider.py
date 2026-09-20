from dataclasses import dataclass
from pathlib import Path
import struct

from .localization import official_display_names


@dataclass(frozen=True)
class _SaveHeader:
    timestamp: int
    location: str
    runs: int
    fear: int
    grasp: int
    current_map: str


class _Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0

    def take(self, size):
        end = self.pos + size
        if size < 0 or end > len(self.data):
            raise ValueError('truncated SGB1 header')
        value = self.data[self.pos:end]
        self.pos = end
        return value

    def u16(self):
        return struct.unpack('<H', self.take(2))[0]

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def u64(self):
        return struct.unpack('<Q', self.take(8))[0]

    def string(self):
        size = self.u32()
        if size > 4096:
            raise ValueError('SGB1 header string is too large')
        return bytes(self.take(size)).decode('utf-8', errors='strict')


def _active_profile(path):
    try:
        data = path.read_bytes()
        if len(data) < 8 or data[:4] != b'SGB1':
            return None
        size = struct.unpack_from('<I', data, 4)[0]
        if size < 1 or size > 64 or 8 + size > len(data):
            return None
        value = data[8:8 + size].decode('utf-8', errors='strict')
    except (OSError, UnicodeDecodeError, struct.error):
        return None
    if not value.startswith('Profile') or not value[7:].isdigit():
        return None
    return value


def _save_header(path):
    try:
        reader = _Reader(path.read_bytes())
        if bytes(reader.take(4)) != b'SGB1':
            return None
        reader.take(4)  # checksum
        version = reader.u16()
        reader.take(2)  # save flags
        timestamp = reader.u64()
        location = reader.string()
        runs = reader.u32()
        reader.u32()  # accumulated meta points
        fear = reader.u32()
        grasp = reader.u32() if version >= 17 else 0
        if version >= 18:
            reader.u32()  # cosmetics points
        reader.take(2)  # easy / hard mode
        for _ in range(reader.u32()):
            reader.string()
        current_map = reader.string()
        reader.string()  # next map
        return _SaveHeader(timestamp, location, runs, fear, grasp, current_map)
    except (OSError, UnicodeDecodeError, ValueError, struct.error):
        return None


class Hades2SaveProvider:
    def __init__(self, game_path=None):
        self.game_path = Path(game_path) if game_path is not None else None

    def resolve(self, roots, declared):
        del roots
        return [(row.root_id, row.relative_path) for row in declared]

    def describe_snapshot(self, files, created_at):
        by_path = {row.relative_path: row.source_path for row in files}
        active_path = by_path.get('activeProfile')
        profile = _active_profile(active_path) if active_path is not None else None
        if profile is None:
            return {'defaultName': None, 'nameDetails': []}

        headers = []
        for relative in (f'{profile}.sav', f'{profile}_Temp.sav'):
            path = by_path.get(relative)
            if path is None:
                continue
            header = _save_header(path)
            if header is not None:
                headers.append(header)
        if not headers:
            return {'defaultName': None, 'nameDetails': []}

        header = max(headers, key=lambda item: item.timestamp)
        names = official_display_names(
            {header.location},
            'zh-CN',
            game_path=self.game_path,
        )
        location = names.get(header.location) or header.current_map or header.location
        time_label = created_at.replace('T', ' ')[:16]
        night = f'第{header.runs}夜'
        details = [night, location, f'悟性 {header.grasp}', f'恐惧 {header.fear}']
        return {
            'defaultName': f'{time_label} · {night} · {location}',
            'nameDetails': details,
        }
