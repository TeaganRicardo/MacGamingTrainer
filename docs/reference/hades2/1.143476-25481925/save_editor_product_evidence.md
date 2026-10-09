# Save Editor：Hades II 1.143476 原生数据与产品交付反证调查

**日期：**2026-10-10。**仓库基线：** `main@fffcc36d1a0fda3d597951b22098ce48c7c88a18`（PR #415 merged）。**父任务：**#397。**性质：**一份可复核的原生资料调查，不代表已经开发、执行仓库测试、加载游戏或通过人工验收。

## 一、证据来源与方法

资料取自用户此前备份的 Google Drive / Hades2 / 1.143476-25481925 / `hades2-catalog-evidence-1.143476-steam-25481925.tar.gz`，2026-09-30 捕获，对应 Hades II 1.143476 / Steam 25481925。归档采用原始 `sources/Scripts`、`sources/Text/en` 和 `sources/Text/zh-CN` 路径。实际执行 `sha256sum -c manifest/FILES.sha256`，**1,164/1,164 通过**；这是对清单中原始文件的校验，不是 tar 物理成员数量。归档的 `sources/Scripts` 有 **958 个 `.lua` 后缀成员**，其中 **479 个有效 Lua 脚本**，另 **479 个是 macOS AppleDouble `._*.lua` 元数据文件**，不得计入脚本扫描。实际调查语料为 **479 个 Lua 脚本、181 个英文 SJSON、181 个简体中文 SJSON**（均排除 AppleDouble），三类合计 841 个有效源文件。

已与仓库 `Backend/games/hades2/save_native_ids.py` 中的生成来源 SHA 对照：`QuestData.lua = df9888d6586e0f8644e31db093bf35452bc3ac057d0f144be2f2f1e8d1e64336`；`ResourceData.lua = 94b2dc9edc22c34b213ab78dea42f2dc76c80cbcfde14104cbe772b254a29b03`；`ObjectiveData.lua = e635ef5c05ba8a22e4af4ed3d4290ec20d31c0bd95c1aff9e8b1ac828940c816`；`StoryResetData.lua = 58509042a27542f96d666071da2fa58ca3c3b227002e4ae628501b7d7738ef8e`，**全部吻合**。

调查方法为冻结仓库生产文件/邻近测试阅读、**仅遍历 479 个非 AppleDouble 的 Lua 脚本**进行词法扫描、针对部分 `name={...}` 场景的括号平衡提取、中英 SJSON `Id/Event` 交叉校验，以及人工检查反例。**静态次数只是候选覆盖，不等于 Lua 游戏语义、持久化字段或可写权限；没有执行真实 Lua 游戏循环、没有读取任何个人存档。**完整原生脚本、台词不进入公共仓库，仅保留最少标识及路径/哈希以供复核。

**数量复核口径：** 在归档根目录执行 `find sources/Scripts -type f -name '*.lua' ! -name '._*' | wc -l` 得到 479；tar 中另有 479 个 `._*.lua` 分叉。`RunLogic.lua` 全文按 `\bGameState\.([A-Za-z_][A-Za-z_0-9]*)\s*=\s*GameState\.\1\s+or\b` 匹配初始化，得到 **146 次、145 个不同字段**；`EnemyEliteAttributeKills` 在第 162、238 行重复出现。SJSON 在保留引号字符串的前提下排除 `//` 与 `/* ... */` 注释，按行首 `Id = "..."` 的字面值提取并在每种语言内去重（不按 `Event` 或文件名筛选）：英文 **38,086**、中文 **37,300**、交集 **37,300**，英文独有 **786**、中文独有 **0**。这仅是 ID 字面值覆盖，不证明对应译文的质量、有效性或语义等价。

## 二、当前产品覆盖（源码事实）

| 任务领域 | 当前能力及代码 | 交付差距 |
|---|---|---|
| 浏览/查找 | `Sources/Hades2/Views/Hades2SaveEditorView.swift:106-135,190-272`：9 个领域 Picker、领域内搜索、100 行一页；`save_workspace.py:363-429` 只匹配当前域 rawID/中文/英文 | 缺少跨领域的任务检索、状态/可编辑筛选、来源及不可编辑理由；已知但未写入存档的剧情对话不出现在普通查询 |
| 对话/剧情 | `save_narrative.py:181-235`：只列已记录布尔 `TextLinesRecord` 和已存在 QuestStatus，主要将对话 ID 显示为「对话记录 · ID」 | 缺少人物、场景、台词、条件树、伙伴/变体/随机竞争和当前运行相关状态；原生可辨识 ID 不等于完整对话 |
| 玩家历史 | `save_workspace.py:21-53` 仅 3 个 `GameState` 统计：GameplayTime、TotalTime、TotalRequiredEnemyKills | 不提供 RunHistory、LifetimeTraitStats、失败/挑战/击杀记录的完整解释；不能用三个标量当作统计产品 |
| 成长/关系 | `save_long_term.py`、`save_equipment.py` 对任务、NPC、目标、塔罗、武器、工具、魔宠提供选定字段；礼物数量只读 | 数据通常跨多个原生 owner，任务奖励、对话、晋级、使用记录没有完整合并成玩家认得的对象 |
| 预览/保存 | `save_workspace.py:464-624` 已具备源文件固定、暂存、联动 diff、冷写入；`Hades2SaveEditorView.swift:337-367` 展示更改 | 审查面板缺少直接移除单条/批量组织、变更理由和影响信心；保障基础设施不能替代可用工作台 |
| Advanced | `save_workspace.py:334-360` 对 LuaTable 按路径生成只读行，`save_document.py` 保留未知内容 | 不等价于语义检索，重复物理键的行 ID 仍有冲突问题（见 F8） |

现有原生生成 ID 数：**89 Quest、97 持久 Resource、52 NPC interaction、89 Objective、393 StoryReset.TextLines**。这是 ID 集合，而非全部可修改数据、全部用户进度、全部剧情或实际可触发内容。

## 三、逐项反证

### F1：生成工具对源版本不可复现（已证实）

`sources/Scripts/StoryResetData.lua:148-702` 含 **393** 个互不重复的有效 `TextLines` 字符串。第 681 行 `"HadesWithPersephone01", -- needed to provide DeathAreaPoints` 是有效 Lua 数据，后面有行内注释。`Tools/generate_hades_save_ids.py:68-75` 的正则只接受逗号/空白后直接结束行，独立执行同一规则得到 **392** 个，漏掉该有效 ID。现有 `save_native_ids.py` 却已经包含 393 个，说明程序和提交生成物不一致。只需要修复源生成器、以可重复生成及「注释整行不入选」为回归验证，不应顺便扩大写入权限。责任 Issue **#417**。

### F2：原生 StoryReset 不是单条对话重置（已证实）

`sources/Scripts/StoryResetLogic.lua:94-174` 的 `DoStoryReset` 同时修改 WorldUpgrades、QuestsCompleted/QuestStatus、Resources/LifetimeResourcesGained、TextLinesRecord、SpeechRecord/SpeechRecordContexts、结局/杀敌/房间状态及近期 RunHistory，还处理当前 Run 与资源托管。`save_narrative.py` 的单条对话重置范围要窄得多。现有 #415 对陪伴记录和重复键的严格校验是必要安全性，但**不能以本原生复位表的成员关系承诺该对话独立可再触发**。产品动词要区分「清除指定历史标记」和「恢复剧情事件/重放」。

### F3：冷存档无法保证下次对话触发（已证实）

`sources/Scripts/NarrativeLogic.lua:16-93` 按优先级选择候选，也可能在同优先级组随机、处理已播随机池；`NarrativeLogic.lua:551-647` 的 `IsTextLineEligible` 同时检查 PlayOnce、PlayOnceThisRun、伙伴是否存在、资源成本、游戏状态及源对象条件。`RequirementsLogic.lua:9+` 还支持 NamedRequirements、NamedRequirementsFalse、OrRequirements、随机 ChanceToPlay、动态 FunctionName、source/args 路径。逐句也可以带要求。**脚本中出现的要求 ≠ 当前存档满足 ≠ 下一局必然播出。**

实例：`sources/Scripts/NPCData_Nemesis.lua:4093+` 的 `NemesisPostTrueEnding01` 依赖 **CurrentRun.TextLinesRecord.TrueEndingFinale01**；这是局内、随上下文变化的要求。另一段 `NemesisAboutChronosBossFights01` 含房间、通关、击杀及赠礼等多项要求。UI 应显示原生要求、当前冷存档能够证明的事实以及未知/运行时/随机部分，不要承诺「下局可触发」。

### F4：事件 ID 与文本并不一对一（全量枚举 + 重点人工核对）

对 **393** 个原生 StoryReset 目标的静态枚举结果：

| 指标 | 结果 | 限定 |
|---|---:|---|
| 存在脚本内可检索 `ID = {...}` 定义 | **392** | `PreTrueEnding01` 未在 479 个有效 Lua 脚本发现该形态定义，**不能断言它在游戏中不存在** |
| 存在多处同名 Lua 定义 | **10** | 部分为双人/伙伴对话镜像和其他所有权 |
| 对应定义块出现 `GameStateRequirements` | **374** | 只证明文本出现，不等于全部条件、可计算性或成立 |
| 可直接由英文 SJSON `Event = "ID"` 联结 | **390** | `HecateAboutUltimateProgress03`、`HecateAboutUltimateProgress04`、`PreTrueEnding01` 没有这一直接映射 |
| 找到静态显式 `/VO/...` Cue | **392** | 未定义的目标不能靠猜测补语音；每个 Cue 可能有子句条件 |
| Cue 缺少相同中英文 `Id` 的目标 | **2 个目标、3 个 Cue ID** | `HecateAboutTyphonFight03` 的 Melinoe_0585_A/B，`HermesFieldAboutTyphon03` 的 MelinoeField_4215；脚本自带英文 Text 不构成官方中文译文 |

针对反例：`NPCData_Hecate.lua:1743,1824` 的 `HecateAboutUltimateProgress03_A` 与 `03` 复用文本 Cue，英语 SJSON 的 Event 归属主要标成 `…03_A`；若仅按 Event 联结，`03` 会被误判为无台词。`NPCData_Hecate.lua:1871` 的 `…04` 也没有同名 Event，但其 `Hecate_0942` 翻译实际在 `Text/en/_EnemyData_Hecate.en.sjson:1241`，不能按 NPC 文件名限制搜索。`NPCData_Hades.lua:2339,5943` 同名 `HadesWithPersephone01` 分别出现在不同定义处，部分通过 Partner/CopyDataFromPartner 取得文本。其余重复 ID 包括 `NemesisWithHecate02`、`NyxWithNemesis01` 等。`PreTrueEnding01` 只找到重置表成员，来源保持未解，不得标为已支持。

**正例：** `NPCData_Nemesis.lua:4093+` 的 `NemesisPostTrueEnding01` 中有 `/VO/Nemesis_0407`，`Text/en/_NPCData_Nemesis.en.sjson:2935+` 记录 `Id=Nemesis_0407`、`Speaker=Nemesis`、`Event=NemesisPostTrueEnding01`；`Text/zh-CN/_NPCData_Nemesis.zh-CN.sjson:2099+` 可用同 Cue ID 联结官方中文。应按 **Event → 来源人物/场景/变体/伙伴 → 多个 Cue 及分支 → 中英译文 → 原生要求** 建立多对多来源索引。

额外基线：全英文 SJSON 静态扫描约 **8,499 个 Event 值**、**30,339 次 Event–Id 关联**、**38,086 个不同 Id**；中文有 **37,300 个不同 Id**，**全部 37,300 个**与英文 Id 集合重合（英文独有 786 个）。这里 Id 包含大量非对话/表现文本，Event 关联亦不等于独立对话数；相同 Id 不表示文本内容、场景与有效翻译一一对应。中文文件通常不重复 Event 元信息，而需要用 Id 联结。不得说「英文 8,499 段对话全部已翻译」。

### F5：「数百个没有实现的 GameState.Flags」这一假设被推翻

遍历所有 479 个有效脚本，找到直接 `GameState.Flags.<NAME>` 共 **14 个不同名称**，与 `save_narrative._FLAG_DESCRIPTORS` 的 14 项一致。发现的其他变量下标 `Flags[variable]` 属于 `MapState.Flags` 的地图级表，没有证据是未列出的动态 `GameState.Flags`。并不意味着玩家所有剧情状态只有 14 项；大量真正的条件位于 `TextLinesRecord`、`SpeechRecord`、`EnemyKills`、`RunHistory`、`WorldUpgrades`、`QuestStatus` 等表。

更广义的词法调查发现约 **251 个直接 `GameState.<FIELD>` 名称**；其中 `RunLogic.lua` 按上述正则有 **146 次 `GameState.X = GameState.X or ...` 初始化匹配、涉及 145 个不同字段**（`EnemyEliteAttributeKills` 出现两次）。这些数字不代表 251 个独立保存字段，更不代表可编辑数：其中有缓存、衍生或上下文状态；完整是否保存须依 `SaveLogic.lua` 的白名单/处理判断。

### F6：不存在完整无限制的局历史（已证实）

`sources/Scripts/SaveLogic.lua:142-205` 的 `StripRunHistoryForSave`/ `StripRunForSave` **按照历史位置裁剪**：最近的上一局先删去指定短暂字段；更近的 **10 局**保留 RecentRun/RecentRunTables 和 MainRun/Permanent 类别；超过 **10 局**但未超过 **500 局**主要只保留 MainRun/Permanent；超过 **500 局**只保留 Permanent。历史项上没有 `RoomsEntered`、`TextLinesRecord`、`EnemyKills` 不能解释成「那局没发生」，可能早已被游戏裁剪。UI 至少区分「明确为 false/0」「没有保存该字段」「历史裁剪导致不可判定」，不得以缺失代替否定事实。

### F7：原生 GameStats 不是平铺的数值（已证实）

`GameStatsData.lua:20-100` 定义五类统计筛选：Weapons、Boons、WeaponUpgrades、Keepsakes、Familiars；六类主要排序/展示指标：使用、通关、地下/地表最快时间、地下/地表最高 Shrine 点数。`GameStatsLogic.lua:150-250` 合并特定 dummy weapon 与 Aspect 记录，计数求和、时间求最小、Shrine 求最大；`RunLogic.lua:2083-2120` 根据单局内容更新 `LifetimeTraitStats`。所以 **面板上一个数值可能对应多个原始存档键的派生结果**。新增一个可编辑数字输入框无法保证用户在游戏中看到预期变化。先交付含原生类别、计算/来源说明、单局历史上下文的检索，待证明写入所有者再开放相应修改。

### F8：#415 修复了对话的重复键，但其他可写领域仍存在同类歧义（源码级反例，需 RED）

`save_document.py:66-123` 的 `LuaTable` 无损保留 luabins 的相同物理键，而 `__getitem__`、`__setitem__`、`__delitem__` 只处理**第一次匹配**。`save_workspace._resource_descriptor` 用 `resources.get(id)`；`_apply_intent` 后续用 `owner[key] = newValue`，没有检测重复键。因而对于临时合成的 `LuaTable(0, 2, [("MetaCurrency", 5.0), ("MetaCurrency", 99.0)])`，当前 API 会以 5 作为可编辑预览，写入后第二个同名物理值 99 仍留存。这是安全操作语义歧义；**尚无证据真实游戏正常输出重复键**，但保存模型允许解析，不应该被一项「编辑成功」掩盖。统计、长期成长、武器等其他路径也缺少统一唯一 owner 约束，不能再逐领域重复局部补丁。

`save_workspace._advanced_rows:334-360` 的 ID 仅由 JSON 路径构造。同层相同键的两个物理行会有相同 ID，`Hades2SaveEditorView.swift:198-204` `ForEach` 不能可靠区分，而且 `_lua_path` 总走首个同名键，无法真实钻取第二个表。`test_hades2_save_advanced_identity.py` 只覆盖「数字/字符串/布尔不同类型」和带斜线的路径，没有覆盖**同类型重复物理键**。这是同一条唯一身份原则的读写两面。**#416** 负责在统一 Hades 语义 owner 层修正，临时测试先 RED、跨领域 batch 应 fail-closed 且不可写磁盘，未知数据仍无损只读。

### F9：QuestStatus 是部分任务历史，不是完整命运清单生命周期

`QuestLogLogic.lua:607-632` 依据 Unlock/CompleteGameStateRequirements 从缺失 → Unlocked → Complete；`CashOutQuest` 还调用 `AddResource` 并标为 `CashedOut`。`QuestPresentation.lua:104-113,400-408` 维护 `QuestsViewed`、`QuestsUpdated`、`PlayedQuestInterstitials`。目前 `save_narrative.py` 对 QuestStatus 的编辑只联动 `QuestsCompleted`，并阻止改已领取的 CashedOut。这一限制不能视作用户产品已涵盖奖赏领取/剧情/任务显示的全部语义。命运清单至少应以实体展示实际原生解锁与完成条件、记录状态、奖励/领取状态、已查看/演出情况，再给出真实可支持的操作和无法编辑原因。

### F10：失败、受击和小游戏纪录没有一个通用的「不完美」总开关

源码逐项定位，避免把用户希望检查的失败/受伤记录一概转成某个零值：`HarvestLogic.lua:738-765` 将驱邪成功分为魔宠和手动，手动小游戏失败另增 `GameState.ExorcismFails` 与局内 `CurrentRun.ExorcismFails`；`HarvestPresentation.lua:949-965,1044-1045` 同样分别记录钓鱼成功、魔宠/手动成功、`FishCaught` 和钓鱼失败。这些是**实际持久化/局内增量**，但并不意味着只改一处历史计数就能撤销相关体验。

`ObjectiveLogic.lua:303-309` 的 `GameState.LastObjectiveFailedRun[objectiveName]` 记录**最后失败的局数**，不是失败总次数。尤其 `NPCData_Nemesis.lua:~12000` 对 `NemesisBet` 的对话直接读取该值并与 `CompletedRunsCache` 比较；删除「失败记录」可能反而改变剧情可用性。`DeathLoopLogic.lua:65-115` 更新最近死因、连胜和死亡后的清算条件，`RunLogic.lua:1946` 从 `GetRunResult(CurrentRun)` 写局结果；它们与一条通用「死亡次数」不是等价语义。

`CombatLogic.lua:1769-1830` 正伤害会修改 `CurrentRun.TotalDamageTaken`，有攻击者时也更新局内及长期 `DamageTakenFromRecord`；遭遇期间还会设置 `Encounter.PlayerTookDamage` 并失败 `PerfectClear` 目标。紧随其后的零伤害分支单独处理受击对话。脚本检索到的 `HeroHit` 相关项主要是震动/演出，不足以证明存在一个可写的通用 `GameState.HeroHit`「零受击」字段。因此**受到命中、受到实际伤害、完美挑战失败、历史局失败、小游戏失败**是不同事件；仅把伤害数值清零不能证明达成 0-hit 或抹去完整失败历史。修改许可必须针对原生 owner 和关联条件另行证实。

## 四、用户应看见的状态模型

| UI 状态 | 证明依据 | 能宣称什么 |
|---|---|---|
| 已记录 | 保存字段存在、值/物理 owner 唯一 | 「存档包含此记录」；是否可编辑需额外原生操作依据 |
| 原生已知但未记录 | 同版游戏有明确 ID，保存 owner 缺少此字段 | 「本 owner 未记录」；**不是**「事件不可能发生」或「历史从未发生」 |
| 有条件/需运行时 | 原生要求树可定位，部分值在当前冷档可观察 | 按需显示来源条件和可观察部分；未来条件、概率、伙伴、优先级标成未知 |
| 来源不完整/歧义 | 文本 Event 缺失、多个脚本定义、未解析 NamedRequirements、重复物理键 | 可检索、可读，展示来源及不可验证原因，禁止不可靠写入 |
| 支持修改 | 唯一 owner、经过核验的原生语义、完整关联变更、原始读取版本固定及冷写回保护 | 可批量暂存、修改/移除条目、审查链接 diff、一次提交；不能自动重试未知结果 |

## 五、按实际场景推进的开发次序

**首先解决正确性根因：**#416（所有 Hades 可写 owner 的重复键语义与 Advanced 物理行身份）及 #417（393 原生 ID 生成一致性）；不是新一轮全局治理。

**首个产品级垂直交付：NPC/剧情/对话/任务可搜索调查工作流。** 搜索 Nemesis 及中英对话文本时能找到相关候选场景，包括按需展示原生已知但未写入存档的内容；点开详情有剧本文本、Cue、人物/变体、官方中英文台词、命名/嵌套触发要求与值的来源；按已记录/未知/只读/安全允许重置分类，绝不保证「下局必定触发」。需要以 Hecate 共享 Cue、跨文件本地化、Hades/Persephone 伙伴重复、PreTrueEnding 来源不明、缺译 Cue、Nemesis 当前局条件作回归。生产资料从本机已安装游戏或可信版本固定来源读取，不能将整套原版台词打包到公共仓库。解析器属于 Hades 模块，不另造共用 Lua/Core 目录或第二份人工真源。

**随后交付玩家统计/局历史的辨识、查找与证据上下文。** 支持 native 5 类统计、显示值来源合并、历史裁剪层级、死因/挑战/失败等经原生核验的字段；先只读、再在证明完整修改 owner 后开放编辑。

**再完成 Quest/关系/武器/魔宠跨 owner 的实体操作与工作台 UX。** 详情按需展开，不出现大段默认条件墙；筛选和搜索不局限九域下拉；暂存项可逐项编辑/移除，审查含间接变化；保持 pinned-original-read、恢复快照和最终写回验证。

**验收方式：** 以临时合成 Lua/SJSON/存档 fixture 对端到端行为回归，必须包含语义未解、名字重复、冷档无法证明未来条件、已知未记录、历史裁剪、双语切换、来源缺失及跨域批量失败。GitHub PR 在最终实际头上按 `AGENTS.md` 跑适用 Linux/macOS 检查并由独立线程 Review。RDC 不运行游戏；最终游戏加载、可视化及人工验收由用户完成。

## 六、引用索引

**仓库（冻结 HEAD）：** [codec](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_document.py) · [workbench](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_workspace.py) · [narrative](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_narrative.py) · [long term](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_long_term.py) · [equipment](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_equipment.py) · [generated IDs](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Backend/games/hades2/save_native_ids.py) · [generator](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Tools/generate_hades_save_ids.py) · [Swift UI](https://github.com/TeaganRicardo/MacGamingTrainer/blob/fffcc36d1a0fda3d597951b22098ce48c7c88a18/Sources/Hades2/Views/Hades2SaveEditorView.swift)。

**原生（Google Drive 快照内，按原始目录访问）：** `sources/Scripts/{RunLogic,SaveLogic,RunHistoryLogic,GameStatsData,GameStatsLogic,NarrativeLogic,RequirementsLogic,QuestData,QuestLogLogic,QuestPresentation,StoryResetData,StoryResetLogic,NPCData_Hecate,NPCData_Nemesis,NPCData_Hades,NPCData_Hermes}.lua`；`sources/Text/en`、`sources/Text/zh-CN` 的对应 SJSON。全部文件可用 `manifest/FILES.sha256` 复验；摘要在第一节列明。后续来源/构建变化必须重新建立这一事实基线，不能将老版参考数据冒充当前版。

**处置：**[父任务 #397](https://github.com/TeaganRicardo/MacGamingTrainer/issues/397) · [重复 owner #416](https://github.com/TeaganRicardo/MacGamingTrainer/issues/416) · [生成器 #417](https://github.com/TeaganRicardo/MacGamingTrainer/issues/417)。本调查不使上述 Issue 自动完成，也不构成实机验收证据。
