"""Synthetic native-shaped Hades I saves; no captured user/game save data.

Independent literal-only LZ4 and luabins writer follows the exact supported
native writer layout documented in docs/reference/hades/save_editor.md.
"""
from pathlib import Path
import struct
import zlib


class Entries:
    def __init__(self, entries, array=0):
        self.entries, self.array = list(entries), array


class RawNumber:
    def __init__(self, bits): self.raw = bytes.fromhex(bits)


def lua(value):
    if value is None: return b'-'
    if value is False: return b'0'
    if value is True: return b'1'
    if isinstance(value, RawNumber): return b'N' + value.raw
    if isinstance(value, (int, float)): return b'N' + struct.pack('<d', value)
    if isinstance(value, (str, bytes)):
        raw = value.encode('utf-8') if isinstance(value, str) else value
        return b'S' + struct.pack('<I', len(raw)) + raw
    if isinstance(value, dict): value = Entries(value.items())
    if isinstance(value, list): value = Entries(enumerate(value, 1), len(value))
    if isinstance(value, Entries):
        return b'T' + struct.pack('<Ii', value.array, len(value.entries) - value.array) + b''.join(
            lua(key) + lua(item) for key, item in value.entries)
    raise TypeError(type(value))


def literal_lz4(payload):
    count = len(payload)
    result = bytearray([min(count, 15) << 4])
    if count >= 15:
        extra = count - 15
        while extra >= 255:
            result.append(255)
            extra -= 255
        result.append(extra)
    return bytes(result) + payload


def sized(value):
    raw = value.encode('utf-8') if isinstance(value, str) else value
    return struct.pack('<I', len(raw)) + raw


def container(lua_bytes, *, version=16, location=b'RoomPreRun\xff', compressed=None):
    compressed = literal_lz4(lua_bytes) if compressed is None else compressed
    body = (struct.pack('<IQ', version, 0x0102030405060708) + sized(location) +
            struct.pack('<IIIBBI', 2, 40, 3, 0, 1, 2) + sized('SwordWeapon') + sized(b'Trait\xfe') +
            sized('RoomPreRun') + sized('A_Opening01') + sized(compressed))
    return b'SGB1' + struct.pack('<I', zlib.adler32(body) & 0xffffffff) + body


def root_state(amount=12, marker='fixed-source'):
    return {
        'GameState': {
            'Resources': {'MetaPoints': amount, 'GiftPoints': 2, 'LockKeys': 3},
            'LifetimeResourcesGained': {'MetaPoints': 100}, 'LifetimeResourcesSpent': {'MetaPoints': 88},
            'MetaUpgradesUnlocked': {'BackstabMetaUpgrade': False, 'FirstStrikeMetaUpgrade': False},
            'MetaUpgrades': {'BackstabMetaUpgrade': 1}, 'MetaUpgradeState': {},
            'MetaUpgradesSelected': ['BackstabMetaUpgrade'], 'MetaUpgradeStagesUnlocked': 0,
            'WeaponsUnlocked': {'SwordWeapon': True}, 'WeaponUnlocks': {}, 'LastWeaponUpgradeData': {},
            'LastInteractedWeaponUpgrade': {}, 'KeepsakeChambers': {'MaxHealthKeepsakeTrait': 4},
            'LastAwardTrait': 'MaxHealthKeepsakeTrait', 'LastAssistTrait': 'FuryAssistTrait',
            'Gift': {'NPC_Nyx_01': {'Value': 1, 'NewTraits': ['BackstabAlphaStrikeTrait']},
                     'NPC_Achilles_01': {'Value': 2, 'NewTraits': ['DirectionalArmorTrait']}},
            'NPCInteractions': {'NPC_Nyx_01': 2, 'NPC_Achilles_01': 3},
            'AssistUnlocks': {'FuryAssistTrait': 1}, 'ActiveMutators': {},
            'QuestStatus': {}, 'Cosmetics': {'Cosmetic_DrapesRed': True},
            'CosmeticsAdded': {'Cosmetic_DrapesRed': True}, 'Flags': {'HardMode': True},
            'TimesCleared': 1, 'TimesClearedWeapon': {'SwordWeapon': 1},
            'WeaponRecordsClearTime': {'SwordWeapon': 120}, 'WeaponRecordsShrinePoints': {'SwordWeapon': 3},
            'ConsecutiveClears': 0, 'ConsecutiveClearsRecord': 1,
            'RoomCountCache': {'A_Opening01': 2}, 'EncountersOccurredCache': {}, 'EncountersCompletedCache': {},
            'RecordClearedShrineThreshold': {}, 'RecordLastClearedShrineReward': {},
            'ClearedWithMetaUpgrades': {}, 'TotalRequiredEnemyKills': 7,
            'CompletedRunsCache': 2, 'AccumulatedMetaPointsCache': 40, 'SpentShrinePointsCache': 3,
            'RunHistory': [{'Cleared': True, 'GameplayTime': 120, 'WeaponsCache': {'SwordWeapon': True}},
                           {'Cleared': False, 'GameplayTime': 80}],
            'UnknownFutureField': {'Marker': marker, 'Enabled': False},
        },
        'TextLinesRecord': {'NyxFirstMeeting': True, 'AchillesFirstMeeting': True},
        'CodexStatus': {'SelectedChapterName': 'ChthonicGods', 'SelectedEntryNames': {},
                        'ChthonicGods': {'NPC_Nyx_01': {'Amount': 3, 1: {'Unlocked': True}}}},
        'CurrentRun': {'Money': 30, 'NumRerolls': 1, 'GameplayTime': 80,
                       'TextLinesRecord': {'NyxFirstMeeting': True}, 'Hero': {'Name': 'Hero', 'Health': 50,
                       'MaxHealth': 50, 'Weapons': {'SwordWeapon': True}, 'Traits': []}},
    }


def build_save(amount=12, marker='fixed-source', *, state=None, extra=()):
    state = root_state(amount, marker) if state is None else state
    nodes = (state, *extra)
    return container(bytes([len(nodes)]) + b''.join(lua(node) for node in nodes))


def environment(base, *, running=False, game_id='hades'):
    from core.module_manifest import SaveManagementSpec, SaveRootSpec
    from core.save_service import CoreSaveService
    base = Path(base)
    saves = base / 'saves'
    saves.mkdir(parents=True)
    (saves / 'Profile1.sav').write_bytes(build_save())
    (saves / 'Profile2.sav').write_bytes(build_save(900, 'target-original'))
    (saves / 'Profile1_Temp.sav').write_bytes(build_save(99, 'independent-temp'))
    (saves / 'Profile1.v.sav').write_bytes(b'native-validation-marker')
    (saves / 'Profile1.sjson').write_bytes(b'fixture settings')
    (saves / 'activeProfile').write_bytes(b'SGB1' + sized('Profile1'))
    spec = SaveManagementSpec(roots=(SaveRootSpec('main', str(saves), ('Profile*.sav', 'Profile*.sjson', 'activeProfile')),),
                             provider=None, hot_backup=True, restore_policy='stoppedOnly', staged_restore=True)
    service = CoreSaveService(game_id, spec, base / 'data', target_running_probe=lambda: running)
    return saves, service
