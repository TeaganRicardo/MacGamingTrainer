import hashlib
import json
import logging
import time

from .persistence import atomic_write_text, quarantine_corrupt_file, UnsupportedSchemaVersionError


PROFILE_SCHEMA_VERSION = 3
_PROFILE_FIELDS = frozenset(('schemaVersion','name','updatedAt','desired','shortcuts'))


_SHORTCUT_DEFAULTS = {
    'godMode': 1,
    'infiniteHealth': 2,
    'infiniteMana': 3,
    'instantCastCooldown': 4,
    'hexAlwaysReady': 5,
    'infiniteAmmo': 6,
    'damageEnabled': 7,
    'autoMiniGames': 8,
    'moneyMultiplierEnabled': 9,
    'disableAll': 0,
}


def _profile_schema_version(payload):
    if 'schemaVersion' not in payload:return 0
    value=payload['schemaVersion']
    if type(value) is not int or value<0:raise ValueError('Profile schemaVersion 无效。')
    return value


def _normalize_shortcuts(raw):
    """Return a deterministic unique shortcut layout for profile payloads.

    Shortcut assignments are normalized to the same unique 0-9 swap semantics
    as the Swift shortcut editor.
    """
    if not isinstance(raw,dict):return {}
    valid={key:value for key,value in raw.items()
           if key in _SHORTCUT_DEFAULTS and type(value) is int and 0<=value<=9}
    if not valid:return {}
    digits=dict(_SHORTCUT_DEFAULTS)
    for action in _SHORTCUT_DEFAULTS:
        if action not in valid:continue
        wanted=valid[action]
        current=digits[action]
        if current==wanted:continue
        other=next((key for key,value in digits.items() if value==wanted),None)
        if other is not None:digits[other]=current
        digits[action]=wanted
    return digits


class Hades2ProfileService:
    """Profile file I/O only. Runtime replay remains in the adapter."""
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
        if version!=PROFILE_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError('Profile',version,PROFILE_SCHEMA_VERSION)
        return version

    def _validate_envelope(self,path,payload,quarantine=True):
        version=self._validate_schema(path,payload,quarantine=quarantine)
        try:
            unknown=set(payload)-_PROFILE_FIELDS
            if unknown:raise ValueError('Profile 包含当前 schema 未定义的顶层字段。')

            raw_name=payload.get('name')
            name=self.sanitize_name(raw_name)
            if raw_name!=name:raise ValueError('Profile 名称未规范化。')
            if self.path(name)!=path:raise ValueError('Profile 名称与文件标识不一致。')

            desired=payload.get('desired')
            if not isinstance(desired,dict):raise ValueError('Profile desired 字段无效。')

            updated_at=payload.get('updatedAt','')
            if not isinstance(updated_at,str) or len(updated_at)>128 or any(ord(ch)<32 for ch in updated_at):
                raise ValueError('Profile updatedAt 字段无效。')
            if not updated_at:
                raise ValueError('Profile updatedAt 字段缺失。')

            if 'shortcuts' in payload and not isinstance(payload['shortcuts'],dict):
                raise ValueError('Profile shortcuts 字段无效。')
        except ValueError:
            if quarantine:self._quarantine(path,'Invalid profile envelope')
            raise ValueError('Profile 文件已损坏。')
        return {
            'name':name,
            'updatedAt':updated_at,
            'desired':desired,
            'shortcuts':_normalize_shortcuts(payload.get('shortcuts')),
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

    def save(self,name,preferences,shortcuts=None):
        name=self.sanitize_name(name)
        if not isinstance(preferences,dict):raise ValueError('Profile desired 字段无效。')
        if shortcuts is not None and not isinstance(shortcuts,dict):raise ValueError('Profile shortcuts 字段无效。')
        path=self.path(name)
        payload={
            'schemaVersion':PROFILE_SCHEMA_VERSION,
            'name':name,
            'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'desired':preferences,
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
        return {'name':envelope['name'],'desired':envelope['desired'],'shortcuts':envelope['shortcuts']}

    def delete(self,name):
        path=self.path(name)
        if not path.is_file():raise ValueError('未找到该 Profile。')
        # Deletion is an explicit destructive user action and does not need to
        # understand the file schema.
        path.unlink()
        return {'deleted':True,'name':self.sanitize_name(name),'profiles':self.list()}
