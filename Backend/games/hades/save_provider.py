"""Hades I save membership and profile naming over Core's save transactions."""
import re
import struct
from pathlib import Path


_PROFILE_FILE = re.compile(r'^(Profile[0-9]+)((?:_[A-Za-z0-9_-]+|[.][A-Za-z0-9_-]+)?)\.sav$')


def profile_file_identity(relative_path):
    match = _PROFILE_FILE.fullmatch(Path(relative_path).name) if isinstance(relative_path, str) else None
    return (match[1], match[2]) if match is not None and match[2] != '.v' else None


def editor_files(files):
    rows = []
    for item in files:
        identity = profile_file_identity(item.relative_path)
        if identity is not None:
            profile, variant = identity
            rows.append({'rootId': item.root_id, 'relativePath': item.relative_path,
                         'profile': profile, 'variant': variant})
    return rows


def active_profile_bytes(raw):
    if len(raw) < 8 or raw[:4] != b'SGB1':
        return None
    size = struct.unpack_from('<I', raw, 4)[0]
    if not 1 <= size <= 64 or len(raw) < 8 + size:
        return None
    match = re.fullmatch(rb'Profile([0-9]+)', raw[8:8 + size])
    return match[0].decode('ascii') if match is not None else None


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
        profile = active_profile_bytes(raw)
        if profile is None:
            return {'defaultName': None, 'nameDetails': []}
        number = profile[len('Profile'):]
        timestamp = created_at.replace('T', ' ')[:16]
        labels = {'zh-CN': f'存档 {number}', 'en': f'Save Slot {number}'}
        localized = {language: {'name': f'{timestamp} · {label}', 'details': [label]}
                     for language, label in labels.items()}
        return {'defaultName': localized['zh-CN']['name'],
                'nameDetails': localized['zh-CN']['details'],
                'localizedPresentation': localized}
