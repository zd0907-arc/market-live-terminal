# MOD-20260606-03 仓库资产盘点与体积审计

## 1. 基本信息
- 标题：仓库资产盘点与体积审计
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-03-repo-asset-inventory-and-size-audit`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`, `CAP-SELECTION-RESEARCH`
- 关联 STG：`MOD-20260606-02`, `MOD-20260524-01`, `MOD-20260524-04`

## 2. 背景与目标

`Phase 1` 已把 `NAS / research-current` 和三端真相入口收口到当前口径。  
这一阶段先回答一个问题：仓库起始约 `7.8G`，这些体积分别是什么，哪些是正式对象，哪些只是兼容、副本、运行产物或候选归档对象。随后按本卡结论进入 `Phase 3`，继续做低风险清理并复核剩余大对象。

本卡的直接用途：

1. 为 `Phase 3` 文件治理提供“先分类、后动作”的依据。
2. 明确区分仓库内 `data/*`、`.run/*` 和外部正式主数据根 `/Users/dong/Desktop/AIGC/market-data`。
3. 避免把仍有兼容引用的大库误删成“垃圾”。

## 3. 方案与边界

- 做什么：
  1. 盘点顶层目录体积。
  2. 盘点全部大文件、数据库、运行产物。
  3. 对高风险对象补代码 / 文档 / 脚本引用证据。
  4. 给出 `正式保留 / 兼容保留 / 候选归档 / 候选删除` 分类。
- 不做什么：
  1. 不在本阶段直接删除物理文件。
  2. 不把外部 `market-data` 正式主库算进仓库治理体积。
  3. 不处理 `docs/portfolio-ops/*`。

## 4. 核心结论

### 4.1 这 7.8G 主要不是代码，而是本地运行 / 研究产物

| 路径 | 体积 | 结论 |
|---|---:|---|
| `data` | `3.3G` | 仓库内本地数据库、研究输出、sandbox 数据域 |
| `.run` | `1.9G` | 日跑 / 旧盘后 / 回传 / 发布现场产物 |
| `.git` | `302M` | Git 历史包，当前不作为首批治理对象 |
| `docs` | `51M` | 文档与研究材料 |
| `backend` | `14M` | 代码本体很小 |
| `public` | `14M` | 前端静态资源 |
| `src` | `1.9M` | 前端代码本体很小 |

补充事实：

1. `.run/` 和 `data/` 整体都被 `.gitignore` 忽略。
2. 当前仓库体积膨胀的主因是“本地保留的运行现场和研究库”，不是 Git 受控源码。
3. `data/market_heat/*.json`、`data/selection/long_term_trends/**`、`data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/{source_manifest.json,sample_candidates_2026-05-14.json}` 是少量被显式保留的轻量配置 / 研究材料。

### 4.2 必须先分清三类根

| 根 | 当前角色 | 是否算本次 7.8G |
|---|---|---|
| 仓库内 `data/*` | 本地兼容库、研究输出、sandbox、少量正式配置 | 是 |
| 仓库内 `.run/*` | 跑数 / 回传 / 发布现场产物 | 是 |
| 外部 `/Users/dong/Desktop/AIGC/market-data` | Mac 正式主读数据根 | 否 |

结论：

1. 当前“仓库 8G”问题，主要是仓库内忽略目录膨胀。
2. 不能把仓库内 `data/market_data.db`、`data/selection/selection_research.db` 直接等同于外部正式主库。

## 5. 大文件与数据库盘点

### 5.1 `> 1GB`

| 对象 | 体积 | 当前判定 | 关键证据 |
|---|---:|---|---|
| `market_data_history.db` | `1.9G` | 仓库根历史兼容库；不是当前正式主链 | `backend/scripts/merge_historical_db_local.py` 直接引用；`docs/ops/market-data-reclassification-plan.md` 已把它列为历史兼容对象 |
| `data/market_data.db` | `1.8G` | 仓库内兼容 / fallback 轻量消费库；不能直接删 | `ops/start_local_backend_with_atomic.sh`、`backend/scripts/build_atomic_trade_from_history.py`、`backend/scripts/l2_wait_then_backfill.py` 等仍直接引用；`docs/03_DATA_CONTRACTS.md` 已标注为 repo 内 fallback |
| `.run/postclose_l2` | `1.5G` | 旧盘后兼容链路现场产物；高优先级候选归档 | `ops/check_postclose_l2_status.sh`、`backend/scripts/run_postclose_l2_daily.py`、`docs/ops/postclose-l2-runbook.md` 仍依赖其状态文件 |
| `data/selection` | `1.4G` | 仓库内研究输出混合区；内部还需再分层 | 含 `selection_research.db`、`opportunity_discovery`、`evolution_lab`、`long_term_trends` 等多类资产 |

### 5.2 `100MB ~ 1GB`

| 对象 | 体积 | 当前判定 | 关键证据 |
|---|---:|---|---|
| `data/selection/selection_research.db` | `954M` | 仓库内兼容 / fallback 研究库；不能直接删 | 多个研究脚本默认指向 `selection/selection_research.db`；`docs/contracts/storage.md` 已明确为 repo 内兼容副本 |
| `.run/daily_new_framework` | `367M` | 当前正式日跑现场产物；保留但要做保留周期 | `backend/scripts/run_daily_new_framework.py`、`ops/check_daily_new_framework_status.sh` 依赖 `latest.json` |
| `data/selection/opportunity_discovery/walk_forward_2024_daily_strict_v0_1/daily_scored_candidates.csv` | `212M` | 大型研究导出；优先列入候选归档，不应长期顶层漂浮 | 位于 `opportunity_discovery` 研究输出目录，不是正式运行入口 |
| `.git/objects/pack/pack-*.pack` | `209M` | Git 历史体积，不属于首批文件治理目标 | `git count-objects -vH` 显示 pack 总量约 `209.49 MiB` |
| `.run/daily_new_framework/20260604/processed/atomic_day_delta_20260604.db` | `169M` | 正式日跑某日 processed 产物；候选归档 | 位于 `.run/daily_new_framework/<date>/processed/` |
| `.run/daily_new_framework/20260605/processed/atomic_day_delta_20260605.db` | `169M` | 同上 | 同上 |

### 5.3 其他高风险库 / 影子库

| 对象 | 体积 | 当前判定 | 关键证据 |
|---|---:|---|---|
| `market_data.db` | `51M` | 仓库根旧轻量库 / 兼容对象；不是正式主链 | `backend/scripts/merge_historical_db_local.py` 把它当 live db；表结构明显是早期轻量盯盘口径 |
| `data/market_data_history_202602_fix.db` | `80M` | 历史修复快照；候选归档 | 文件名已表达一次性修复语义，当前未见正式入口引用 |
| `backend/app/market_data.db` | `152K` | 小样本库 / sample 对象 | 文档多处明确为 sample；库内只有 `history_daily`、`history_30m` 两张小表 |
| `backend/market.db` | `0B` | shadow 空壳 | 文档多处明确为 shadow；当前只会误导，不承担主链 |
| `backend/app/db/market_data.db` | `0B` | shadow 空壳 | 同上 |
| `data/market_heat/market_heat.db` | `0B` | 高风险误导残留；优先候选删除 | 代码真正依赖的是 `data/market_heat/*.json` 规则文件与外部 `market-data/market_heat/*.db`，未见正式入口读取该空库 |

## 6. 资产角色分类

### 6.1 正式保留

| 路径 | 角色 | 说明 |
|---|---|---|
| `data/market_heat/*.json` | 正式规则 / 配置资产 | `backend/app/services/market_heat.py`、`backend/scripts/build_tradable_theme_map.py`、`backend/scripts/analyze_hot_sector_granularity.py` 直接读取 |
| `data/sandbox/review_v2/*` | sandbox 隔离数据域 | `backend/scripts/sandbox_review_v2_backfill.py`、`docs/03_DATA_CONTRACTS.md` 明确保留 |
| `data/sandbox_review.db` | sandbox 兼容主库 | `backend/app/routers/sandbox_review.py`、`backend/app/db/sandbox_review_db.py` 直接读取 |
| `.run/daily_new_framework/latest.json` 与近期待处理现场 | 正式日跑状态现场 | 当前主链状态查看依赖它 |
| `.run/nas_research_releases/*` | NAS 发布现场 | `ops/build_nas_research_release_manifest.sh`、`ops/upload_nas_research_release.sh` 直接使用 |

### 6.2 兼容保留

| 路径 | 角色 | 说明 |
|---|---|---|
| `data/market_data.db` | repo 内 fallback 轻量消费库 | 仍有脚本直接以默认路径读取 |
| `data/selection/selection_research.db` | repo 内 fallback 研究库 | 仍有研究脚本直接以默认路径读取 |
| `data/user_data.db` | repo 内 fallback 用户态库 | 库内只有 `app_config`、`watchlist`；真实用户态数据优先走外部 `market-data/live` 或兼容解析链 |
| `market_data.db` | 仓库根旧轻量兼容库 | 个别历史脚本仍直接读取 |
| `market_data_history.db` | 仓库根历史兼容库 | 仍被 merge 脚本点名 |
| `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db` | shadow / sample / 排障对象 | 当前应继续保留语义说明，但不当正式库看待 |

### 6.3 候选归档

| 路径 | 原因 | Phase 3 建议 |
|---|---|---|
| `.run/postclose_l2/<date>/*` | 旧兼容链路的历史日现场过重 | 保留 `latest.json`、最近失败现场、最近成功摘要，其余转归档目录 |
| `.run/mac_sync_backfill_*` | 跨端回传批次现场 | 只留最近可回滚批次和摘要 |
| `.run/tmp_market_heat_release_check` | 临时 release 检查现场 | 收成单份摘要或直接清空临时目录 |
| `data/selection/opportunity_discovery/*` 中的大型 walk-forward 导出 | 研究输出体积大，且不是正式入口 | 下沉到研究归档区，顶层只留摘要 / manifest |
| `data/selection/evolution_lab/*` 的模型 zip / 大型训练结果 | 训练现场产物，不应与正式研究入口平铺 | 下沉归档或按实验批次整理 |
| `data/sandbox_exports/*` | 导出物，不是正式运行链 | 归档到 artifacts 区或直接按用途保留最近版本 |
| `data/market_data_history_202602_fix.db` | 一次性修复快照 | 改为 archive 命名与归档位置 |

### 6.4 候选删除

| 路径 | 原因 | 当前判断 |
|---|---|---|
| `data/market_heat/market_heat.db` | `0B` 残留，正式代码未见读取；只会误导 AI/维护者 | Phase 3 第一批高置信候选删除 |

## 7. Phase 3 直接执行边界

### 7.1 下一步优先动谁

1. `data/market_heat/market_heat.db`
2. `.run/tmp_market_heat_release_check`
3. `.run/mac_sync_backfill_*`
4. `.run/postclose_l2` 历史日目录
5. `data/sandbox_exports/*`
6. `data/selection/opportunity_discovery/*` 与 `data/selection/evolution_lab/*` 中的大型导出 / 模型包

### 7.2 现在不能直接动谁

1. `data/market_data.db`
2. `data/selection/selection_research.db`
3. `.run/daily_new_framework`
4. `data/sandbox/review_v2/*`
5. `data/sandbox_review.db`
6. `data/market_heat/*.json`
7. `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db`

原因：

1. 这些对象要么仍有代码默认引用。
2. 要么已经在文档契约里被定义为兼容对象。
3. 要么本身就是当前正式配置 / 状态现场。

## 8. 验收标准（Given / When / Then，绝对时间）

- Given `2026-06-06` 仓库工作区总占用约 `7.8G`，且 `Phase 1` 已固定三端真相入口。
- When 完成目录体积、数据库、大文件和引用盘点，并对关键对象做角色分类。
- Then 应能明确回答：
  1. 这 `7.8G` 主要由哪些目录构成；
  2. 哪些是正式对象，哪些只是兼容、副本、运行现场；
  3. `Phase 3` 应先治理谁，不该碰谁。

## 9. 风险与回滚

主要风险：

1. 把仍有默认脚本引用的兼容大库误判为“可删垃圾”。
2. 把 `.run` 现场一把清掉，导致状态回溯和排障证据丢失。
3. 把外部 `market-data` 正式主库与仓库内 ignored 副本混为一谈。

回滚原则：

1. `Phase 3` 先做归档 / 摘要化，再做删除。
2. 每一批治理只处理一个目录族。
3. 删除前再做一次局部引用复核。

## 10. 结果回填

- 实际改动：
  - 新增本卡，固化 `Phase 2` 的仓库资产盘点与分类结论。
  - 后续已按本卡推进 `Phase 3` 前 4 批治理：删除 `data/market_heat/market_heat.db`、`.run/tmp_market_heat_release_check/`、`.run/mac_sync_backfill_*`、`.run/relay_test_2/`、`data/sandbox_exports/`，并裁掉 `.run/postclose_l2` 历史 `artifacts/*.db` 与 `walk_forward_2024_daily_strict_v0_1/daily_scored_candidates.csv`。
- 验证结果：
  - 已完成目录体积盘点：`du -sh . .run data docs backend src public .git`
  - 已完成大文件盘点：`find . -type f -size +100M`
  - 已完成数据库盘点：`find . -type f \\( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.duckdb' \\)`
  - 已完成关键引用审计：`rg` 复核 `market_data.db`、`selection_research.db`、`.run/postclose_l2`、`.run/daily_new_framework`、`sandbox`、`market_heat`
  - 当前已压缩到约 `6.2G`；`.run` 已从约 `1.9G` 降到约 `507M`，`data/selection/opportunity_discovery` 已降到约 `170M`
- 遗留问题：
  - `Phase 3` 仍需把 `daily_new_framework` 历史 processed 增量、`evolution_lab` 训练导出、根目录 `market_data.db` / `market_data_history.db` 的兼容边界继续收口。
  - repo 内 `data/market_data.db` 与 `data/selection/selection_research.db` 仍是兼容运行资产，当前不应直接删除。
