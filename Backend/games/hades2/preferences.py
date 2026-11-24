import json
import logging
import math
from pathlib import Path

from core.persistence import VersionedDocumentStore
from .vital_state import normalize_vital_locks

from .error_presentation import Hades2ValueError
from .persistence import (
    PersistenceError,
    UnsupportedSchemaVersionError,
)
from .schema import (
    BOON_RARITY_TARGETS,
    ELEMENT_IDS,
    MAX_AMOUNT,
    MULTIPLIER_RULES,
    MULTIPLIERS,
    STAT_RULES,
    TOGGLES,
    default_boon_rarity,
    desired_feature_defaults,
    normalize_desired_feature_value,
    normalize_gathering_probabilities,
    normalize_chaos_gate_probability,
)

DESIRED_STATE_SCHEMA_VERSION = 13


def _finite_number(value):
    return type(value) in (int,float) and not isinstance(value,bool) and math.isfinite(value)


LEGACY_DAMAGE_MULTIPLIER = 2.0


def migrate_legacy_damage_identity(raw):
    """Collapse the retired damageEnabled toggle into damageMultiplier for schema < 13."""
    if not isinstance(raw,dict):return raw
    result=dict(raw)
    rule=MULTIPLIER_RULES['damageMultiplier']
    enabled=result.get('damageEnabled')
    multiplier=result.get('damageMultiplier')
    if not _finite_number(multiplier) or not rule['min']<=multiplier<=rule['max']:
        multiplier=None
    if enabled is False:
        multiplier=1.0
    elif multiplier is None:
        multiplier=LEGACY_DAMAGE_MULTIPLIER if enabled is True else rule['default']
    result['damageMultiplier']=float(multiplier)
    result.pop('damageEnabled',None)
    result.pop('gardenQoL',None)
    return result


def _normalize_amount(value):
    if not _finite_number(value) or not 0<=value<=MAX_AMOUNT:return None
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
        if element in ELEMENT_IDS and normalized is not None:result[element]=normalized
    return result


def _desired_schema_version(raw):
    if 'schemaVersion' not in raw:return 0
    value=raw['schemaVersion']
    if type(value) is not int or value<0:raise Hades2ValueError('hades2.error.desiredSchemaInvalid', 'desired-state schemaVersion 无效。')
    return value


def migrate_legacy_invincibility_identity(raw):
    """Rename the retired Trainer invulnerability key at persistence boundaries only."""
    if not isinstance(raw,dict):return raw
    result=dict(raw)
    if type(result.get('godMode')) is bool:
        result['invincibility']=result['godMode']
    result.pop('godMode',None)
    return result


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


def normalize_persisted_desired(raw, schema_version):
    """Migrate one persisted desired document to current canonical semantics."""
    if type(schema_version) is not int or schema_version < 0:
        raise Hades2ValueError('hades2.error.desiredSchemaInvalid', 'desired-state schemaVersion 无效。')
    if schema_version > DESIRED_STATE_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            'desired-state', schema_version, DESIRED_STATE_SCHEMA_VERSION
        )
    migrated=dict(raw) if isinstance(raw,dict) else raw
    if schema_version < 3:
        migrated=migrate_legacy_boon_semantics(migrated,schema_version)
    if schema_version < 5:
        migrated=migrate_legacy_invincibility_identity(migrated)
    if schema_version < 6 and isinstance(migrated,dict):
        # This field did not have accepted semantics in older documents.
        migrated.pop('gatheringProbabilities',None)
    if schema_version < 7 and isinstance(migrated,dict):
        migrated.pop('chaosGateProbability',None)
    if schema_version < 8 and isinstance(migrated,dict):
        migrated.pop('forceEnableRerolls',None)
    if schema_version < 10 and isinstance(migrated,dict):
        migrated.pop('infiniteMoney',None)
        migrated.pop('infiniteRerolls',None)
    if schema_version < 13:
        migrated=migrate_legacy_damage_identity(migrated)
    if isinstance(migrated,dict):
        for key in ('nextRoomReward','nextRoomRewardToken','nextOccurrenceTarget','nextOccurrenceToken'):
            migrated.pop(key,None)
    return Hades2PreferenceStore.normalize(migrated)


def _prepare_desired_document(preferences, schema_version):
    document=Hades2PreferenceStore.normalize(preferences)
    document['schemaVersion']=schema_version
    return document


class Hades2PreferenceStore:
    def __init__(self, path):
        self.path = Path(path)
        self._store = VersionedDocumentStore(
            self.path,
            schema_version=DESIRED_STATE_SCHEMA_VERSION,
            compatibility_floor=0,
            defaults=self.defaults,
            normalize=normalize_persisted_desired,
            build_document=_prepare_desired_document,
            serialize=lambda doc: json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',
            document_label='desired-state profile',
            quarantine_corrupt=True,
            fallback_on_error=True,
            newer_schema_error=lambda found, supported: UnsupportedSchemaVersionError('desired-state', found, supported),
            read_error=lambda _reason, _exc: PersistenceError(
                '现有 desired-state 无法安全读取，已禁止本次进程覆盖原文件。',
                presentation='hades2.error.preferenceWriteBlocked',
            ),
            quarantine_failed_error=lambda reason: PersistenceError(
                '现有 desired-state 无法安全隔离，已禁止覆盖原文件。'
                if reason == 'unreadable'
                else '损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。',
                presentation='hades2.error.preferenceWriteBlocked',
            ),
            write_error=lambda error: error if isinstance(error, PersistenceError) else PersistenceError('无法安全写入本地配置。'),
        )

    @property
    def unsupported_schema_version(self):
        return self._store.unsupported_schema_version

    @unsupported_schema_version.setter
    def unsupported_schema_version(self, value):
        self._store.unsupported_schema_version = value

    @property
    def write_blocked_error(self):
        return self._store.write_blocked_error

    @write_blocked_error.setter
    def write_blocked_error(self, value):
        self._store.write_blocked_error = value

    @staticmethod
    def defaults():
        values=desired_feature_defaults()
        values.update(
            boonRarity=default_boon_rarity(),
            statLocks={},vitalLocks={},resourceLocks={},rerollsLock=None,elementLocks={},biomeTimerFrozen=False,gatheringProbabilities={},chaosGateProbability=None,
        )
        return values

    @classmethod
    def normalize(cls, raw):
        result=cls.defaults()
        if not isinstance(raw,dict):return result
        for key in TOGGLES+MULTIPLIERS:
            value=normalize_desired_feature_value(key,raw.get(key))
            if value is not None:result[key]=value
        rarity=raw.get('boonRarity')
        # Keep the serialized v17 field neutral when loading older probability settings.
        if isinstance(rarity,dict):
            target=rarity.get('target')
            if target in BOON_RARITY_TARGETS:result['boonRarity']['target']=target
            if type(rarity.get('forceLegendary')) is bool:result['boonRarity']['forceLegendary']=rarity['forceLegendary']
            if type(rarity.get('forceDuo')) is bool:result['boonRarity']['forceDuo']=rarity['forceDuo']
        result['statLocks']=_normalize_stat_locks(raw.get('statLocks'))
        result['vitalLocks']=normalize_vital_locks(raw.get('vitalLocks'))
        result['resourceLocks']=_normalize_resource_locks(raw.get('resourceLocks'))
        if type(raw.get('biomeTimerFrozen')) is bool:result['biomeTimerFrozen']=raw['biomeTimerFrozen']
        if result.get('infiniteMoney'):
            result['resourceLocks'].pop('Money',None)
        result['elementLocks']=_normalize_element_locks(raw.get('elementLocks'))
        result['gatheringProbabilities']=normalize_gathering_probabilities(raw.get('gatheringProbabilities'))
        result['chaosGateProbability']=normalize_chaos_gate_probability(raw.get('chaosGateProbability'))
        value=_normalize_amount(raw.get('rerollsLock'))
        if value is not None:result['rerollsLock']=value
        if result.get('infiniteRerolls'):
            result['rerollsLock']=None
        return result

    def load(self):
        return self._store.load()

    def save(self, preferences):
        try:
            self._store.save(preferences)
        except Exception:
            logging.exception('Failed to persist desired-state profile')
            raise
