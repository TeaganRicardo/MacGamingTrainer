"""Pinned Hades I document workspaces, semantic owners and combined edit plans."""
from dataclasses import fields
import json
import math
from pathlib import Path
import uuid

from .catalog import trait_names, resource_catalog
from .save_document import HadesSaveDocument, LuaTable, AmbiguousKeyError
from .save_edit import HadesSaveEditSession
from .save_owners import NATIVE_OWNERS, ENTITY_DEPTHS, ordinary_purpose
from .save_provider import editor_files, active_profile_bytes
from . import save_values as values


_CATALOG = json.loads(Path(__file__).with_name('save_catalog.json').read_text())
DOMAINS = ('resources', 'progression', 'equipment', 'relationships', 'narrative',
           'statistics', 'history', 'advanced')
_PAIRS = {
    'GameState': ('长期进度', 'Persistent progress'), 'CurrentRun': ('当前挑战', 'Current run'),
    'RunHistory': ('挑战历史', 'Run history'), 'Resources': ('资源库存', 'Resource balances'),
    'LifetimeResourcesGained': ('累计获得资源', 'Lifetime resource gains'),
    'LifetimeResourcesSpent': ('累计消耗资源', 'Lifetime resource spending'),
    'MetaUpgrades': ('夜之圣镜 · 当前等级', 'Mirror of Night · active ranks'),
    'MetaUpgradesUnlocked': ('夜之圣镜 · 已解锁天赋', 'Mirror of Night · unlocked talents'),
    'MetaUpgradesSelected': ('夜之圣镜 · 当前天赋', 'Mirror of Night · selected talents'),
    'MetaUpgradeState': ('夜之圣镜 · 备用等级', 'Mirror of Night · stored ranks'),
    'MetaUpgradeStagesUnlocked': ('夜之圣镜 · 解锁阶段', 'Mirror of Night · unlocked stages'),
    'Gift': ('关系与赠礼', 'Relationships and gifts'), 'Value': ('赠礼进度', 'Gift progress'),
    'NewTraits': ('新获信物与效果', 'Newly granted traits'),
    'NPCInteractions': ('角色互动次数', 'Character interaction counts'),
    'TextLinesRecord': ('已发生剧情', 'Recorded scenes'),
    'Flags': ('剧情标志', 'Story flags'),
    'QuestStatus': ('命运清单进度', 'Prophecy progress'),
    'Cosmetics': ('房屋修整', 'House renovations'), 'CosmeticsAdded': ('已购房屋修整', 'Purchased renovations'),
    'CodexStatus': ('冥界宝典记录', 'Codex records'),
    'WeaponsUnlocked': ('已解锁兵器', 'Unlocked weapons'), 'WeaponUnlocks': ('兵器形态等级', 'Weapon aspect ranks'),
    'LastWeaponUpgradeData': ('兵器形态选择', 'Selected weapon aspects'),
    'LastInteractedWeaponUpgrade': ('最近选择的形态', 'Last selected aspect'),
    'LastAwardTrait': ('下次装备的信物', 'Next-equip keepsake'),
    'LastAssistTrait': ('下次装备的伙伴', 'Next-equip companion'),
    'KeepsakeChambers': ('信物遭遇计数', 'Keepsake encounter counts'), 'AssistUnlocks': ('伙伴解锁', 'Companion unlocks'),
    'Hero': ('扎格列欧斯', 'Zagreus'), 'Weapons': ('已装备兵器', 'Equipped weapons'),
    'Traits': ('祝福与效果', 'Boons and effects'), 'MaxHealth': ('生命上限', 'Maximum life'),
    'Health': ('生命值', 'Life'), 'Money': ('卡戎金币', 'Charon’s Obol'), 'NumRerolls': ('重掷次数', 'Rerolls'),
    'Name': ('名称', 'Name'), 'Rarity': ('稀有度', 'Rarity'), 'Level': ('等级', 'Rank'),
    'Index': ('形态序号', 'Aspect index'), 'Cleared': ('已成功逃脱', 'Escaped'),
    'WeaponName': ('兵器', 'Weapon'), 'ItemIndex': ('形态序号', 'Aspect index'),
    'Amount': ('宝典累计进度', 'Codex accumulated progress'), 'Unlocked': ('已解锁', 'Unlocked'),
    'SelectedChapterName': ('当前宝典章节', 'Selected Codex chapter'),
    'SelectedEntryNames': ('各章当前宝典条目', 'Selected Codex entries by chapter'),
    'TimesCleared': ('成功逃脱次数', 'Escape count'), 'TimesClearedWeapon': ('各兵器成功逃脱次数', 'Escapes by weapon'),
    'WeaponRecordsClearTime': ('各兵器最快逃脱时间', 'Fastest escapes by weapon'),
    'WeaponRecordsShrinePoints': ('各兵器最高热度', 'Highest Heat by weapon'),
    'ConsecutiveClears': ('连续成功逃脱次数', 'Consecutive escapes'),
    'ConsecutiveClearsRecord': ('连续逃脱纪录', 'Consecutive escape record'),
    'CompletedRunsCache': ('挑战次数缓存', 'Completed run count cache'),
    'AccumulatedMetaPointsCache': ('黑暗累计值缓存', 'Accumulated Darkness cache'),
    'SpentShrinePointsCache': ('已投入热度缓存', 'Spent Heat cache'),
    'GameplayTime': ('本次挑战时间（秒）', 'Current-run time (seconds)'),
    'TotalRequiredEnemyKills': ('必要敌人击杀数', 'Required enemy kills'),
    'RecordClearedShrineThreshold': ('各兵器与首领的热度纪录', 'Heat records by weapon and boss chamber'),
    'RecordLastClearedShrineReward': ('各兵器与首领的热度奖励记录', 'Heat reward records by weapon and boss chamber'),
    'ClearedWithMetaUpgrades': ('成功逃脱时的圣镜等级纪录', 'Mirror rank records on escape'),
    'EncountersOccurredCache': ('遭遇发生次数缓存', 'Encounter occurrence count cache'),
    'EncountersCompletedCache': ('遭遇完成次数缓存', 'Encounter completion count cache'),
    'EndingRoomName': ('结束房间', 'Ending chamber'), 'EndingMoney': ('结束时金币', 'Ending Obol'),
    'WeaponsCache': ('兵器记录', 'Recorded weapons'), 'TraitCache': ('祝福记录', 'Recorded boons'),
    'MetaUpgradeCache': ('圣镜记录', 'Recorded Mirror talents'), 'RunDepthCache': ('挑战深度缓存', 'Run depth cache'),
    'RoomCountCache': ('房间计数缓存', 'Chamber count cache'), 'BiomeDepthCache': ('区域深度缓存', 'Biome depth cache'),
    'MetaPointsCache': ('黑暗记录', 'Recorded Darkness'), 'ShrinePointsCache': ('热度记录', 'Recorded Heat'),
    'EndingKeepsakeName': ('结束时信物', 'Ending keepsake'),
    'ActiveMutators': ('已启用挑战条件', 'Active challenge conditions'),
    'HardMode': ('地狱模式', 'Hell Mode'), 'FistUnlocked': ('拳套解锁剧情标志', 'Twin Fists unlock story flag'),
    'GunUnlocked': ('坚炮解锁剧情标志', 'Adamant Rail unlock story flag'),
    'AspectsUnlocked': ('形态解锁剧情标志', 'Aspect unlock story flag'),
    'EasyModeLevel': ('神力模式累计强度', 'Accumulated God Mode strength'),
    'TargetShrinePointThreshold': ('挑战目标热度', 'Target Heat threshold'),
    'SquelchedHermes': ('已关闭赫尔墨斯对白', 'Hermes dialogue silenced'),
    'RunClearMessage': ('逃脱结果消息', 'Escape result message'),
    'timestamp': ('保存时间戳', 'Save timestamp'), 'location': ('保存地点', 'Save location'),
    'completed_runs': ('挑战次数 · 文件头', 'Run count · file header'),
    'accumulated_meta_points': ('黑暗累计值 · 文件头', 'Accumulated Darkness · file header'),
    'active_shrine_points': ('热度 · 文件头', 'Heat · file header'),
    'easy_mode': ('神力模式 · 文件头', 'God Mode · file header'),
    'hard_mode': ('地狱模式 · 文件头', 'Hell Mode · file header'),
    'notable_lua_data': ('摘要标签 · 文件头', 'Summary labels · file header'),
    'map_name': ('当前地图 · 文件头', 'Current map · file header'),
    'next_map_name': ('下一地图 · 文件头', 'Next map · file header'),
}
_NAMES = {**trait_names(), **_CATALOG['names']}
for _resource in resource_catalog('en'):
    _NAMES[_resource['id']] = _resource['names']
_HEADER_PROJECTIONS = {'CompletedRunsCache': 'completed_runs',
                       'AccumulatedMetaPointsCache': 'accumulated_meta_points',
                       'SpentShrinePointsCache': 'active_shrine_points'}


def label(key, language):
    if isinstance(key, str) and key in _NAMES: return _NAMES[key][language]
    if isinstance(key, str) and key in _PAIRS: return _PAIRS[key][0 if language == 'zh-CN' else 1]
    return values.display(key)


def warning(language, known=False):
    if known:
        return ('直接修改保存的数值；游戏之后重新计算缓存时可能覆盖此值。' if language == 'zh-CN' else
                'Edits the stored value directly. A later native cache recalculation may replace it.')
    return ('此字段的完整游戏影响尚未确认；将按所选类型和物理位置写入。' if language == 'zh-CN' else
            'The complete gameplay impact is unknown. This writes the selected type and physical occurrence.')


def scene(keys):
    return (_CATALOG['scenes'].get(keys[1]) if len(keys) >= 2 and keys[0] == 'TextLinesRecord'
            and isinstance(keys[1], str) else None)


def logical(document, keys):
    current = document.lua_state
    for key in keys:
        if not isinstance(current, LuaTable):
            raise ValueError('A native semantic owner is a scalar; repair its typed value in Advanced.')
        current = current[key]
    return current


def physical(document, keys):
    current, path = document.lua_state, (0,)
    for key in keys:
        if not isinstance(current, LuaTable):
            raise ValueError('A native semantic owner is a scalar; repair its typed value in Advanced.')
        index = current._index(key)
        if index is None: raise KeyError(key)
        path += (index * 2 + 1,)
        current = current.entries()[index][1]
    return path


def _logical_set(document, keys, value):
    owner = document.lua_state
    for key in keys[:-1]:
        if not isinstance(owner, LuaTable): raise ValueError('A linked semantic owner is not a table.')
        child = owner.get(key)
        if child is None:
            child = LuaTable()
            owner[key] = child
        owner = child
    if not isinstance(owner, LuaTable): raise ValueError('A linked semantic owner is not a table.')
    owner[keys[-1]] = value


def _address(document, keys):
    for count in range(len(keys), -1, -1):
        try: return physical(document, keys[:count]) + tuple('new:' + repr(key) for key in keys[count:])
        except KeyError: continue


class HadesSaveWorkspace:
    def __init__(self, session):
        self.session = session
        self.identifier = uuid.uuid4().hex
        self.pending = {}
        self.baseline_generation = uuid.uuid4().hex

    @property
    def document(self): return self.session.document

    def _identifier(self, path): return values.identifier(path, self.baseline_generation)

    def _parse_id(self, identifier): return values.parse_id(identifier, self.baseline_generation)

    def _require_generation(self, generation):
        if generation != self.baseline_generation:
            raise ValueError('This control belongs to an earlier document baseline. Refresh the editor before editing.')

    @staticmethod
    def inventory(service, snapshot_id=None):
        sources = service.source_files(snapshot_id)
        choices = editor_files(sources)
        defaults = []
        for item in sources:
            if item.relative_path == 'activeProfile':
                _, raw = service.read_source_file(item.root_id, item.relative_path, snapshot_id)
                profile = active_profile_bytes(raw)
                identity = {'rootId': item.root_id, 'relativePath': str(profile) + '.sav'}
                if identity in [{key: row[key] for key in ('rootId', 'relativePath')} for row in choices]:
                    defaults.append(identity)
        return {'sources': choices, 'targets': editor_files(service.resolved_files()),
                'defaultSource': defaults[0] if len(defaults) == 1 else None}

    @classmethod
    def open(cls, service, *, snapshot_id=None, source=None, target=None):
        inventory = cls.inventory(service, snapshot_id)
        if source is None: source = inventory['defaultSource']
        if not isinstance(source, dict) or set(source) != {'rootId', 'relativePath'}:
            raise ValueError('Choose one physical Hades save document to open.')
        session = HadesSaveEditSession.open(service, source['relativePath'], root_id=source['rootId'],
            snapshot_id=snapshot_id, target=target, default_target=False, version_pinned=True)
        return cls(session)

    def summary(self, language='en'):
        return {'workspaceId': self.identifier, 'baselineGeneration': self.baseline_generation, 'source': self.session.source,
                'sourceSHA256': self.session.source_sha256, 'target': self.session.target,
                'domains': list(DOMAINS), 'review': self.review(language),
                'recoveryPath': self.session.recovery_path}

    def set_target(self, target, *, baseline_generation):
        self._require_generation(baseline_generation)
        self.session.set_target(target)
        return self.summary()

    def _row(self, path, keys, language, *, full=False, key_row=False):
        node = values.resolve(self.document, path)
        purpose = ordinary_purpose(keys, _CATALOG)
        def purpose_label(selected):
            if isinstance(purpose, tuple): return purpose[0 if selected == 'zh-CN' else 1]
            return label(purpose if purpose is not None else keys[-1], selected) if keys else ('保存的全局状态' if selected == 'zh-CN' else 'Saved globals')
        name = purpose_label(language)
        if key_row: name += ' · ' + ('键' if language == 'zh-CN' else 'key')
        group = label(keys[-2], language) if len(keys) > 1 else ('全局状态' if language == 'zh-CN' else 'Global state')
        kind = values.typed(node)['luaType'] if not isinstance(node, LuaTable) else 'table'
        operations = ['set']
        if path != (0,): operations.append('unset')
        if isinstance(node, LuaTable): operations.append('append')
        result = {'id': self._identifier(path), 'baselineGeneration': self.baseline_generation, 'name': name, 'englishName': purpose_label('en'),
                  'group': group, 'owner': ' › '.join(label(key, language) for key in keys[:-1]),
                  'ownerId': self._identifier(path[:-1]) if len(path) > 1 else 'root:' + str(path[0]),
                  'groupId': self._identifier(path[:-1]) if len(path) > 1 else 'root:' + str(path[0]),
                  'valueType': kind, 'displayValue': values.display(node), 'editable': True,
                  'hasChildren': isinstance(node, LuaTable), 'operations': operations,
                  'warning': warning(language, bool(keys and isinstance(keys[-1], str) and
                      ('Cache' in keys[-1] or tuple(keys) in NATIVE_OWNERS['statistics'])))}
        for root, entity_depth in ENTITY_DEPTHS.items():
            if len(keys) >= entity_depth and tuple(keys[:len(root)]) == root:
                entity_path = path[:entity_depth + 1]
                result.update(owner=label(keys[entity_depth - 1], language), ownerId=self._identifier(entity_path),
                              group=label(keys[-2] if len(keys) > entity_depth + 1 else root[-1], language),
                              groupId=self._identifier(path[:-1] if len(keys) > entity_depth + 1 else entity_path))
                break
        narrative = scene(keys)
        if narrative and len(keys) == 2 and not key_row:
            result.update(name='已发生' if language == 'zh-CN' else 'Played', englishName='Played',
                          owner=label(narrative['owner'], language) if narrative['owner'] else narrative['content'][language][0]['speaker'],
                          group=label('TextLinesRecord', language), content=narrative['content'][language])
        if full or not isinstance(node, LuaTable): result['typedValue'] = values.typed(node)
        return result

    def _logical_keys(self, path):
        current, keys = self.document.lua_values[path[0]], []
        for token in path[1:]:
            key, item = current.entries()[token // 2]
            keys.append(key)
            current = (key, item)[token % 2]
        return keys

    def _header_row(self, name, language, *, full=False):
        node = getattr(self.document.header, name)
        if name == 'notable_lua_data':
            node = LuaTable(len(node), 0, enumerate(node, 1))
        elif name == 'timestamp': node = str(node)
        return {'id': 'h:' + name, 'baselineGeneration': self.baseline_generation, 'name': label(name, language), 'englishName': label(name, 'en'),
                'group': '文件头' if language == 'zh-CN' else 'File header', 'owner': 'SGB1',
                'ownerId': 'header', 'groupId': 'header',
                'valueType': 'table' if isinstance(node, LuaTable) else values.typed(node)['luaType'],
                'displayValue': values.display(node), 'typedValue': values.typed(node),
                'editable': True, 'hasChildren': False, 'operations': ['set'], 'warning': warning(language)}

    def _semantic_rows(self, domain, language):
        rows = []
        if domain == 'resources':
            try: owner = logical(self.document, ('GameState', 'Resources'))
            except KeyError: owner = LuaTable()
            except ValueError: owner = None
            if isinstance(owner, LuaTable):
                for item in resource_catalog(language):
                    try: amount = owner.get(item['id'], 0)
                    except AmbiguousKeyError: continue
                    if type(amount) is bool or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0 or int(amount) != amount:
                        continue
                    rows.append({'id': 'resource:' + item['id'], 'name': item['name'],
                        'englishName': item['names']['en'], 'group': label('Resources', language),
                        'owner': item['name'], 'valueType': 'number', 'displayValue': values.display(amount),
                        'typedValue': values.typed(amount), 'editable': True, 'hasChildren': False,
                        'operations': ['set'], 'constraints': {'min': 0, 'max': 9007199254740991, 'integer': True},
                        'warning': ('直接设置库存；累计获得、消耗和赠礼事件保持为独立记录。' if language == 'zh-CN' else
                                    'Sets the balance directly. Lifetime gains, spending and gift events are separate records.')})
        if domain == 'progression':
            for index, names in enumerate(_CATALOG['mirrorRows'], 1):
                try:
                    owner = logical(self.document, ('GameState', 'MetaUpgradesUnlocked'))
                    if not isinstance(owner, LuaTable): continue
                    unlocked = all(owner.get(name) is True for name in names)
                except KeyError:
                    try: logical(self.document, ('GameState',))
                    except (KeyError, ValueError): continue
                    unlocked = False
                except ValueError: continue
                name = ' / '.join(label(name, language) for name in names)
                rows.append({'id': 'mirror:' + str(index), 'name': name,
                    'englishName': ' / '.join(label(name, 'en') for name in names),
                    'group': '夜之圣镜 · 成对天赋解锁' if language == 'zh-CN' else 'Mirror · paired talent unlocks',
                    'owner': '夜之圣镜' if language == 'zh-CN' else 'Mirror of Night',
                    'valueType': 'boolean', 'displayValue': values.display(unlocked), 'typedValue': values.typed(unlocked),
                    'editable': True, 'hasChildren': False, 'operations': ['set'],
                    'warning': ('直接设置成对解锁状态；资源消耗与剧情资格保持为独立记录。' if language == 'zh-CN' else
                                'Sets the paired unlock state. Resource spending and story eligibility are separate records.')})
        if domain == 'equipment':
            for weapon, aspects in _CATALOG['weapons'].items():
                try:
                    owner = logical(self.document, ('GameState', 'LastWeaponUpgradeData'))
                    if not isinstance(owner, LuaTable): continue
                    last = owner.get(weapon)
                    selected = last.get('Index', 1) if isinstance(last, LuaTable) else 1
                except KeyError:
                    try: logical(self.document, ('GameState',))
                    except (KeyError, ValueError): continue
                    selected = 1
                except ValueError: continue
                choices = [{'name': label(item['trait'], language) or str(item['index']),
                            'value': values.typed(item['index'])} for item in aspects]
                base = {'group': label(weapon, language), 'owner': label('LastWeaponUpgradeData', language),
                        'editable': True, 'hasChildren': False, 'operations': ['set'], 'valueType': 'number',
                        'warning': ('修改下次装备使用的形态记录；当前挑战角色的兵器和效果可在下方单独编辑。' if language == 'zh-CN' else
                                    'Edits the aspect used on next equip. Current-run weapons and traits are separately editable below.')}
                rows.append({**base, 'id': 'aspectSelection:' + weapon,
                    'name': label(weapon, language) + (' · 下次装备形态' if language == 'zh-CN' else ' · next-equip aspect'),
                    'englishName': label(weapon, 'en') + ' · next-equip aspect',
                    'displayValue': values.display(selected), 'typedValue': values.typed(selected), 'choices': choices})
                for item in aspects:
                    try:
                        owner = logical(self.document, ('GameState', 'WeaponUnlocks'))
                        if not isinstance(owner, LuaTable): continue
                        ranks = owner.get(weapon)
                    except KeyError: ranks = None
                    except ValueError: continue
                    try: rank = ranks.get(item['index'], 0) if isinstance(ranks, LuaTable) else 0
                    except AmbiguousKeyError: continue
                    if type(rank) is bool or not isinstance(rank, (int, float)) or not math.isfinite(rank): continue
                    rows.append({**base, 'id': 'aspectRank:' + weapon + ':' + str(item['index']),
                        'name': label(item['trait'], language), 'englishName': label(item['trait'], 'en'),
                        'displayValue': values.display(rank), 'typedValue': values.typed(rank),
                        'constraints': {'min': 0, 'max': item['maxRank'], 'integer': True}})
        for row in rows:
            identifier = row['id']
            owner = ('weapon:' + identifier.split(':')[1] if identifier.startswith(('aspectRank:', 'aspectSelection:')) else identifier)
            row.update(ownerId=owner, groupId=owner, baselineGeneration=self.baseline_generation)
        return rows

    def _domain_roots(self, domain):
        if domain == 'advanced':
            return [((index,), []) for index in range(len(self.document.lua_values))]
        result = []
        for keys in NATIVE_OWNERS[domain]:
            try: result.append((physical(self.document, keys), list(keys)))
            except (KeyError, ValueError): continue
        return result

    def query(self, domain='resources', language='en', query='', parentId=None, offset=0, limit=100):
        if domain not in DOMAINS or language not in ('en', 'zh-CN') or not isinstance(query, str):
            raise ValueError('Invalid editor domain, language or query.')
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Invalid editor page.')
        rows, breadcrumbs = [], []
        if parentId is not None:
            path = self._parse_id(parentId)
            owner = values.resolve(self.document, path)
            if not isinstance(owner, LuaTable): raise ValueError('Open a table to browse its fields.')
            keys = self._logical_keys(path)
            if domain != 'advanced' and ordinary_purpose(keys, _CATALOG) is None:
                raise ValueError('This field has no ordinary purpose descriptor. Open its typed occurrence in Advanced.')
            for depth in range(1, len(path) + 1):
                crumb = path[:depth]
                crumb_keys = self._logical_keys(crumb)
                breadcrumbs.append({'id': self._identifier(crumb), 'name': label(crumb_keys[-1], language) if crumb_keys else 'Lua'})
            roots, max_depth = [(path, keys)], 1
        else:
            roots, max_depth = self._domain_roots(domain), 2 if domain != 'advanced' else 1
            rows.extend(self._semantic_rows(domain, language))
            if domain == 'advanced': rows.extend(self._header_row(field.name, language) for field in fields(self.document.header))

        def walk(path, keys, depth):
            node = values.resolve(self.document, path)
            if domain != 'advanced' and ordinary_purpose(keys, _CATALOG) is None: return
            if depth == 0 and parentId is None: rows.append(self._row(path, keys, language))
            if not isinstance(node, LuaTable): return
            for index, (key, item) in enumerate(node.entries()):
                child = path + (index * 2 + 1,)
                child_keys = [*keys, key]
                if domain != 'advanced' and ordinary_purpose(child_keys, _CATALOG) is None: continue
                if not (parentId is None and domain == 'resources' and keys == ['GameState', 'Resources']
                        and type(key) is str and any(row['id'] == 'resource:' + key for row in rows)):
                    row = self._row(child, child_keys, language)
                    if domain == 'advanced':
                        row['owner'] = label(key, language) + (' · ' + str(index + 1) if domain == 'advanced' else '')
                        row['ownerId'] = self._identifier(child)
                    rows.append(row)
                if domain == 'advanced':
                    key_row = self._row(path + (index * 2,), child_keys, language, key_row=True)
                    key_row['owner'] = label(key, language) + ' · ' + str(index + 1)
                    key_row['ownerId'] = self._identifier(child)
                    rows.append(key_row)
                    if isinstance(key, LuaTable) and (query or depth + 1 < max_depth):
                        walk(path + (index * 2,), child_keys, depth + 1)
                if isinstance(item, LuaTable) and (query or depth + 1 < max_depth):
                    walk(child, child_keys, depth + 1)

        for path, keys in roots: walk(path, keys, 0)
        words = query.casefold().split()
        if words:
            matches = set()
            for row in rows:
                identifier = row['id']
                keys = self._logical_keys(self._parse_id(identifier)) if identifier.startswith('p:') else []
                if identifier.startswith('mirror:'): keys = _CATALOG['mirrorRows'][int(identifier.split(':')[1]) - 1]
                elif identifier.startswith(('aspectSelection:', 'aspectRank:')):
                    keys = [identifier.split(':')[1]]
                    if identifier.startswith('aspectRank:'):
                        keys.append(_CATALOG['weapons'][keys[0]][int(identifier.split(':')[2]) - 1]['trait'])
                elif identifier.startswith(('h:', 'resource:')): keys = [identifier.split(':')[1]]
                content = scene(keys) if 'content' in row else None
                searchable = [row['name'], row['englishName'], row['owner'], row['group'], row['displayValue'],
                              *(label(key, language) for language in ('zh-CN', 'en') for key in keys)]
                purpose = ordinary_purpose(keys, _CATALOG)
                if isinstance(purpose, tuple): searchable.extend(purpose)
                if content:
                    searchable.extend(part for lines in content['content'].values() for line in lines
                                      for part in (line['speaker'], line['text']))
                searchable = ' '.join(searchable).casefold()
                if all(word in searchable for word in words): matches.add(row['ownerId'])
            rows = [row for row in rows if row['ownerId'] in matches]
        # Domains may intentionally include the same owner through multiple roots.
        unique = {row['id']: row for row in rows}
        rows = list(unique.values())
        groups = {}
        for row in rows: groups.setdefault(row['ownerId'], []).append(row)
        selected, cursor, start = [], 0, offset
        for group in groups.values():
            end = cursor + len(group)
            if end > offset and len(selected) < limit:
                if not selected: start = cursor
                selected.extend(group)
            cursor = end
        return {'workspaceId': self.identifier, 'baselineGeneration': self.baseline_generation, 'rows': selected, 'total': len(rows),
                'offset': start, 'limit': len(selected), 'nextOffset': start + len(selected),
                'parentId': parentId, 'breadcrumbs': breadcrumbs}

    def detail(self, entry_id, language='en'):
        if not isinstance(entry_id, str) or language not in ('en', 'zh-CN'):
            raise ValueError('Invalid editor entry or language.')
        if entry_id.startswith('h:'):
            if entry_id[2:] not in {item.name for item in fields(self.document.header)}:
                raise ValueError('Unknown native header field.')
            row = self._header_row(entry_id[2:], language, full=True)
        elif entry_id.startswith('p:'):
            path = self._parse_id(entry_id)
            row = self._row(path, self._logical_keys(path), language, full=True,
                            key_row=len(path) > 1 and path[-1] % 2 == 0)
        else:
            row = next((row for domain in ('resources', 'progression', 'equipment') for row in self._semantic_rows(domain, language)
                        if row['id'] == entry_id), None)
            if row is None: raise ValueError('Editor entry does not exist.')
        return {'row': row}

    def stage(self, entry_id, operation, value=None, language='en', *, baseline_generation):
        self._require_generation(baseline_generation)
        row = self.detail(entry_id, language)['row']
        if operation not in row['operations']: raise ValueError('This operation is unavailable for the selected entry.')
        intent = {'id': entry_id, 'operation': operation, 'value': value, 'baselineGeneration': baseline_generation}
        candidate = {**self.pending, entry_id: intent}
        _, review = self._plan(tuple(candidate.values()), language)
        planned = {action['id'] for action in review['actions']}
        candidate = {key: value for key, value in candidate.items() if key in planned}
        if operation == 'set' and value == row.get('typedValue'):
            candidate.pop(entry_id, None)
        self.pending = candidate
        return self.review(language)

    def unstage(self, entry_id, language='en', *, baseline_generation):
        self._require_generation(baseline_generation)
        candidate = {key: value for key, value in self.pending.items() if key != entry_id}
        self._plan(candidate.values(), language)
        self.pending = candidate
        return self.review(language)

    def cancel(self, language='en', *, baseline_generation):
        self._require_generation(baseline_generation)
        self.pending.clear()
        return self.review(language)

    def _plan(self, intents, language):
        for intent in intents: self._require_generation(intent['baselineGeneration'])
        candidate = self.document.clone()
        writes, actions = [], []

        def add(intent, address, before, after, name, *, path=None, logical_keys=None, header=None, operation='set', wire=None):
            if operation == 'set' and values.equal(before, after): return
            effect = {'id': ('h:' + header if header else self._identifier(path) if path else 'linked:' + repr(logical_keys)),
                      'name': name, 'before': values.display(before), 'after': values.display(after)}
            writes.append({'action': intent['id'], 'address': address, 'before': before, 'after': after,
                           'path': path, 'logical': logical_keys, 'header': header, 'operation': operation,
                           'wire': wire, 'effect': effect})

        def linked(intent, keys, after, name):
            try: before = logical(self.document, keys)
            except KeyError: before = None
            add(intent, _address(self.document, keys), before, after, name, logical_keys=keys)

        for intent in intents:
            identifier, operation, wire = intent['id'], intent['operation'], intent['value']
            row = self.detail(identifier, language)['row']
            if operation not in row['operations']: raise ValueError('Staged operation no longer matches its entry.')
            start = len(writes)
            if identifier.startswith('p:'):
                path = self._parse_id(identifier)
                before = values.resolve(self.document, path)
                after = values.from_typed(wire) if operation == 'set' else None
                add(intent, path, before, after, row['name'], path=path, operation=operation, wire=wire)
                keys = self._logical_keys(path)
                if operation == 'set' and path[-1] % 2 == 1 and len(keys) == 2 and keys[0] == 'GameState' and keys[1] in _HEADER_PROJECTIONS:
                    field = _HEADER_PROJECTIONS[keys[1]]
                    # This is the proven non-overflowing native double->int32
                    # projection. Other encoded Lua types stay editable with
                    # the ordinary unknown-impact warning.
                    if type(after) is not bool and isinstance(after, (int, float)) and math.isfinite(after) and 0 <= after <= 0x7fffffff and int(after) == after:
                        add(intent, ('header', field), getattr(self.document.header, field), int(after), label(field, language), header=field)
            elif identifier.startswith('h:'):
                field = identifier[2:]
                if field not in {item.name for item in fields(self.document.header)}: raise ValueError('Unknown native header field.')
                after = values.from_typed(wire)
                original = getattr(self.document.header, field)
                before = original
                if field == 'timestamp':
                    if not isinstance(after, str) or not after.isdigit() or not 0 <= int(after) <= 0xffffffffffffffff:
                        raise ValueError('Timestamp requires an unsigned 64-bit decimal string.')
                    after, before = after, str(before)
                elif field == 'notable_lua_data':
                    before = LuaTable(len(original), 0, enumerate(original, 1))
                    if (not isinstance(after, LuaTable)
                            or any(type(key) is bool or not isinstance(key, (int, float)) or key != index
                                   or not isinstance(item, str) for index, (key, item) in enumerate(after.entries(), 1))):
                        raise ValueError('Native summary labels require an ordered 1-based string table.')
                elif isinstance(original, str):
                    if not isinstance(after, str): raise ValueError('Native header string requires a typed string.')
                elif type(after) is bool or not isinstance(after, (int, float)) or not math.isfinite(after) or int(after) != after or not 0 <= after <= (255 if field in ('easy_mode', 'hard_mode') else 0xffffffff):
                    raise ValueError('Native header integer is outside its encoded range.')
                add(intent, ('header', field), before, after, row['name'], header=field)
            elif identifier.startswith('resource:'):
                after = values.from_typed(wire)
                if (type(after) is bool or not isinstance(after, (int, float)) or not math.isfinite(after)
                        or not 0 <= after <= 9007199254740991 or int(after) != after):
                    raise ValueError('Resource balance requires an exactly representable nonnegative integer.')
                linked(intent, ('GameState', 'Resources', identifier.split(':')[1]), after, row['name'])
            elif identifier.startswith('mirror:'):
                after = values.from_typed(wire)
                if type(after) is not bool: raise ValueError('Mirror row unlock requires a boolean.')
                names = _CATALOG['mirrorRows'][int(identifier.split(':')[1]) - 1]
                for name in names:
                    linked(intent, ('GameState', 'MetaUpgradesUnlocked', name), after, label(name, language))
            elif identifier.startswith(('aspectSelection:', 'aspectRank:')):
                parts = identifier.split(':')
                weapon, after = parts[1], values.from_typed(wire)
                aspects = _CATALOG['weapons'][weapon]
                index = int(after) if parts[0] == 'aspectSelection' and type(after) is not bool and isinstance(after, (int, float)) and math.isfinite(after) else (int(parts[2]) if len(parts) == 3 else 0)
                if index < 1 or index > len(aspects): raise ValueError('Choose one native weapon aspect.')
                aspect = aspects[index - 1]
                if type(after) is bool or not isinstance(after, (int, float)) or not math.isfinite(after) or int(after) != after:
                    raise ValueError('Aspect selection/rank requires an integer.')
                if parts[0] == 'aspectRank':
                    if not 0 <= after <= aspect['maxRank']: raise ValueError('Aspect rank exceeds its native range.')
                    linked(intent, ('GameState', 'WeaponUnlocks', weapon, index), after, row['name'])
                    try: old_rank = logical(self.document, ('GameState', 'WeaponUnlocks', weapon, index))
                    except KeyError: old_rank = None
                    newly_unlocked = old_rank is None and after > 0
                else: newly_unlocked = True
                if newly_unlocked:
                    linked(intent, ('GameState', 'LastWeaponUpgradeData', weapon, 'Index'), index, label('LastWeaponUpgradeData', language))
                    linked(intent, ('GameState', 'LastInteractedWeaponUpgrade', 'WeaponName'), weapon, label('LastInteractedWeaponUpgrade', language))
                    linked(intent, ('GameState', 'LastInteractedWeaponUpgrade', 'ItemIndex'), index, label('Index', language))
            else: raise ValueError('Unknown staged editor identity.')
            if len(writes) == start: continue
            actions.append({'id': identifier, 'name': row['name'], 'before': row['displayValue'],
                'after': (values.display(values.from_typed(wire)) if operation == 'set' else '∅' if operation == 'unset' else
                          '+ ' + values.display(values.from_typed(wire['key'])) + ': ' + values.display(values.from_typed(wire['value']))),
                'operation': operation, 'valueType': row['valueType'],
                'typedValue': wire['value'] if operation == 'append' else wire,
                **({'typedKey': wire['key']} if operation == 'append' else {}),
                'effects': [write['effect'] for write in writes[start:] if write['effect']['id'] != identifier
                            and not (identifier.startswith(('resource:', 'aspectRank:')) and write['effect']['name'] == row['name'])]})

        unique = []
        for write in writes:
            for previous in unique:
                if previous['action'] == write['action']: continue
                left, right = previous['address'], write['address']
                overlap = left[:len(right)] == right or right[:len(left)] == left
                if len(left) == len(right) and len(left) > 1 and left[:-1] == right[:-1] and type(left[-1]) is int and type(right[-1]) is int:
                    overlap |= left[-1] // 2 == right[-1] // 2
                if overlap:
                    if left == right and previous['operation'] == write['operation'] == 'set' and values.equal(previous['after'], write['after']):
                        break
                    raise ValueError('These staged actions overlap one physical owner. Revise or remove one action in Changes.')
            else:
                unique.append(write)

        # Descending original occurrence paths preserve sibling identities when
        # a batch removes entries. Semantic additions follow existing entries.
        for write in sorted((item for item in unique if item['path'] is not None), key=lambda item: item['path'], reverse=True):
            values.mutate(candidate, write['path'], write['operation'], write['wire'])
        for write in unique:
            if write['logical'] is not None: _logical_set(candidate, write['logical'], write['after'])
            if write['header']:
                field, after = write['header'], write['after']
                if field == 'timestamp': after = int(after)
                elif field == 'notable_lua_data': after = tuple(item for _, item in after.entries())
                elif not isinstance(after, str): after = int(after)
                setattr(candidate.header, field, after)
        for intent in intents:
            if intent['id'].startswith('aspectSelection:'):
                weapon = intent['id'].split(':')[1]
                index = int(values.from_typed(intent['value']))
                aspect = _CATALOG['weapons'][weapon][index - 1]
                if not aspect['startsUnlocked']:
                    try: rank = logical(candidate, ('GameState', 'WeaponUnlocks', weapon, index))
                    except KeyError: rank = 0
                    if not isinstance(rank, (int, float)) or type(rank) is bool or rank <= 0:
                        raise ValueError('Unlock or rank this aspect before selecting it; its rank can be staged in the same batch.')
        projections = [(('GameState', key), field) for key, field in _HEADER_PROJECTIONS.items()]
        projections.append((('GameState', 'Flags', 'HardMode'), 'hard_mode'))
        for keys, field in projections:
            try: before = logical(self.document, keys)
            except (KeyError, ValueError): before = None
            try: after = logical(candidate, keys)
            except (KeyError, ValueError): continue
            if values.equal(before, after): continue
            if field == 'hard_mode':
                if type(after) is not bool: continue
                projected = int(after)
            else:
                if (type(after) is bool or not isinstance(after, (int, float)) or not math.isfinite(after)
                        or int(after) != after or not 0 <= after <= 0x7fffffff): continue
                projected = int(after)
            address = _address(self.document, keys)
            owners = [write for write in unique if write['header'] is None and
                      (write['address'][:len(address)] == address or address[:len(write['address'])] == write['address'])]
            if not owners: continue
            owner = owners[0]['action']
            existing = next((write for write in unique if write['header'] == field), None)
            if existing is not None:
                if int(existing['after']) != projected:
                    raise ValueError('A staged header edit conflicts with the native cache/mode projection. Revise one action.')
                continue
            old_header = getattr(candidate.header, field)
            setattr(candidate.header, field, projected)
            if old_header != projected:
                action = next(action for action in actions if action['id'] == owner)
                action['effects'].append({'id': 'h:' + field, 'name': label(field, language),
                    'before': str(old_header), 'after': str(projected)})
        HadesSaveDocument.from_bytes(candidate.to_bytes())
        return candidate, {'baselineGeneration': self.baseline_generation, 'actions': actions, 'count': len(actions),
                           'effectCount': sum(len(action['effects']) for action in actions)}

    def review(self, language='en'):
        if language not in ('en', 'zh-CN'): raise ValueError('Unsupported editor language.')
        return self._plan(tuple(self.pending.values()), language)[1]

    def apply(self, *, baseline_generation):
        self._require_generation(baseline_generation)
        if not self.pending: raise ValueError('There are no staged changes to apply.')
        candidate, _ = self._plan(tuple(self.pending.values()), 'en')
        original = self.session.document
        self.session.document = candidate
        try:
            result = self.session.apply()
        except BaseException:
            self.session.document = original
            raise
        self.pending.clear()
        self.baseline_generation = uuid.uuid4().hex
        return {**result, 'baselineGeneration': self.baseline_generation, 'verified': True, 'workspaceId': self.identifier,
                'source': self.session.source, 'target': self.session.target,
                'sourceSHA256': self.session.source_sha256,
                'installedSHA256': self.session.original_sha256}
