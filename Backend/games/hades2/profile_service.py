import json
import re
import time
from pathlib import Path

from core.persistence import ProfileStore, normalize_shortcut_map

from .cheats import HADES2_CHEAT_CATALOG
from .error_presentation import Hades2ValueError
from .persistence import (
    PersistenceError,
    UnsupportedSchemaVersionError,
)
from .preferences import DESIRED_STATE_SCHEMA_VERSION, normalize_persisted_desired

PROFILE_SCHEMA_VERSION = 7
PROFILE_COMPATIBILITY_FLOOR = 3
_LEGACY_V3_SHORTCUT_MODIFIERS = (1 << 11) | (1 << 12)
_LEGACY_V3_DIGIT_KEYCODES = {
    0:29, 1:18, 2:19, 3:20, 4:21, 5:23, 6:22, 7:26, 8:28, 9:25,
}
_SHORTCUT_ACTION_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
_RETIRED_SHORTCUT_ACTIONS = HADES2_CHEAT_CATALOG.retired_ids | frozenset(HADES2_CHEAT_CATALOG.alias_map())


def _normalize_shortcuts(raw):
    """Validate current Profile shortcut chords without legacy coercion."""
    return normalize_shortcut_map(raw, retired_actions=_RETIRED_SHORTCUT_ACTIONS)


def _migrate_v3_shortcuts(raw):
    """Translate the released 0.1 integer digit layout to chord payloads."""
    if not isinstance(raw,dict):return {}
    migrated={}
    for action in sorted(raw):
        digit=raw.get(action)
        if not isinstance(action,str) or not _SHORTCUT_ACTION_RE.fullmatch(action):continue
        if type(digit) is not int or digit not in _LEGACY_V3_DIGIT_KEYCODES:continue
        migrated[action]={
            'keyCode':_LEGACY_V3_DIGIT_KEYCODES[digit],
            'modifiers':_LEGACY_V3_SHORTCUT_MODIFIERS,
            'keyLabel':str(digit),
        }
    return migrated


def _migrate_legacy_shortcut_identity(raw):
    """Rename legacy shortcut action IDs only while upgrading historical Profiles."""
    if not isinstance(raw,dict):return raw
    return HADES2_CHEAT_CATALOG.migrate_shortcut_payload(raw)


def _migrate_profile_payload(payload, version):
    """Upgrade supported historical envelopes in memory without rewriting them."""
    result=dict(payload)
    desired=result.get('desired')
    if version==3:
        result['desiredSchemaVersion']=3
        if 'shortcuts' in result:
            result['shortcuts']=_migrate_v3_shortcuts(result.get('shortcuts'))
    elif version==4:
        # Profile v4 spans the desired-state v3 -> v4 transition. v4 desired
        # documents always carry nextRoomRewardToken (including null); v3 did not.
        result['desiredSchemaVersion']=(
            4 if isinstance(desired,dict) and 'nextRoomRewardToken' in desired else 3
        )
    if version<PROFILE_SCHEMA_VERSION and 'shortcuts' in result:
        result['shortcuts']=_migrate_legacy_shortcut_identity(result.get('shortcuts'))
    result['schemaVersion']=PROFILE_SCHEMA_VERSION
    return result


def _invalid_name_error(reason):
    if reason == 'non_string':
        return Hades2ValueError('hades2.error.profileNameInvalid', 'Profile 名称无效。')
    if reason == 'separator':
        return Hades2ValueError('hades2.error.profileNameSeparator', 'Profile 名称不能包含路径分隔符。')
    return Hades2ValueError('hades2.error.profileNameLength', 'Profile 名称必须为 1–64 个可见字符。')


def _invalid_payload_input_error(reason):
    if reason == 'shortcuts':
        return Hades2ValueError('hades2.error.profileShortcutsInvalid', 'Profile shortcuts 字段无效。')
    return Hades2ValueError('hades2.error.profileDesiredInvalid', 'Profile desired 字段无效。')


class Hades2ProfileService:
    """Versioned Profile file I/O over Core ProfileStore."""
    def __init__(self, root):
        self.root = Path(root)
        self._store = ProfileStore(
            self.root,
            schema_version=PROFILE_SCHEMA_VERSION,
            compatibility_floor=PROFILE_COMPATIBILITY_FLOOR,
            payload_key='desired',
            normalize_payload=normalize_persisted_desired,
            prepare_save_payload=lambda payload: normalize_persisted_desired(payload, DESIRED_STATE_SCHEMA_VERSION),
            payload_version_key='desiredSchemaVersion',
            payload_schema_version=DESIRED_STATE_SCHEMA_VERSION,
            slug_length=24,
            serialize=lambda doc: json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',
            timestamp=lambda: time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            quarantine_corrupt=True,
            create_root_dir=True,
            migrate_envelope=_migrate_profile_payload,
            retired_shortcut_actions=_RETIRED_SHORTCUT_ACTIONS,
            include_shortcuts_in_list=True,
            invalid_name_error=_invalid_name_error,
            corrupt_error=lambda _reason, exc=None: Hades2ValueError('hades2.error.profileCorrupt', 'Profile 文件已损坏。'),
            not_found_error=lambda _name: Hades2ValueError('hades2.error.profileNotFound', '未找到该 Profile。'),
            newer_schema_error=lambda found, supported: UnsupportedSchemaVersionError('Profile', found, supported),
            older_schema_error=lambda found, supported: UnsupportedSchemaVersionError('Profile', found, supported),
            newer_payload_schema_error=lambda found, supported: UnsupportedSchemaVersionError(
                'Profile desired-state', found, supported
            ),
            invalid_payload_input_error=_invalid_payload_input_error,
            write_error=lambda error: error if isinstance(error, PersistenceError) else PersistenceError('无法安全写入本地配置。'),
        )

    @staticmethod
    def sanitize_name(name):
        return ProfileStore.sanitize_profile_name(name, _invalid_name_error)

    def path(self, name):
        return self._store.path(name)

    def list(self):
        return self._store.list()

    def save(self, name, preferences, shortcuts=None):
        profiles = self._store.save(name, preferences, shortcuts)
        return {'saved':True,'name':self.sanitize_name(name),'profiles':profiles}

    def load(self, name):
        return self._store.load(name)

    def delete(self, name):
        safe_name, profiles = self._store.delete(name)
        return {'deleted':True,'name':safe_name,'profiles':profiles}
