# Round 15 — Global game/UI decoupling

Version: **0.15.0**  
Build: **21**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Hades II Lua runtime revision: **19 (unchanged)**

本轮是结构重构，不改变 Hades II wire schema 或 Lua 游戏行为，因此协议与 Lua revision 不升级。

## 目标

新增第二款游戏原则上不修改：

- `Sources/Core/**`
- `Backend/core/**`
- `Sources/App.swift`
- `build.sh`
- `Tools/**`

只增加自己的 Swift frontend、Backend module 与 `module.json`。

同时把基础 UI/style 变成 Core 能力，后续全局视觉改版不再逐游戏复制修改。

## 完成内容

- Core Swift 重排为 Runtime / Game / UI / Input。
- 新增全局 `TrainerTheme` 与共享 Shell/Sidebar/Status/Feature/Multiplier/Stat/Resource 组件。
- App 对所有游戏统一注入 theme、tint 和 dark appearance。
- Hades II frontend 改用共享 UI；祝福 picker 保持为 Hades-specific View。
- `TrainerFeatureState` 统一 active/pending/waiting/detached/mismatch 的显示语义。
- `TrainerBackendSession` 接管通用 backend 路径定位和生命周期。
- Backend adapter/registry/server 全部进入 `Backend/core`。
- Hades Lua runtime 移至 `Backend/games/hades2/runtime/hades.lua`。
- Steam helper 从 Core 移回 Hades module。
- Tools 拆为 module support / validation / Swift binding generator。
- build 完全 manifest-driven，只编译/打包 selected module。
- 新增第二游戏 source-graph 与 packaged-backend smoke test。
- 新增 Round 15 架构不变量测试，禁止游戏/发行平台逻辑重新泄漏到 Core。

## 行为兼容

Round 9–14 兼容测试、Hades adapter/preparation、两套 Lua mock 保持通过。法阵、三岔路、desired/active/dormant、存档/Profile 等逻辑没有在本轮重写。
