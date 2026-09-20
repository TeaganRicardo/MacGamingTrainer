import json
import logging
import math

from .persistence import atomic_write_text, quarantine_corrupt_file, PersistenceError, UnsupportedSchemaVersionError
from .schema import MULTIPLIERS, STAT_RULES, TOGGLES


NEXT_ROOM_REWARD_MIGRATIONS = {
    # Pre-1.0 / early-access reward identifiers retained by older trainer profiles.
    'RoomRewardMoney': 'RoomMoneyDrop',
    'RoomRewardMetaPoint': 'MetaCardPointsCommonDrop',
    'RoomRewardPsyche': 'MemPointsCommonDrop',
    'RoomRewardMaxHealth': 'MaxHealthDrop',
    'RoomRewardPom': 'StackUpgrade',
    # There is no current room-door equivalent for the old direct fabric reward.
    'RoomRewardMixerFabric': None,
    'RoomRewardTrash': None,
}


_ELEMENT_IDS = frozenset(('Fire','Water','Earth','Air','Aether'))
_MAX_AMOUNT = 999999
DESIRED_STATE_SCHEMA_VERSION = 3


def _finite_number(value):
    return type(value) in (int,float) and not isinstance(value,bool) and math.isfinite(value)


def _normalize_amount(value):
    if not _finite_number(value) or not 0<=value<=_MAX_AMOUNT:return None
    if type(value) is int:return value
    if type(value) is float and value.is_integer():return int(value)
    return None


def _normalize_stat_locks(raw):
    if not isinstance(raw,dict):return {}
    result={}
    for stat,value in raw.items():
        rule=STAT_RULES.get(stat) if isinstance(stat,str) else None
        if rule is None or not _finite_number(value):continue
        if rule.get('integer'):
            if type(value) is float and value.is_integer():value=int(value)
            elif type(value) is not int:continue
        if rule['min']<=value<=rule['max']:result[stat]=value
    return result


def _normalize_vital_locks(raw):
    if not isinstance(raw,dict):return {}
    result={}
    for vital,row in raw.items():
        if vital not in ('health','mana','armor') or not isinstance(row,dict):continue
        current=row.get('current')
        if not _finite_number(current) or not 0<=current<=_MAX_AMOUNT or (vital=='health' and current<1):continue
        normalized={'current':current}
        if vital!='armor':
            maximum=row.get('max')
            if not _finite_number(maximum) or not 0<=maximum<=_MAX_AMOUNT or (vital=='health' and maximum<1):continue
            normalized['max']=maximum
        result[vital]=normalized
    return result


def _normalize_resource_locks(raw):
    if not isinstance(raw,dict):return {}
    result={}
    for resource,amount in raw.items():
        normalized=_normalize_amount(amount)
        if isinstance(resource,str) and resource and normalized is not None:result[resource]=normalized
    return result


def _normalize_element_locks(raw):
    if not isinstance(raw,dict):return {}
    result={}
    for element,amount in raw.items():
        normalized=_normalize_amount(amount)
        if element in _ELEMENT_IDS and normalized is not None:result[element]=normalized
    return result


def _desired_schema_version(raw):
    if 'schemaVersion' not in raw:return 0
    value=raw['schemaVersion']
    if type(value) is not int or value<0:raise ValueError('desired-state schemaVersion 无效。')
    return value


def migrate_legacy_boon_semantics(raw, schema_version):
    """Canonicalize pre-v3 boon controls to explicit force semantics.

    Schema 2 already used the old allowLegendary/allowDuo field names for the
    new force action, so those values migrate exactly. Schemas 0/1 used the
    names literally (allow/filter semantics), which cannot be truthfully mapped
    to a force action and therefore reset both controls off.
    """
    if not isinstance(raw,dict):return raw
    result=dict(raw)
    rarity=result.get('boonRarity')
    rarity=dict(rarity) if isinstance(rarity,dict) else {}
    if schema_version==2:
        rarity['forceLegendary']=rarity.get('allowLegendary') if type(rarity.get('allowLegendary')) is bool else False
        rarity['forceDuo']=rarity.get('allowDuo') if type(rarity.get('allowDuo')) is bool else False
    else:
        rarity['forceLegendary']=False
        rarity['forceDuo']=False
    rarity.pop('allowLegendary',None)
    rarity.pop('allowDuo',None)
    result['boonRarity']=rarity
    return result


class Hades2PreferenceStore:
    def __init__(self, path):
        self.path = path
        self.unsupported_schema_version = None
        self.write_blocked_error = None

    @staticmethod
    def defaults():
        values={key:False for key in TOGGLES}
        values.update(damageMultiplier=2.0,moneyMultiplier=2.0,resourceMultiplier=2.0,gameSpeed=1.0)
        values.update(
            boonRarity={'target':'Epic','multiplier':100.0,'forceLegendary':False,'forceDuo':False},
            statLocks={},vitalLocks={},resourceLocks={},rerollsLock=None,elementLocks={},nextRoomReward=None,
        )
        return values

    @classmethod
    def normalize(cls, raw):
        result=cls.defaults()
        if not isinstance(raw,dict):return result
        for key in TOGGLES:
            if type(raw.get(key)) is bool:result[key]=raw[key]
        for key in MULTIPLIERS:
            value=raw.get(key)
            if type(value) in (int,float) and not isinstance(value,bool) and math.isfinite(value):
                if (key=='gameSpeed' and 0<=value<=10) or (key!='gameSpeed' and 1<=value<=100):result[key]=float(value)
        rarity=raw.get('boonRarity')
        if isinstance(rarity,dict):
            target=rarity.get('target');mult=rarity.get('multiplier')
            if target in ('Common','Rare','Epic','Heroic'):result['boonRarity']['target']=target
            if type(mult) in (int,float) and not isinstance(mult,bool) and math.isfinite(mult) and 0<=mult<=1000:result['boonRarity']['multiplier']=float(mult)
            if type(rarity.get('forceLegendary')) is bool:result['boonRarity']['forceLegendary']=rarity['forceLegendary']
            if type(rarity.get('forceDuo')) is bool:result['boonRarity']['forceDuo']=rarity['forceDuo']
        result['statLocks']=_normalize_stat_locks(raw.get('statLocks'))
        result['vitalLocks']=_normalize_vital_locks(raw.get('vitalLocks'))
        result['resourceLocks']=_normalize_resource_locks(raw.get('resourceLocks'))
        result['elementLocks']=_normalize_element_locks(raw.get('elementLocks'))
        value=_normalize_amount(raw.get('rerollsLock'))
        if value is not None:result['rerollsLock']=value
        reward=raw.get('nextRoomReward')
        if reward is None or (isinstance(reward,str) and len(reward)<=128):
            result['nextRoomReward']=NEXT_ROOM_REWARD_MIGRATIONS.get(reward,reward)
        return result

    def load(self):
        self.unsupported_schema_version=None
        self.write_blocked_error=None
        if not self.path.is_file():return self.defaults(),False
        try:
            text=self.path.read_text(encoding='utf-8')
        except UnicodeError:
            quarantined=quarantine_corrupt_file(self.path)
            logging.exception('Quarantined unreadable desired-state profile as %s',quarantined)
            if quarantined is None and self.path.exists():
                self.write_blocked_error=PersistenceError('现有 desired-state 无法安全隔离，已禁止覆盖原文件。')
            return self.defaults(),False
        except FileNotFoundError:
            # The file may disappear between is_file() and read_text(); that is
            # equivalent to first-run state and does not justify write-protecting
            # the store for the rest of this backend lifetime.
            return self.defaults(),False
        except OSError:
            logging.exception('Failed to read desired-state profile')
            self.write_blocked_error=PersistenceError('现有 desired-state 无法安全读取，已禁止本次进程覆盖原文件。')
            return self.defaults(),False
        try:
            raw=json.loads(text)
        except (json.JSONDecodeError,UnicodeError):
            quarantined=quarantine_corrupt_file(self.path)
            logging.exception('Quarantined invalid desired-state profile as %s',quarantined)
            if quarantined is None and self.path.exists():
                self.write_blocked_error=PersistenceError('损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。')
            return self.defaults(),False
        if not isinstance(raw,dict):
            quarantined=quarantine_corrupt_file(self.path)
            logging.error('Quarantined invalid desired-state profile shape as %s',quarantined)
            if quarantined is None and self.path.exists():
                self.write_blocked_error=PersistenceError('损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。')
            return self.defaults(),False
        try:
            schema_version=_desired_schema_version(raw)
        except ValueError:
            quarantined=quarantine_corrupt_file(self.path)
            logging.exception('Quarantined desired-state profile with invalid schema version as %s',quarantined)
            if quarantined is None and self.path.exists():
                self.write_blocked_error=PersistenceError('损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。')
            return self.defaults(),False
        if schema_version>DESIRED_STATE_SCHEMA_VERSION:
            self.unsupported_schema_version=schema_version
            self.write_blocked_error=UnsupportedSchemaVersionError(
                'desired-state',schema_version,DESIRED_STATE_SCHEMA_VERSION
            )
            logging.error(
                'Desired-state schema %s is newer than supported schema %s; preserving file read-only',
                schema_version,DESIRED_STATE_SCHEMA_VERSION,
            )
            return self.defaults(),False
        if schema_version<DESIRED_STATE_SCHEMA_VERSION:
            raw=migrate_legacy_boon_semantics(raw,schema_version)
        return self.normalize(raw),True

    def save(self, preferences):
        try:
            if self.write_blocked_error is not None:
                raise self.write_blocked_error
            document=dict(preferences)
            document['schemaVersion']=DESIRED_STATE_SCHEMA_VERSION
            payload=json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
            atomic_write_text(self.path,payload)
        except Exception:
            logging.exception('Failed to persist desired-state profile')
            raise
