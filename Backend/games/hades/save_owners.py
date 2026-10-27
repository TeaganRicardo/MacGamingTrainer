"""Supported Hades I saved-global locations and ordinary entity boundaries.

Main.lua:1019..1035 saves eligible globals. RunManager.lua:121..178,
Narrative.lua:4, CodexScripts.lua:2, AwardMenuScripts.lua:752..756 and
RunManager.lua:251..252 establish these distinct owners. A path is always
relative to the first saved-global table, never implicitly to GameState.
"""

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
