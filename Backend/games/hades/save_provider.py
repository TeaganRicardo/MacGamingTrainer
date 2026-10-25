"""Hades I save membership and profile naming over Core's save transactions."""
import re
import struct


class HadesSaveProvider:
    def resolve(self, roots, declared):
        return [(row.root_id, row.relative_path) for row in declared]

    def describe_snapshot(self, files, created_at):
        active = next((row.source_path for row in files if row.relative_path == 'activeProfile'), None)
        if active is None:
            return {'defaultName': None, 'nameDetails': []}
        try:
            with active.open('rb') as source:
                raw = source.read(72)
        except OSError:
            return {'defaultName': None, 'nameDetails': []}
        if len(raw) < 8 or raw[:4] != b'SGB1':
            return {'defaultName': None, 'nameDetails': []}
        size = struct.unpack_from('<I', raw, 4)[0]
        if not 1 <= size <= 64 or len(raw) < 8 + size:
            return {'defaultName': None, 'nameDetails': []}
        match = re.fullmatch(rb'Profile([0-9]+)', raw[8:8 + size])
        if match is None:
            return {'defaultName': None, 'nameDetails': []}
        number = match[1].decode('ascii')
        timestamp = created_at.replace('T', ' ')[:16]
        labels = {'zh-CN': f'存档 {number}', 'en': f'Save Slot {number}'}
        localized = {language: {'name': f'{timestamp} · {label}', 'details': [label]}
                     for language, label in labels.items()}
        return {'defaultName': localized['zh-CN']['name'],
                'nameDetails': localized['zh-CN']['details'],
                'localizedPresentation': localized}
