# v0.17.9

App version: **0.17.9**  
Build: **32**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **20**

## 局内数据 UI

- 修正 `TrainerMetricCard` 的高度计算顺序：padding 现在包含在卡片总高度内，不再形成顶部大块空白和异常高卡片。
- 生命/魔力 `X / Y` 输入区域收紧，`/` 保持在两个数值中央。
- 百分比和 `/s` 后缀改为紧邻数值。
- 卡片内容重新垂直居中。
- 展开/收起改为 `文字 + 箭头` 的单一紧凑点击区域，箭头本身也可点击。

## Switch 与状态同步

- 唯一共享 `TrainerToggleControl` 从 `.small` 调整到 `.regular`，继续使用 `theme.accent` 的亮紫色和原生动画。
- Hades2 仍然没有独立 Switch 渲染实现。
- 增加轻量 runtime state reconciliation：只要存在已开启 desired feature（或等待消费的下一房奖励），连接状态下每 4 秒静默读取一次 status。
- 游戏在场景切换后自主激活功能时，等待中的橙色 icon 会自动恢复 active 紫色，不再要求手动重新开关一次。

## 左侧存档管理闪动

- “存档管理”按钮不再绑定瞬时 `model.busy` disabled 状态；普通开关、数值和列表修改不会再让该文字反复 disabled/enabled 而闪动。

## 下一房奖励

旧实现仍使用 Early Access `RoomReward*` 名称，已改成当前正式版奖励 ID：

- `RoomMoneyDrop`
- `MetaCurrencyDrop`
- `MetaCardPointsCommonDrop`
- `MemPointsCommonDrop`
- `MaxHealthDrop`
- `MaxManaDrop`
- `StackUpgrade`
- `WeaponUpgrade`

诸神/塞勒涅等 Loot 使用 `Boon + ForceLootName`，与当前游戏 `SpawnRoomReward` 的原生路径一致。

旧 Profile 中保存的 `RoomRewardMoney / RoomRewardMetaPoint / RoomRewardPsyche / RoomRewardMaxHealth / RoomRewardPom` 会自动迁移；已经不存在安全对应项的旧 `RoomRewardMixerFabric` 会清除而不是继续写入无效 ID。

下一房奖励是一次性状态：Lua 消费后，后续 status 会同步清除持久化 desired 值，避免 UI 或重连时把已消费奖励重新复活。

## 塞勒涅 / 月神巫咒 Spawn

`SpellDrop` 不再用低层 `CreateLoot` 直接造一个外壳对象，而是调用游戏自己的：

```lua
GiveLoot({ ForceLootName = "SpellDrop", ... })
```

这样会使用当前 `LootData.SpellDrop` 的完整原生初始化，包括 Selene 交互、送礼能力、`OpenSpellScreen` 和 `PregenerateSpells` setup event。

其他已经工作正常的普通 Loot/Consumable Spawn 路径不变。

## Runtime

Lua revision **19 → 20**，因为 next-room hook 与 Selene spawn 行为发生了实际变化。同 revision reload 仍保持 resident state；旧 revision 会执行 cleanup 后重新加载。
