# Provisional catalog names

Supported target: Hades II 1.139672 / Steam build 24556151.

This file is human-readable reference rationale for the Trainer-authored or Trainer-composed display labels used with this supported build. It is documentation only. Production naming behavior is owned by `Backend/games/hades2/catalog.py` and verified through catalog behavior tests; production code and tests must not depend on this file.

These entries need Trainer-side labels because the installed localization either has no usable standalone DisplayName for the runtime reward identifier or deliberately reuses the base item's DisplayName for a distinct size variant. Runtime name-source provenance remains explicit.

| Runtime ID | Chinese | English | Basis |
| --- | --- | --- | --- |
| RoomMoneyTinyDrop | 少量金币 | Small Gold Crowns | Variant of official 金币 / Gold Crowns |
| EmptyMaxHealthSmallDrop | 小型半人马之魂 | Small Centaur Soul | Variant of official 半人马之魂 / Centaur Soul |
| MaxHealthDropSmall | 小型半人马之心 | Small Centaur Heart | Official ID reuses 半人马之心 / Centaur Heart; size prefix distinguishes the smaller +5 variant |
| MaxManaDropSmall | 小型灵魂之水 | Small Soul Tonic | Official ID reuses 灵魂之水 / Soul Tonic; size prefix distinguishes the smaller +10 variant |
| MetaCurrencyBigDrop | 大量骨骸 | Large Bones | Variant of official 骨骸 / Bones |
| MetaCardPointsCommonBigDrop | 大量尘灰 | Large Ashes | Variant of official 尘灰 / Ashes |
| MemPointsCommonBigDrop | 大量魂魄 | Large Psyche | Variant of official 魂魄 / Psyche |
| GemPointsBigDrop | 大量宝石 | Large Gemstones | Larger GemPoints pickup; no standalone localized DisplayName under this runtime ID |
| FireBoost | 火元素精华 | Fire Essence | Game HelpText describes essence of Fire |
| WaterBoost | 水元素精华 | Water Essence | Game HelpText describes essence of Water |
| EarthBoost | 土元素精华 | Earth Essence | Game HelpText describes essence of Earth |
| AirBoost | 风元素精华 | Air Essence | Game HelpText describes essence of Air |
| ElementalBoost | 元素精华 | Elemental Essence | Generic ElementalEssence reward data |
| StoreRewardRandomStack | 随机祝福强化 | Random Boon Upgrade | Randomly adds a stack to one boon |
| HealDropMajor | 大型生命恢复 | Major Healing | Functional 50-health variant; no standalone localized DisplayName under this runtime ID |
| HealDropMinor | 少量治疗 | Minor Healing | Localized entry is icon-only after markup cleanup; label describes the 10-health variant |
| RandomLoot | 随机奥林匹斯祝福 | Random Olympian Boon | Store wrapper resolves to an eligible Olympian before spawning; no standalone localized DisplayName |
| BoostedRandomLoot | 强化随机祝福 | Boosted Random Boon | Store wrapper resolves to an eligible Olympian with the native rarity override; no standalone localized DisplayName |

Linked or directly resolved official names are not provisional. For example ArmorBoost resolves through ArmorBoost_Store to 护盾饰符 / Shield Charm, RoomRewardHealDrop resolves through RoomRewardHealDrop_Store to 新鲜食粮 / Fresh Sustenance, SpellDrop resolves through SpellDrop_Store to 月之礼赠 / Gift of the Moon, and RoomRewardConsolationPrize has its own official 红洋葱 / Red Onion DisplayName.
