# 三端存储与桌面旧目录盘点

日期：2026-06-16

## 1. 本轮结论

1. `代码提交云端` 的正式含义已经固化为双推：`NAS Gitea nas` + `GitHub origin`。本轮规则提交已推到两端，远端 `main` 均为 `f2d867b95370b7c21a2e53aa7958d9ff9912853e`。
2. Mac 正式工作根目录是 `/Users/dong/ZhangData`：
   - 代码：`/Users/dong/ZhangData/market-live-terminal`
   - 数据：`/Users/dong/ZhangData/market-data`
3. Mac 本地不常驻 66G/67G 级完整 atomic 大库；日常开发和页面功能使用轻量消费库、selection、model feature、market heat 以及轻量 atomic。完整大库保留在 Windows 与 NAS。
4. Windows 现在是跑数站：保留完整 71.30G atomic 库；`research/current` 入口是 junction 别名层，还不是完全物理搬家。
5. NAS Docker 数据卷已经包含完整 66.88G atomic 库；容器通过 `/runtime-data` 挂载 host 目录，不是把数据放进镜像。

## 2. Mac 桌面旧目录差异

旧目录：`/Users/dong/Desktop/桌面 - Zhangdong的MacBook Air/AIGC/market-live-terminal`

新目录：`/Users/dong/ZhangData/market-live-terminal`

当前事实：

1. 旧目录不是 Git 仓库。
2. 旧目录约 `1.5G`，主要重量在 `data/selection`。
3. 新目录约 `717M`，代码与文档明显更新；旧目录没有当前 `agentic_finance_agents`、新后端服务、6 月恢复链路等大量新文件。
4. 旧目录 non-data 文件对比结果：
   - 旧目录独有：`52` 个
   - 新目录独有：`245` 个
   - 同路径但内容不同：`33` 个

建议保留清单：

| 类型 | 路径/内容 | 大小 | 处理建议 |
|---|---:|---:|---|
| 早期 AI 过程文档 | `.trae/documents/plan_*.md`，共 47 个 | 204K | 可归档到新路径；文本是 mojibake，但可恢复标题和内容 |
| 翻倍股研究日志 | `logs/ytd_doublers_20260430*` | 约 124K | 建议迁入新路径的研究归档 |
| 旧 selection 实验 | `data/selection/evolution_lab` | 79M | 若还要追溯 4-5 月实验，可归档；不进入正式运行链 |
| 旧机会发现实验 | `data/selection/opportunity_discovery` | 358M | 新 repo 只有 55M 子集；是否保留取决于是否还要复盘旧实验 |
| 旧策略产物 | `aggressive_10cm`、`cycle_returns`、`doubler_analysis`、`litong_similarity`、`research_watchlist` | 约 4M | 小体积，建议作为研究历史归档 |

不建议迁入清单：

| 类型 | 路径/内容 | 原因 |
|---|---|---|
| 旧选股研究库 | `data/selection/selection_research.db`，954M | 比当前正式库更小、更旧；当前正式库在 `/Users/dong/ZhangData/market-data/research/current/selection/selection_research.db`，约 3.2G |
| 旧行情修复库 | `data/market_data_history_202602_fix.db`，73M | 历史修复产物，不是当前正式 live 库 |
| 旧本地运行日志 | `logs/backend_*.log`、`vite-*.log` 等 | 启动/排障日志，除非要追事故，不建议长期迁入 |
| 编辑器状态 | `.obsidian/*` | 编辑器本地状态，不是业务资料 |
| 旧组件路径 | `src/components/selection/AgenticCompanyResearchEmbed.tsx` | 新实现已迁到 `src/components/common/AgenticCompanyResearchEmbed.tsx`，旧文件不应回迁 |

桌面旧目录删除前的建议动作：

1. 先归档 `.trae/documents` 和 `logs/ytd_doublers_20260430*`。
2. 再由用户决定是否保留 `data/selection/evolution_lab` 与 `data/selection/opportunity_discovery` 的旧实验产物。
3. 不把旧 `selection_research.db` 当正式库恢复。

## 3. 三端数据库现状

### 3.1 Mac

根目录：`/Users/dong/ZhangData/market-data`

当前大小：

| 对象 | 大小 |
|---|---:|
| `market-data` | 9.3G |
| `live` | 928M |
| `research/current` | 8.4G |
| `market-live-terminal` repo | 717M |

关键库：

| 逻辑库 | 物理路径 | 大小 | 表数 / schema |
|---|---|---:|---|
| `market_data_main` | `live/market_data.db` | 919M | 29 表，schema `cd9ffb50e6beca9b` |
| `selection_research_main` | `research/current/selection/selection_research.db` | 3.2G | 10 表，schema `edaf615093738273` |
| `model_feature_store_main` | `research/current/selection/model_feature_store.db` | 4.6G | 7 表，schema `98f90e5b85a91479` |
| `atomic_compact_main` | `research/current/atomic_facts/market_atomic_mainboard_compact_current.db` | 129M | 12 表，轻量本地库 |

本轮已补齐空目录骨架：

```text
cache/market_heat
cache/eastmoney_sector_cache
artifacts/reports
incoming
```

### 3.2 Windows

主机：`DESKTOP-9LMADRQ`，局域网 SSH `laqiyuan@192.168.3.108`

关键路径：

```text
D:\MarketData
D:\market-live-terminal\data
Z:\atomic_stage
Z:\atomic_legacy_backup
```

当前结构：

1. `D:\market-live-terminal\data\live\market_data.db` 与 `D:\market-live-terminal\data\market_data.db` 是硬链接同一文件。
2. `D:\market-live-terminal\data\research\current\atomic_facts` 是 junction，指向 `D:\market-live-terminal\data\atomic_facts`。
3. `D:\market-live-terminal\data\research\current\selection` 是 junction，指向 `D:\market-live-terminal\data\selection`。
4. `D:\market-live-terminal\data\research\current\market_heat` 是 junction，指向 `D:\market-live-terminal\data\market_heat`。

关键库：

| 逻辑库 | 大小 | 表数 / schema | 备注 |
|---|---:|---|---|
| `market_data_main` | 2.64G | 13 表，schema `6dfe3fa3a137d915` | 跑数站 live 库，缺在线研究上下文表 |
| `selection_research_main` | 2.65G | 9 表，schema `46c1900093a5bb94` | 缺 `selection_exit_watchlist_daily` |
| `model_feature_store_main` | 4.58G | 7 表，schema `98f90e5b85a91479` | 与 Mac/NAS 一致 |
| `atomic_compact_main` | 71.30G | 15 表，schema `cd84ea35e4681948` | Windows 完整跑数库 |

结论：Windows 文件名和入口层已经对齐；物理层仍是旧目录 + junction 别名。若要做到完全物理终态，需要单独迁移，不建议在交易日跑数链路没有停机窗口时直接搬大库。

### 3.3 NAS

主机：`DXP4800PRO-1167`，局域网 SSH `zhangdong@192.168.3.43`

关键路径：

```text
/volume1/docker/market-live-terminal/app
/volume1/docker/market-live-terminal/data
/volume1/docker/market-live-terminal/backups
/volume1/docker/gitea/git/repositories/zhangdong/market-live-terminal.git
```

当前大小：

| 对象 | 大小 |
|---|---:|
| app | 78M |
| data | 225G |
| backups | 380G |
| Gitea bare repo | 72M |

Docker compose 口径：

```text
/volume1/docker/market-live-terminal/data:/runtime-data
FORMAL_MARKET_DATA_ROOT=/runtime-data
LIVE_DATA_ROOT=/runtime-data/live
RESEARCH_CURRENT_ROOT=/runtime-data/research/current
```

关键库：

| 逻辑库 | 大小 | 表数 / schema | 备注 |
|---|---:|---|---|
| `market_data_main` | 0.89G | 29 表，schema `cd9ffb50e6beca9b` | 与 Mac schema 一致 |
| `selection_research_main` | 3.25G | 10 表，schema `edaf615093738273` | 与 Mac schema 一致 |
| `model_feature_store_main` | 4.58G | 7 表，schema `98f90e5b85a91479` | 与 Mac schema 一致 |
| `atomic_compact_main` | 66.88G | 15 表，schema `7c0a8cfdd7ac19a1` | NAS 完整库 |

补充：NAS app 部署目录的 `.deploy_commit` 仍是 `351377a93dda7b2fda9cace4db03968319f56988`。本轮只做 Git 双推和本地路径治理，没有发布 Docker app；规则文档变更不影响线上运行。

## 4. 推荐终态

### 4.1 代码

1. Mac 是主开发控制面。
2. 代码每次关键提交默认双推：
   - `git push nas main`
   - `git push origin main`
3. NAS Gitea 只保存 Git 仓库内容，不保存数据库、不保存整个工作目录。
4. NAS app 运行目录是部署工作副本，不等同于 Gitea bare repo。

### 4.2 数据

1. Mac 保留日常开发与页面功能所需数据，不保留完整 66G/67G atomic 大库。
2. Windows 保留完整跑数库和原始包，是交易日数据生产站。
3. NAS 保留完整线上运行数据卷，也是 Mac 需要时拉完整库的来源。
4. 三端文件名尽量统一；当前完全一致的是 `model_feature_store_main`，Mac/NAS 的 `live` 和 `selection` 也已经一致。
5. Windows 与 Mac/NAS 的 schema 差异暂按职责差异处理，不在无停机窗口时强行改生产跑数库。

### 4.3 备份

1. 用户手动负责整体文件夹冷备。
2. Agent 负责 Docker data 内的运行边界、路径、发布和可恢复性。
3. NAS data 备份建议由用户选定一个 Docker 外部冷备目录后，再做定期 `data/` 快照或 rsync。
4. 不建议把 Gitea 理解为数据备份；Gitea 只备代码和文本型仓库内容。

## 5. 待决策

1. 是否把桌面旧目录的 `.trae` 和 `logs/ytd_doublers_20260430*` 归档进新路径。
2. 是否保留旧 `data/selection/evolution_lab` 与 `opportunity_discovery` 历史实验产物。
3. Windows 是否继续停在 junction 别名层，还是安排一次停机窗口做真实物理目录迁移。
4. Windows 是否做 schema-only migration，让 `live` 和 `selection` 补齐 Mac/NAS 的在线服务表。
5. NAS app 部署目录是否要跟随本轮文档/path commit 更新；如果只是文档规则变更，可暂不部署。
