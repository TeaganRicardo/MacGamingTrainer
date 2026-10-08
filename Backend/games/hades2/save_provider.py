import struct
from pathlib import Path

from .localization import official_display_names
from .save_document import HadesSaveError, read_hades2_save_header


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


def resolve_active_profile_save(files):
    """Resolve the profile and source Hades is expected to load.

    A stale _Temp.sav is a recovery copy, not the active save. The validation
    marker must exist and be newer than the main save for Temp to win.
    """
    by_path = {row.relative_path: row.source_path for row in files}
    active = by_path.get("activeProfile")
    profile = _active_profile(active) if active is not None else None
    if profile is None:
        raise ValueError("Save Editor could not resolve the active Hades profile.")
    persistent = "{}.sav".format(profile)
    temporary = "{}_Temp.sav".format(profile)
    validation = "{}.v.sav".format(profile)
    if persistent not in by_path:
        raise ValueError("Save Editor active profile save is missing.")
    if temporary in by_path and validation in by_path:
        try:
            if (by_path[validation].stat().st_mtime_ns >
                    by_path[persistent].stat().st_mtime_ns):
                return profile, temporary
        except OSError as error:
            raise ValueError("Save Editor could not inspect the active-save marker.") from error
    return profile, persistent


class Hades2SaveProvider:
    def __init__(self, game_path=None):
        self.game_path = Path(game_path) if game_path is not None else None

    def resolve(self, roots, declared):
        del roots
        return [(row.root_id, row.relative_path) for row in declared]

    def describe_snapshot(self, files, created_at):
        by_path = {row.relative_path: row.source_path for row in files}
        try:
            _profile, relative = resolve_active_profile_save(files)
            header = read_hades2_save_header(by_path[relative])
        except (ValueError, OSError, HadesSaveError):
            return {'defaultName': None, 'nameDetails': []}
        time_label = created_at.replace('T', ' ')[:16]

        def presentation(language):
            names = official_display_names(
                {header.location},
                language,
                game_path=self.game_path,
            )
            location = names.get(header.location) or header.map_name or header.location
            if language == 'en':
                night = f'Night {header.completed_runs}'
                details = [
                    night,
                    location,
                    f'Grasp {header.meta_upgrade_level}',
                    f'Fear {header.active_shrine_points}',
                ]
            else:
                night = f'第{header.completed_runs}夜'
                details = [
                    night,
                    location,
                    f'悟性 {header.meta_upgrade_level}',
                    f'恐惧 {header.active_shrine_points}',
                ]
            return {
                'name': f'{time_label} · {night} · {location}',
                'details': details,
            }

        localized = {
            language: presentation(language)
            for language in ('zh-CN', 'en')
        }
        default = localized['zh-CN']
        return {
            'defaultName': default['name'],
            'nameDetails': default['details'],
            'localizedPresentation': localized,
        }
