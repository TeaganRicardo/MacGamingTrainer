"""Hades II player-facing error identity.

A user-facing failure must be readable in every supported language, but the
backend does not know the Host language. So a Hades-owned failure carries a
stable presentation *key* on the wire; the shipped bilingual tables
(`Sources/Hades2/Presentation/Localization/hades2.<lang>.json`) own the wording and
the Host resolves the key when it renders the message.

This is exactly the B02 split: `code` stays the stable machine identity,
`presentation` becomes a language-neutral key, and `diagnostic` keeps the
operator-readable detail. Core never learns a Hades term.

The Chinese text that used to be the raised message is retained as the
authoritative source for each key and is still surfaced through the diagnostic,
so the operator trace is unchanged while the wire stops being localized.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from core.adapter import AdapterError


@dataclass(frozen=True)
class Hades2PresentationKey:
    """A language-neutral player-facing message identity.

    `key` resolves in every shipped language. `arguments` fill its `{n}`
    placeholders and are runtime values, not copy: a game display name, a
    process name, or a raw tool error.
    """

    key: str
    arguments: Sequence[str] = field(default_factory=tuple)

    def render(self, template: str) -> str:
        """Fill this key's template with its arguments."""
        result = template
        for index, argument in enumerate(self.arguments):
            result = result.replace('{%d}' % index, argument)
        return result


class Hades2PresentationError(AdapterError):
    """A Hades failure whose player-facing value is a presentation key.

    `presentation` is the key and `diagnostic` keeps the readable text.
    `arguments` fills the key's `{n}` placeholders and travels alongside the
    key in the Core-owned `error.arguments` envelope field, so the Host can
    render the module's own sentence in the player's language.
    """

    def __init__(self, code, key, arguments=(), *, diagnostic=None):
        super().__init__(code, key, diagnostic=diagnostic)
        self.arguments = tuple(arguments)


# Raised message (pre-migration Chinese) -> presentation key.
#
# This is the migration record: it is the single place that knows which key
# replaced which literal, and the test suite asserts the table stays in step
# with the raised messages in the module. A message that is not listed here is
# not player-facing Hades copy and keeps its own value.
MESSAGE_KEYS = {
    # transport / connection
    '请先连接游戏。': 'hades2.error.notConnected',
    '游戏已退出或连接已断开。': 'hades2.error.notAttached',
    '游戏进程已结束。': 'hades2.error.processExited',
    '游戏进程已退出。': 'hades2.error.processExitedSecond',
    '游戏进程状态切换超时。': 'hades2.error.processTimeout',
    '无法在时限内暂停游戏。': 'hades2.error.pauseFailed',
    '游戏未能恢复运行。': 'hades2.error.resumeUnverified',
    '后台暂停标志尚未恢复，请保持连接重试断开。': 'hades2.error.focusNotRestored',
    '后台暂停标志恢复校验失败。': 'hades2.error.focusRestoreMismatch',
    '后台运行标志无法验证。': 'hades2.error.runFlagUnverifiable',
    '游戏发生非预期停顿，已停止当前操作。': 'hades2.error.unexpectedStop',
    '等待游戏世界更新超时。请进入存档并关闭暂停菜单后重试。': 'hades2.error.worldUpdateTimeout',
    '上次调用结果不明，请重启游戏后重新连接。': 'hades2.error.restartRequired',
    '无法定位游戏镜像。': 'hades2.error.imageNotFound',
    '游戏内操作失败，请查看日志。': 'hades2.error.runtimeActionFailed',
    'runtime observation 仅允许 status。': 'hades2.error.runtimeObservationOnly',
    '功能代码过长。': 'hades2.error.featureCodeTooLong',
    'Lua 执行失败': 'hades2.error.luaFailed',
    '游戏调用结果不明，未自动重试。': 'hades2.error.outcomeUnknownEmpty',
    '游戏调用结果不明，未自动重试；请检查游戏并重启。': 'hades2.error.outcomeUnknownGeneric',
    '无法读取操作结果；请检查游戏，不要重复资源操作。': 'hades2.error.outcomeUnknownUnreadable',

    # request / schema validation
    '未知命令。': 'hades2.error.invalidCommand',
    'command 无效。': 'hades2.error.invalidCommandValue',
    'params 必须是对象。': 'hades2.error.invalidParamsObject',
    '参数类型不支持。': 'hades2.error.invalidParamsObject',
    '请求 ID 无效。': 'hades2.error.invalidRequestId',
    '请求包含不可序列化的 JSON 值。': 'hades2.error.unserializableRequest',
    '同一请求 ID 的内容发生变化。': 'hades2.error.duplicateConflict',
    '未知功能。': 'hades2.error.unknownFeature',
    '开关值必须为布尔值。': 'hades2.error.featureToggleBoolean',
    '锁定值必须为布尔值。': 'hades2.error.lockedBoolean',
    '倍率必须为有限数值。': 'hades2.error.multiplierFinite',
    '倍率范围为 1–100。': 'hades2.error.multiplierRange',
    '游戏速度范围为 0–10。': 'hades2.error.gameSpeedRange',
    '必须输入有限数值。': 'hades2.error.statFinite',
    '属性值必须为有限数值。': 'hades2.error.statFinite',
    'probeRuntime 必须为布尔值。': 'hades2.error.probeRuntimeBoolean',

    # vitals / stats / elements
    '局内数值字段无效。': 'hades2.error.vitalField',
    '护甲仅提供当前值，不存在可编辑上限。': 'hades2.error.armorNoMaximum',
    '局内数值必须为 0–': 'hades2.error.vitalRange',
    '生命值必须至少为 1。': 'hades2.error.healthMinimum',
    '未知局内计数器。': 'hades2.error.unknownCounter',
    '巫咒充能必须为 0–': 'hades2.error.spellChargeRange',
    '未知局内数值。': 'hades2.error.unknownVital',
    '未知属性。': 'hades2.error.unknownStat',
    '未知元素。': 'hades2.error.unknownElement',
    '元素数量必须为 0–': 'hades2.error.elementRange',
    '数量必须是 0–': 'hades2.error.amountRange',
    '请选择资源。': 'hades2.error.selectResource',
    '请选择掉落物或祝福。': 'hades2.error.selectReward',
    '请选择支持原生奖励选择界面的角色。': 'hades2.error.selectChoiceSource',
    '最低稀有度无效。': 'hades2.error.invalidRarityTarget',
    '稀有度倍率必须为 0–1000%。': 'hades2.error.invalidRarityMultiplier',
    'Legendary / Duo 设置无效。': 'hades2.error.invalidLegendaryDuo',
    '下一房奖励无效。': 'hades2.error.invalidNextRoomReward',

    # lifecycle / preparation / persistence
    '请断开连接并退出游戏后操作。': 'hades2.error.disconnectBeforePrepare',
    '无法安全写入本地配置。': 'hades2.error.localWriteFailed',
    'desired-state schemaVersion 无效。': 'hades2.error.desiredSchemaInvalid',
    '原始备份损坏或与记录不匹配；拒绝覆盖游戏。': 'hades2.error.backupCorrupt',
    '备份 UUID 不匹配。': 'hades2.error.backupUUIDMismatch',
    '无法读取原始权限；未修改游戏。': 'hades2.error.permissionsUnreadable',
    '独立验证副本校验失败；未修改游戏。': 'hades2.error.verificationFailed',
    '原始恢复副本 UUID 不匹配；未修改游戏。': 'hades2.error.restoreUUIDMismatch',
    '暂存文件校验失败；未修改游戏。': 'hades2.error.stagedVerificationFailed',
    '游戏文件在操作期间改变；拒绝覆盖。': 'hades2.error.fileChangedDuringOperation',
    '调试签名校验失败；未修改游戏。': 'hades2.error.signingVerificationFailed',
    '已准备文件缺少调试权限。': 'hades2.error.missingDebugPermission',
    '当前可执行文件已带调试权限，但没有匹配的原始备份；拒绝覆盖。': 'hades2.error.noMatchingBackup',
    '没有与当前文件匹配的原始签名备份；游戏可能已更新，拒绝覆盖。': 'hades2.error.noOriginalBackup',

    '现有 desired-state 无法安全隔离，已禁止覆盖原文件。': 'hades2.error.preferenceWriteBlocked',
    '现有 desired-state 无法安全读取，已禁止本次进程覆盖原文件。': 'hades2.error.preferenceWriteBlocked',
    '损坏的 desired-state 无法安全隔离，已禁止覆盖原文件。': 'hades2.error.preferenceWriteBlocked',
    '使用新的数据格式': 'hades2.error.preferenceNewerFormat',

    # D01 current-run trait inventory / sell-safe removal
    '请选择要移除的祝福。': 'hades2.error.selectTraitToRemove',
    'Trait removal requires an active run room': 'hades2.error.traitRemovalNeedsRun',
    'Trait removal requires a trait name': 'hades2.error.traitRemovalNeedsName',
    'Native sell predicate is unavailable': 'hades2.error.sellPredicateUnavailable',

    # stat rules (schema.STAT_RULES)
    '悟性上限必须是 0–999 的整数。': 'hades2.error.graspRange',
    '概率必须为 0–100。': 'hades2.error.percentRange',
    '速度倍率必须为 10–1000%。': 'hades2.error.speedMultiplierRange',
    '额外魔力恢复必须为 0–1000/秒。': 'hades2.error.manaRegenRange',
    '敌人伤害倍率必须为 0–1000%。': 'hades2.error.enemyDamageRange',
    '敌人生命倍率必须为 10–1000%。': 'hades2.error.enemyHealthRange',

    # profiles
    'Profile schemaVersion 无效。': 'hades2.error.profileSchemaInvalid',
    'Profile desiredSchemaVersion 无效。': 'hades2.error.profileDesiredSchemaInvalid',
    'Profile 名称无效。': 'hades2.error.profileNameInvalid',
    'Profile 名称必须为 1–64 个可见字符。': 'hades2.error.profileNameLength',
    'Profile 名称不能包含路径分隔符。': 'hades2.error.profileNameSeparator',
    'Profile 文件已损坏。': 'hades2.error.profileCorrupt',
    'Profile 包含当前 schema 未定义的顶层字段。': 'hades2.error.profileUnknownFields',
    'Profile 名称未规范化。': 'hades2.error.profileNameNotNormalized',
    'Profile 名称与文件标识不一致。': 'hades2.error.profileNameIdentifierMismatch',
    'Profile desired 字段无效。': 'hades2.error.profileDesiredInvalid',
    'Profile updatedAt 字段无效。': 'hades2.error.profileUpdatedAtInvalid',
    'Profile updatedAt 字段缺失。': 'hades2.error.profileUpdatedAtMissing',
    'Profile shortcuts 字段无效。': 'hades2.error.profileShortcutsInvalid',
    '未找到该 Profile。': 'hades2.error.profileNotFound',

    # fallback
    '未知错误': 'hades2.error.unknownDetail',
}

# Messages built by interpolation: the prefix selects the key and the remainder
# becomes its runtime argument, so a tool error or process name is never baked
# into a localized sentence.
#
# A prefix must end exactly where the runtime value ends. A prefix that stops
# early drags the sentence's own static tail into the argument, which then
# renders as a hole-free but wrong value; a prefix that runs past the value
# cannot match at all. The source-derived contract test replays every real raise
# through this table, so a mismatched boundary fails there rather than in the UI.
PREFIX_KEYS = {
    'Trait is not sell-eligible, so no safe removal exists: ': 'hades2.error.traitNotSellEligible',
    'Trait removal is not proven safe: ': 'hades2.error.traitRemovalNotProven',
    'Trait is not present in the current run: ': 'hades2.error.traitNotPresent',
    'Native trait removal failed: ': 'hades2.error.traitRemovalFailed',
    '请先启动 ': 'hades2.error.gameNotRunning',
    '查询 ': 'hades2.error.processQueryFailed',
    '连接被拒绝：': 'hades2.error.attachDenied',
    '缺少符号：': 'hades2.error.missingSymbol',
    '新版本关键符号无法唯一定位：': 'hades2.error.symbolNotUnique',
    '新版本关键符号不可读：': 'hades2.error.symbolUnreadable',
    '运行中的游戏函数校验失败：': 'hades2.error.runtimeVerificationFailed',
    '无法恢复游戏运行：': 'hades2.error.resumeFailed',
    '后台暂停标志恢复失败：': 'hades2.error.focusRestoreFailed',
    '请先退出 ': 'hades2.error.prepareWhileRunning',
    '无法运行 ': 'hades2.error.commandLaunchFailed',
    '游戏调用结果不明，未自动重试：': 'hades2.error.outcomeUnknownTransport',
    '未经验证的游戏版本：': 'hades2.error.unverifiedBuildWarning',
    '未从本机 ': 'hades2.error.missingOfficialNames',
}

# Messages whose interpolated value sits *inside* the sentence, so neither a
# whole-message nor a prefix rule can isolate it.
#
# A leading-space prefix such as `' 适配器需要 '` looks correct in isolation but
# never matches: `startswith` anchors at position 0, and the real message leads
# with the game display name (`transport.py`). A value-leading prefix such as
# `'使用了更新的数据格式'` fails the same way for the opposite reason. Both used
# to fall through to a raw Chinese message on the wire.
#
# Each entry is a pattern anchored to the whole message whose groups are the
# arguments, in template order. Anchoring matters: a pattern that matches only
# part of the sentence would again absorb the static tail into an argument.
REGEX_KEYS = (
    # `f'{GAME_SPEC.display_name} 适配器需要 {requirement} 原生游戏。'`
    (re.compile(r'^(?P<game>.+?) 适配器需要 (?P<requirement>.+?) 原生游戏。$'),
     'hades2.error.architectureRequired'),
    # transport.py: `'连接被拒绝：' + detail + '。退出游戏后…'` — the OS error
    # sits between the prefix and a second, static sentence, so a plain prefix
    # rule handed the rest of the message to the template as the error detail.
    (re.compile(r'^连接被拒绝：(?P<detail>.+?)。退出游戏后使用'),
     'hades2.error.attachDenied'),
    # `'找不到匹配架构的 Mach-O UUID' + suffix + '。'` — the sentence owns its
    # own period, so it must not be handed to the template as an argument. The
    # suffix may or may not carry its own parentheses, and may be absent
    # entirely when the source-derived contract probe is the bare first literal.
    (re.compile(r'^找不到匹配架构的 Mach-O UUID\s*(?P<suffix>[^\s，。]*)?。?$'),
     'hades2.error.uuidLookupFailed'),
    # catalog.py: `未从本机 {game} 中文语言文件解析到 {count} 项{term:…}的官方中文名称，…`
    (re.compile(r'^未从本机 (?P<game>.+?) 中文语言文件解析到 (?P<count>.+?) 项'),
     'hades2.error.missingOfficialNames'),
    # preparation.py: `f'{args[0]} 失败（{rc}）：{detail}'`
    (re.compile(r'^(?P<tool>.+?) 失败（(?P<returncode>.+?)）：(?P<detail>.+)$'),
     'hades2.error.commandFailed'),
    # preparation.py: `f'{args[0]} 超时（{TIMEOUT} 秒）；操作结果需重新检查。'`
    (re.compile(r'^(?P<tool>.+?) 超时（(?P<timeout>.+?) 秒）；'),
     'hades2.error.timeout'),
    # preparation.py: `f'请先退出 {game}；运行中不能修改签名或恢复存档。'`
    (re.compile(r'^请先退出 (?P<game>.+?)；'),
     'hades2.error.prepareWhileRunning'),
    # preparation.py: `f'未经验证的游戏版本：version={v}, build={b}, UUID={u}。'`
    (re.compile(
        r'^未经验证的游戏版本：version=(?P<version>.*?), '
        r'build=(?P<build>.*?), UUID=(?P<uuid>.*?)。$'),
     'hades2.error.unverifiedBuildWarning'),
    # preparation.py: `f'无法运行 {args[0]}：{error}'` — the tool name and the
    # OS error are two values, not one; joining them left `{1}` unfilled.
    (re.compile(r'^无法运行 (?P<tool>[^：]+)：(?P<detail>.+)$'),
     'hades2.error.commandLaunchFailed'),
)

# Messages composed into a local variable and only raised later, which a
# `raise`-site scan cannot see at all. `persistence.py` builds its text with
# `.format(...)` and calls `super().__init__(message)`, so a scan that
# "replays every real raise" never looked at these — and the
# `使用了更新的数据格式` rule shipped broken anyway because nothing probed it.
ASSIGNED_KEYS = (
    # '{} 使用了更新的数据格式（schemaVersion={}，当前支持 {}），本次读取已拒绝且原文件保持不变。'
    (re.compile(
        r'^(?P<kind>.+?) 使用了更新的数据格式'
        r'（schemaVersion=(?P<found>[^，]*)，当前支持 (?P<supported>[^）]*)），'),
     'hades2.error.preferenceNewerFormat'),
    # '{} 使用了已不再支持的旧数据格式（…），本次读取已拒绝且原文件保持不变。'
    (re.compile(
        r'^(?P<kind>.+?) 使用了已不再支持的旧数据格式'
        r'（schemaVersion=(?P<found>[^，]*)，当前支持 (?P<supported>[^）]*)），'),
     'hades2.error.preferenceOlderFormat'),
)

# Messages whose interpolated value is delimited, with the sentence's own
# leading and trailing text. These are matched before the plain prefix rules so
# the runtime value is isolated and the static wording stays in the template,
# where the module can translate it.
DELIMITED_AFFIX_KEYS = {
    '请先启动': (' 并进入存档。', 'hades2.error.gameNotRunning'),
    '检测到多个': (' 进程，请保留一个。', 'hades2.error.multipleProcesses'),
}

# Messages shaped `lead + value + middle + code + tail + detail`, mapped to a
# key whose template takes all three values positionally.
SEGMENTED_KEYS = {
    '查询': (' 进程失败（', '）：', 'hades2.error.processQueryFailed'),
}

# Keys whose template takes the interpolated value as its first argument.
_ARGUMENT_KEYS = frozenset((
    'hades2.error.traitNotSellEligible',
    'hades2.error.traitRemovalNotProven',
    'hades2.error.traitNotPresent',
    'hades2.error.traitRemovalFailed',
    'hades2.error.missingSymbol',
    'hades2.error.symbolNotUnique',
    'hades2.error.symbolUnreadable',
    'hades2.error.runtimeVerificationFailed',
    'hades2.error.resumeFailed',
    'hades2.error.focusRestoreFailed',
    'hades2.error.uuidLookupFailed',
    'hades2.error.outcomeUnknownTransport',
    'hades2.error.commandLaunchFailed',
    'hades2.error.gameNotRunning',
    'hades2.error.multipleProcesses',
    'hades2.error.processQueryFailed',
    'hades2.error.attachDenied',
    'hades2.error.architectureRequired',
    'hades2.error.prepareWhileRunning',
    'hades2.error.timeout',
    'hades2.error.commandFailed',
    'hades2.error.unverifiedBuildWarning',
    'hades2.error.preferenceNewerFormat',
    'hades2.error.preferenceOlderFormat',
    'hades2.error.missingOfficialNames',
))


# Rendered shapes where the value is delimited inside the message.
#
# A prefix rule cannot express these: the value sits in the middle, and
# preparation.py even leads with a command name, as in
# `f'{args[0]} 失败（{result.returncode}）：{detail}'`. Each entry is
# `(opening, closing)`; everything between them becomes the argument.
DELIMITED_KEYS = {
    ('元素数量必须为 0–', ' 的整数。'): 'hades2.error.elementRange',
    ('局内数值必须为 0–', '。'): 'hades2.error.vitalRange',
    ('巫咒充能必须为 0–', '。'): 'hades2.error.spellChargeRange',
    ('数量必须是 0–', ' 的整数。'): 'hades2.error.amountRange',
    (' 失败（', '）'): 'hades2.error.commandFailed',
    (' 超时（', ' 秒）'): 'hades2.error.timeout',
}

def presentation_for(message, diagnostic: Optional[str] = None):
    """Return `(key, arguments)` for a raised message, or `(None, [])`.

    `None` means the message is not registered Hades player-facing copy, so the
    caller keeps its own value untouched.
    """
    if not isinstance(message, str) or not message:
        return None, []
    key = MESSAGE_KEYS.get(message)
    if key is not None:
        return key, []
    for pattern, candidate in REGEX_KEYS + ASSIGNED_KEYS:
        match = pattern.match(message)
        if match is None:
            continue
        # Group order is the template's {n} order, so the static wording stays
        # in the module's own table instead of riding along as an argument.
        # Positions are preserved: dropping a group would shift every later
        # value into the wrong placeholder. An absent optional value is kept as
        # an empty string so its position still holds.
        arguments = [group or '' for group in match.groups()]
        return candidate, arguments
    for lead, (tail, candidate) in DELIMITED_AFFIX_KEYS.items():
        if not message.startswith(lead) or not message.endswith(tail):
            continue
        value = message[len(lead):len(message) - len(tail)].strip()
        if not value:
            continue
        return candidate, [value]
    for lead, (middle, tail, candidate) in SEGMENTED_KEYS.items():
        if not message.startswith(lead):
            continue
        rest = message[len(lead):]
        split = rest.find(middle)
        if split < 0:
            continue
        value, remainder = rest[:split].strip(), rest[split + len(middle):]
        split2 = remainder.find(tail)
        if split2 < 0:
            continue
        code, detail = remainder[:split2], remainder[split2 + len(tail):]
        if not value or not code:
            continue
        return candidate, [value, code, detail]
    for prefix, candidate in PREFIX_KEYS.items():
        if message.startswith(prefix):
            remainder = message[len(prefix):]
            # A composed message is kept whole as one argument: splitting it
            # further would bake structure into a localized sentence.
            return candidate, [remainder] if candidate in _ARGUMENT_KEYS else []
    # Delimited shape: the value is bracketed inside the message, so neither a
    # whole-message nor a prefix rule can match it.
    for (opening, closing), candidate in DELIMITED_KEYS.items():
        start = message.find(opening)
        if start < 0:
            continue
        begin = start + len(opening)
        end = message.find(closing, begin)
        if end <= begin:
            continue
        return candidate, [message[begin:end]]
    return None, []
