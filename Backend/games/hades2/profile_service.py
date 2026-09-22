import hashlib
import json
import logging
import re
import time

from .persistence import atomic_write_text, quarantine_corrupt_file, UnsupportedSchemaVersionError
from .preferences import DESIRED_STATE_SCHEMA_VERSION, normalize_persisted_desired


PROFILE_SCHEMA_VERSION = 5
PROFILE_COMPATIBILITY_FLOOR = 3
_PROFILE_FIELDS = frozenset((
    'schemaVersion','desiredSchemaVersion','name','updatedAt','desired','shortcuts',
))
_SHORTCUT_MODIFIER_MASK = (1 << 8) | (1 << 9) | (1 << 11) | (1 << 12)
_LEGACY_V3_SHORTCUT_MODIFIERS = (1 << 11) | (1 << 12)
_LEGACY_V3_DIGIT_KEYCODES = {
    0:29, 1:18, 2:19, 3:20, 4:21, 5:23, 6:22, 7:26, 8:28, 9:25,
}

_SHORTCUT_ACTION_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')


def _profile_schema_version(payload):
    if 'schemaVersion' not in payload:return 0
    value=payload['schemaVersion']
    if type(value) is not int or value<0:raise ValueError('Profile schemaVersion 无效。')
    return value


def _profile_desired_schema_version(payload):
    value=payload.get('desiredSchemaVersion')
    if type(value) is not int or value<0:raise ValueError('Profile desiredSchemaVersion 无效。')
    return value


def _normalize_shortcuts(raw):
    """Validate current Profile shortcut chords without legacy coercion."""
    if not isinstance(raw,dict):return {}
    result={}
    actions=sorted(
        action for action in raw
        if isinstance(action,str) and _SHORTCUT_ACTION_RE.fullmatch(action)
    )
    for action in actions:
        row=raw.get(action)
        if not isinstance(row,dict) or set(row)!= {'keyCode','modifiers','keyLabel'}:continue
        key_code=row.get('keyCode');modifiers=row.get('modifiers');label=row.get('keyLabel')
        if type(key_code) is not int or not 0<=key_code<=65535:continue
        if type(modifiers) is not int or not 0<=modifiers<=0xFFFFFFFF or modifiers & ~_SHORTCUT_MODIFIER_MASK:continue
        if not isinstance(label,str) or not label or len(label)>16 or any(ord(ch)<32 for ch in label):continue
        result[action]={'keyCode':key_code,'modifiers':modifiers,'keyLabel':label}
    return result


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
    result['schemaVersion']=PROFILE_SCHEMA_VERSION
    return result


class Hades2ProfileService:
    """Versioned Profile file I/O. Runtime replay remains in the adapter."""
    def __init__(self, root):
        self.root=root
        self.root.mkdir(parents=True,exist_ok=True)

    @staticmethod
    def sanitize_name(name):
        if not isinstance(name,str):raise ValueError('Profile 名称无效。')
        name=name.strip()
        if not name or len(name)>64 or any(ord(ch)<32 for ch in name):raise ValueError('Profile 名称必须为 1–64 个可见字符。')
        if '/' in name or '\\' in name:raise ValueError('Profile 名称不能包含路径分隔符。')
        return name

    def path(self,name):
        safe=self.sanitize_name(name)
        slug=hashlib.sha256(safe.encode('utf-8')).hexdigest()[:24]
        return self.root/(slug+'.json')

    @staticmethod
    def _quarantine(path, message):
        quarantined=quarantine_corrupt_file(path)
        logging.error('%s %s quarantined=%s',message,path,quarantined)
        return quarantined

    @classmethod
    def _read_payload(cls,path,quarantine=True):
        try:
            text=path.read_text(encoding='utf-8')
        except UnicodeError:
            if quarantine:cls._quarantine(path,'Unreadable profile')
            raise ValueError('Profile 文件已损坏。')
        except OSError:
            raise
        try:
            payload=json.loads(text)
        except json.JSONDecodeError:
            if quarantine:cls._quarantine(path,'Invalid JSON profile')
            raise ValueError('Profile 文件已损坏。')
        if not isinstance(payload,dict):
            if quarantine:cls._quarantine(path,'Invalid profile shape')
            raise ValueError('Profile 文件已损坏。')
        return payload

    @classmethod
    def _validate_schema(cls,path,payload,quarantine=True):
        try:
            version=_profile_schema_version(payload)
        except ValueError:
            if quarantine:cls._quarantine(path,'Invalid profile schema version')
            raise ValueError('Profile 文件已损坏。')
        if version<PROFILE_COMPATIBILITY_FLOOR or version>PROFILE_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError('Profile',version,PROFILE_SCHEMA_VERSION)
        return version

    def _validate_envelope(self,path,payload,quarantine=True):
        version=self._validate_schema(path,payload,quarantine=quarantine)
        document=_migrate_profile_payload(payload,version) if version<PROFILE_SCHEMA_VERSION else dict(payload)
        try:
            unknown=set(document)-_PROFILE_FIELDS
            if unknown:raise ValueError('Profile 包含当前 schema 未定义的顶层字段。')

            raw_name=document.get('name')
            name=self.sanitize_name(raw_name)
            if raw_name!=name:raise ValueError('Profile 名称未规范化。')
            if self.path(name)!=path:raise ValueError('Profile 名称与文件标识不一致。')

            desired=document.get('desired')
            if not isinstance(desired,dict):raise ValueError('Profile desired 字段无效。')
            desired_schema_version=_profile_desired_schema_version(document)
            if desired_schema_version>DESIRED_STATE_SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    'Profile desired-state',desired_schema_version,DESIRED_STATE_SCHEMA_VERSION
                )
            desired=normalize_persisted_desired(desired,desired_schema_version)

            updated_at=document.get('updatedAt','')
            if not isinstance(updated_at,str) or len(updated_at)>128 or any(ord(ch)<32 for ch in updated_at):
                raise ValueError('Profile updatedAt 字段无效。')
            if not updated_at:
                raise ValueError('Profile updatedAt 字段缺失。')

            if 'shortcuts' in document and not isinstance(document['shortcuts'],dict):
                raise ValueError('Profile shortcuts 字段无效。')
        except UnsupportedSchemaVersionError:
            raise
        except ValueError:
            if quarantine:self._quarantine(path,'Invalid profile envelope')
            raise ValueError('Profile 文件已损坏。')
        return {
            'name':name,
            'updatedAt':updated_at,
            'desiredSchemaVersion':desired_schema_version,
            'desired':desired,
            'shortcuts':_normalize_shortcuts(document.get('shortcuts')),
        }

    def list(self):
        rows=[]
        for path in sorted(self.root.glob('*.json')):
            try:
                data=self._read_payload(path)
                envelope=self._validate_envelope(path,data)
                rows.append({'name':envelope['name'],'updatedAt':envelope['updatedAt'],'shortcuts':envelope['shortcuts']})
            except UnsupportedSchemaVersionError:
                logging.warning('Ignoring unsupported Profile schema without modifying it: %s',path)
            except ValueError:logging.exception('Ignoring corrupt profile %s',path)
            except OSError:logging.exception('Unable to read profile %s',path)
        rows.sort(key=lambda item:item['name'].casefold())
        return rows

    @classmethod
    def _protect_future_overwrite(cls,path):
        if not path.is_file():return
        try:
            payload=cls._read_payload(path,quarantine=False)
            version=_profile_schema_version(payload)
        except (ValueError,OSError):
            return
        if version>PROFILE_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError('Profile',version,PROFILE_SCHEMA_VERSION)
        if version==PROFILE_SCHEMA_VERSION:
            desired_version=payload.get('desiredSchemaVersion')
            if type(desired_version) is int and desired_version>DESIRED_STATE_SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    'Profile desired-state',desired_version,DESIRED_STATE_SCHEMA_VERSION
                )

    def save(self,name,preferences,shortcuts=None):
        name=self.sanitize_name(name)
        if not isinstance(preferences,dict):raise ValueError('Profile desired 字段无效。')
        if shortcuts is not None and not isinstance(shortcuts,dict):raise ValueError('Profile shortcuts 字段无效。')
        path=self.path(name)
        self._protect_future_overwrite(path)
        desired=normalize_persisted_desired(preferences,DESIRED_STATE_SCHEMA_VERSION)
        payload={
            'schemaVersion':PROFILE_SCHEMA_VERSION,
            'desiredSchemaVersion':DESIRED_STATE_SCHEMA_VERSION,
            'name':name,
            'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'desired':desired,
        }
        if isinstance(shortcuts,dict):
            payload['shortcuts']=_normalize_shortcuts(shortcuts)
        atomic_write_text(path,json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
        return {'saved':True,'name':name,'profiles':self.list()}

    def load(self,name):
        path=self.path(name)
        if not path.is_file():raise ValueError('未找到该 Profile。')
        payload=self._read_payload(path)
        envelope=self._validate_envelope(path,payload)
        return {
            'name':envelope['name'],
            'desired':envelope['desired'],
            'shortcuts':envelope['shortcuts'],
        }

    def delete(self,name):
        path=self.path(name)
        if not path.is_file():raise ValueError('未找到该 Profile。')
        # Deletion is an explicit destructive user action and does not need to
        # understand the file schema.
        path.unlink()
        return {'deleted':True,'name':self.sanitize_name(name),'profiles':self.list()}
