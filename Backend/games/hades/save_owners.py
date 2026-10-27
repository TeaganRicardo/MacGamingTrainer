"""Supported Hades I saved-global locations and ordinary entity boundaries.

Main.lua:1019..1035 saves eligible globals. RunManager.lua:121..178,
Narrative.lua:4, CodexScripts.lua:2, AwardMenuScripts.lua:752..756 and
RunManager.lua:251..252 establish these distinct owners. A path is always
relative to the first saved-global table, never implicitly to GameState.
"""
import math

NATIVE_OWNERS = {
    'resources': tuple(('GameState', name) for name in
                       ('Resources', 'LifetimeResourcesGained', 'LifetimeResourcesSpent')),
    'progression': tuple(('GameState', name) for name in
                        ('MetaUpgrades', 'MetaUpgradesUnlocked', 'MetaUpgradeStagesUnlocked',
                         'MetaUpgradesSelected', 'MetaUpgradeState', 'AssistUnlocks', 'ActiveMutators')),
    'equipment': (*tuple(('GameState', name) for name in
                        ('WeaponsUnlocked', 'WeaponUnlocks', 'LastWeaponUpgradeData',
                         'LastInteractedWeaponUpgrade', 'KeepsakeChambers', 'LastAwardTrait', 'LastAssistTrait')),
                  ('CurrentRun', 'Hero')),
    'relationships': tuple(('GameState', name) for name in ('Gift', 'NPCInteractions', 'AssistUnlocks')),
    'narrative': (('TextLinesRecord',), ('CodexStatus',),
                  *tuple(('GameState', name) for name in ('Flags', 'QuestStatus', 'Cosmetics', 'CosmeticsAdded'))),
    'statistics': (*tuple(('GameState', name) for name in
                         ('TimesCleared', 'TimesClearedWeapon', 'WeaponRecordsClearTime',
                          'WeaponRecordsShrinePoints', 'ConsecutiveClears', 'ConsecutiveClearsRecord',
                          'CompletedRunsCache', 'AccumulatedMetaPointsCache', 'SpentShrinePointsCache',
                          'RecordClearedShrineThreshold', 'RecordLastClearedShrineReward',
                          'ClearedWithMetaUpgrades', 'TotalRequiredEnemyKills', 'RoomCountCache',
                          'EncountersOccurredCache', 'EncountersCompletedCache')),
                   ('CurrentRun', 'GameplayTime')),
    'history': (('GameState', 'RunHistory'), ('CurrentRun',)),
}
NATIVE_PATHS = {path for roots in NATIVE_OWNERS.values() for path in roots}

# The child occurrence owns both its collection row and all nested fields.
# Identity comes from its physical path, independently of a localized name.
ENTITY_DEPTHS = {root: len(root) + 1 for root in (*NATIVE_OWNERS['relationships'],
    ('GameState', 'WeaponUnlocks'), ('GameState', 'LastWeaponUpgradeData'),
    ('GameState', 'KeepsakeChambers'), ('GameState', 'RunHistory'),
    ('GameState', 'TimesClearedWeapon'), ('GameState', 'WeaponRecordsClearTime'),
    ('GameState', 'WeaponRecordsShrinePoints'), ('GameState', 'QuestStatus'),
    ('GameState', 'Cosmetics'), ('GameState', 'CosmeticsAdded'),
    ('GameState', 'Flags'), ('TextLinesRecord',))}
# CodexScripts.lua:32..38: chapter -> entry -> Amount / numbered unlocks.
ENTITY_DEPTHS[('CodexStatus',)] = 3

# Ordinary views describe these persisted fields, rather than inheriting every
# runtime field below a saved owner. Main.lua:933..956 keeps these run summaries;
# RunManager.lua:1..15,1918..1931 establishes Hero / trait / weapon projections.
RUN_FIELDS = {'Cleared', 'GameplayTime', 'Money', 'NumRerolls', 'EndingRoomName',
              'EndingMoney', 'RunDepthCache', 'BiomeDepthCache', 'MetaPointsCache',
              'ShrinePointsCache', 'EndingKeepsakeName', 'Hero', 'WeaponsCache',
              'TraitCache', 'MetaUpgradeCache', 'RoomCountCache', 'TextLinesRecord',
              'EasyModeLevel', 'TargetShrinePointThreshold', 'SquelchedHermes', 'RunClearMessage'}
HERO_FIELDS = {'Name', 'Health', 'MaxHealth', 'Weapons', 'Traits'}
TRAIT_FIELDS = {'Name', 'Rarity'}


def sequence_index(key, minimum=1):
    return (type(key) is not bool and isinstance(key, (int, float)) and math.isfinite(key)
            and key >= minimum and int(key) == key)


def ordinary_purpose(keys, catalog):
    """Return a native field/identity or bilingual indexed purpose, else None."""
    if not keys or any(type(key) is bool or not isinstance(key, (str, int, float)) for key in keys): return None
    identities = catalog['nativeIds']
    if any(key in identities['diagnostics'] for key in keys if isinstance(key, str)): return None

    def member(path, category):
        known = catalog[category] if category in ('scenes', 'weapons') else identities[category]
        if len(path) != 1 or not isinstance(path[0], str) or path[0] not in known: return None
        if category in ('meta', 'characters', 'traits', 'quests', 'cosmetics') and path[0] not in catalog['names']:
            return None
        return path[0]

    def trait(path):
        if not path: return 'Traits'
        if not sequence_index(path[0]): return None
        if len(path) == 1: return ('祝福与效果 #' + str(int(path[0])), 'Boon/effect #' + str(int(path[0])))
        return path[1] if len(path) == 2 and path[1] in TRAIT_FIELDS else None

    def hero(path):
        if not path: return 'Hero'
        if path[0] not in HERO_FIELDS: return None
        if len(path) == 1: return path[0]
        if path[0] == 'Weapons': return member(path[1:], 'weapons')
        if path[0] == 'Traits': return trait(path[1:])
        return None

    def run(path):
        if not path: return 'CurrentRun'
        name = path[0]
        if name not in RUN_FIELDS: return None
        if len(path) == 1: return name
        if name == 'Hero': return hero(path[1:])
        category = {'WeaponsCache': 'weapons', 'TraitCache': 'traits', 'MetaUpgradeCache': 'meta',
                    'RoomCountCache': 'rooms', 'TextLinesRecord': 'scenes'}.get(name)
        return member(path[1:], category) if category else None

    if keys[0] == 'CurrentRun': return run(keys[1:])
    if keys[0] == 'TextLinesRecord':
        return 'TextLinesRecord' if len(keys) == 1 else member(keys[1:], 'scenes')
    if keys[0] == 'CodexStatus':
        path = keys[1:]
        if not path: return 'CodexStatus'
        if path[0] in ('SelectedChapterName', 'SelectedEntryNames'):
            if len(path) == 1: return path[0]
            return member(path[1:], 'chapters') if path[0] == 'SelectedEntryNames' else None
        chapter = identities['codex'].get(path[0]) if isinstance(path[0], str) else None
        if chapter is None: return None
        if len(path) == 1: return path[0]
        if path[1] not in chapter: return None
        if len(path) == 2: return path[1]
        if path[2] == 'Amount': return 'Amount' if len(path) == 3 else None
        if not sequence_index(path[2]): return None
        if len(path) == 3: return ('宝典解锁页 #' + str(int(path[2])), 'Codex unlock #' + str(int(path[2])))
        return 'Unlocked' if len(path) == 4 and path[3] == 'Unlocked' else None
    if keys[0] != 'GameState' or len(keys) < 2: return None
    root, path = keys[1], keys[2:]
    if ('GameState', root) not in NATIVE_PATHS:
        return None
    if not path: return root
    if root == 'RunHistory':
        if not sequence_index(path[0]): return None
        if len(path) == 1: return ('挑战记录 #' + str(int(path[0])), 'Run #' + str(int(path[0])))
        return run(path[1:])
    if root == 'Gift':
        if member(path[:1], 'characters') is None: return None
        if len(path) == 1: return path[0]
        if path[1] not in ('Value', 'NewTraits'): return None
        if len(path) == 2: return path[1]
        if path[1] == 'NewTraits' and len(path) == 3 and sequence_index(path[2]):
            return ('新获信物与效果 #' + str(int(path[2])), 'Newly granted trait #' + str(int(path[2])))
        return None
    if root == 'WeaponUnlocks':
        if path[0] not in catalog['weapons']: return None
        if len(path) == 1: return path[0]
        if len(path) == 2 and sequence_index(path[1]) and path[1] <= len(catalog['weapons'][path[0]]):
            return catalog['weapons'][path[0]][int(path[1]) - 1]['trait']
        return None
    if root == 'LastWeaponUpgradeData':
        if path[0] not in catalog['weapons']: return None
        return path[-1] if len(path) == 1 or len(path) == 2 and path[1] == 'Index' else None
    if root == 'LastInteractedWeaponUpgrade':
        return path[0] if len(path) == 1 and path[0] in ('WeaponName', 'ItemIndex') else None
    if root == 'MetaUpgradesSelected':
        if len(path) == 1 and sequence_index(path[0]) and path[0] <= len(catalog['mirrorRows']):
            return ('圣镜天赋行 #' + str(int(path[0])), 'Mirror talent row #' + str(int(path[0])))
        return None
    if root in ('RecordClearedShrineThreshold', 'RecordLastClearedShrineReward'):
        if path[0] not in catalog['weapons']: return None
        if len(path) == 1: return path[0]
        if path[1] not in identities['rooms']: return None
        if len(path) == 2: return path[1]
        if root == 'RecordLastClearedShrineReward' and len(path) == 3 and sequence_index(path[2], 0):
            return ('热度奖励记录 #' + str(int(path[2])), 'Heat reward record #' + str(int(path[2])))
        return None
    category = {
        'Resources': 'resources', 'LifetimeResourcesGained': 'resources', 'LifetimeResourcesSpent': 'resources',
        'MetaUpgrades': 'meta', 'MetaUpgradesUnlocked': 'meta', 'MetaUpgradeState': 'meta',
        'ClearedWithMetaUpgrades': 'meta', 'ActiveMutators': 'meta',
        'WeaponsUnlocked': 'weapons', 'TimesClearedWeapon': 'weapons',
        'WeaponRecordsClearTime': 'weapons', 'WeaponRecordsShrinePoints': 'weapons',
        'KeepsakeChambers': 'traits', 'AssistUnlocks': 'traits', 'NPCInteractions': 'characters',
        'QuestStatus': 'quests', 'Cosmetics': 'cosmetics', 'CosmeticsAdded': 'cosmetics',
        'Flags': 'flags', 'RoomCountCache': 'rooms',
        'EncountersOccurredCache': 'encounters', 'EncountersCompletedCache': 'encounters',
    }.get(root)
    return member(path, category) if category else None
