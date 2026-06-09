# MOD-20260606-10 仓库与 market-data 结构治理计划

## 1. 基本信息
- 标题：仓库与 `market-data` 结构治理计划
- 状态：`ACTIVE`
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-10-repo-and-market-data-structure-governance-plan`
- 前置任务：`MOD-20260606-02`, `MOD-20260606-09`
- 当前接手文档：`docs/changes/MOD-20260606-11-repo-and-market-data-governance-handoff.md`

## 2. 这张卡解决什么问题

上一轮综合治理已经把三件事收口：

1. `Mac / Windows / NAS` 的运行真相统一了。
2. `research/current` 的发布链、回滚链和运行文档统一了。
3. 仓库里第一批明显的大文件和运行垃圾清掉了。

但用户现在指出的核心问题是另外一层：

1. Finder 视角下目录还是乱。
2. 仓库里的脚本和兼容库还是太多，看不出哪个是正式入口。
3. 外置 `market-data` 已经变成一个约 `86G` 的正式数据根，但里面仍把正式库、缓存、研究导出、修复副本、空壳对象混放在一起。

这张卡不再处理“运行真相是不是对的”，而是处理“物理目录结构是不是清楚”。

## 3. 当前基线

`2026-06-06` 复核时，当前现场是：

| 对象 | 当前体积 / 数量 | 当前判断 |
|---|---:|---|
| 仓库总占用 | `6.2G` | 比治理前下降，但仍不清爽 |
| repo `data/` | `5.0G` | 兼容库、研究输出、历史对象混合区 |
| repo `.run/` | `507M` | 当前正式日跑现场 + 少量保留现场 |
| `backend/scripts` 文件数 | `202` -> `185` | 已开始下降，但仍远超“一眼能懂”范围 |
| `ops` 文件数 | `50` | 正式入口、NAS 运维、Windows 工具、历史脚本混放 |
| `docs/changes` 文件数 | `19` | 当前 still readable，但还可以继续压缩 |
| 外置 `market-data/` | `86G` | 当前正式主数据根，但目录仍未物理收口 |

补充事实：

1. repo 内 `data/market_data.db` 与 `data/selection/selection_research.db` 不是当前默认正式主库，而是兼容 / fallback 副本。
2. Mac 当前正式主读根目录是 `/Users/dong/Desktop/AIGC/market-data`。
3. NAS 当前正式在线查询根目录是 `/volume1/docker/market-live-terminal/data/live` 与 `/volume1/docker/market-live-terminal/data/research/current`。
4. 当前三端对齐主要是“职责、路径解析、发布链、文档真相”对齐，不等于“Mac 与 NAS 上所有历史目录都已经物理整理干净”。

## 4. 当前已完成与未完成

### 4.1 已完成

1. `Mac / Windows / NAS` 角色和运行口径已经统一。
2. `research/current` 发布、回滚、检查脚本已经成体系。
3. 高曝光文档已经不再把 repo 内 `data/` 讲成默认正式主库。
4. 仓库体积已从约 `7.8G` 降到约 `6.2G`。

### 4.2 未完成

1. `backend/scripts` 还没有整理成正式入口、研究脚本、历史兼容脚本几层。
2. `ops` 还没有按正式入口、NAS 运维、Windows 辅助、历史兼容做物理或至少文档分层。
3. repo 内 fallback / shadow / sample 对象仍然太显眼。
4. `market-data` 还没有收口到 `live / research / cache / artifacts / incoming` 目标结构。
5. 没有一套足够明确的“以后 AI 不准再往根目录乱写”的治理约束。

## 5. 三端当前真实对齐方式

| 端 | 当前正式职责 | 当前正式数据位置 |
|---|---|---|
| Mac | 开发控制台、本地研究站、文档与发布控制台 | `/Users/dong/Desktop/AIGC/market-data` |
| Windows | 数据主站、盘中 crawler、盘后正式跑数与主产出 | Windows 本地正式产出目录，随后同步到 Mac / NAS |
| NAS | 在线服务、在线轻量库、`research/current` 在线查询、发布与回滚节点 | `/volume1/docker/market-live-terminal/data/live` + `/volume1/docker/market-live-terminal/data/research/current` |

这里要特别固定两个判断：

1. 我已经把三端的“正式入口和正式说法”对齐了。
2. 我还没有把 Mac `market-data` 和 NAS 上所有历史文件夹做完一次彻底的物理整理。

## 6. 外置 `market-data` 当前最值得处理的对象

当前复核到的高关注对象：

| 对象 | 当前体积 | 当前判断 |
|---|---:|---|
| `atomic_facts/market_atomic_mainboard_compact_current.db` | `66G` | 正式底座，不动 |
| `market_data.db` | `4.6G` | 正式轻量消费库，不动 |
| `selection/selection_research.db` | `3.2G` | 正式研究库，不动 |
| `selection/model_feature_store.db` | `4.5G` | 正式模型特征库，不动 |
| `selection/model_feature_store.db.backup_20260602_101012` | `4.5G` | 高优先级候选复核对象 |
| `selection/model_feature_store.db.repaired` | `2.9G` | 高优先级候选复核对象 |
| `market_feature_store.db` | `0B` | 高风险空壳残留 |
| `atomic_facts/market_atomic_mainboard_full_reverse.db` | `0B` | 高风险历史残留 |
| `fine_theme_member_daily` | 正式表已确认存放在 `market_heat/fine_theme_heat_daily.db` 内 | 独立 `fine_theme_member_daily.db` 文件已判定为旧表达，不再保留 |
| `incoming/` | 当前为空目录 | 正式导入落地区，保留 |

结论：

1. 真正占空间的正式主库并不多，主要是 `atomic_facts`、`market_data.db`、`selection`。
2. 当前最可疑的冗余对象，是 `model_feature_store` 的备份 / repaired 双副本，以及多处 `0B` 空壳对象。

## 7. 本轮执行边界

这张卡要做：

1. 先完成目录角色盘点和文档冻结。
2. 先固化正式入口、兼容入口、历史入口的边界。
3. 先整理低风险缓存、产物、空壳对象的治理顺序。
4. 再决定哪些对象可以物理移动、归档或删除。

这张卡先不做：

1. 不盲删正式大库。
2. 不把 `docs/portfolio-ops/*` 纳入治理。
3. 不在未做引用审计前直接搬 repo 内 fallback 库。
4. 不直接重命名 Windows 侧正式物理库。

## 8. 执行方式

后续进入目标模式时，默认按“总控 + 并行子 Agent”推进：

1. 总控负责基线、边界、文档回写和最终合并。
2. 子 Agent 并行负责：
   - `backend/scripts` 分类盘点
   - `ops` 分类盘点
   - `market-data` 大文件与疑似冗余对象复核
   - 文档引用与待归档对象复核

但用户沟通里不用再讲代号，只讲白话结论。

## 9. 执行顺序

### 第一步：先做目录清单冻结

目标：

1. 固化 `backend/scripts`、`ops`、`docs/changes`、repo `data/`、外置 `market-data/` 的当前 inventory。
2. 给每个噪音目录产出“正式 / 兼容 / 研究 / 历史 / 候选删除”分类。

通过标准：

- 能回答每个大目录里哪些是正式入口，哪些只是历史负担。

### 第二步：先做 repo 结构降噪

目标：

1. 收紧 `backend/scripts` 默认认知，先文档分层，再决定是否做物理迁移。
2. 收紧 `ops` 默认认知，明确白名单入口和历史脚本族。
3. 继续压缩 `docs/changes` 顶层，只保留当前真相母卡、当前活跃治理卡和必要阶段总结。

通过标准：

- 新会话再进入项目时，不会一上来被 `backend/scripts`、`ops`、`docs/changes` 顶层误导。

### 第三步：处理 repo 内 fallback / shadow / sample 对象

目标：

1. 固化 repo 内 `data/*` 的保留边界。
2. 固化 `backend/sample_data/shadow/market.db`、`backend/sample_data/shadow/market_data.db`、`backend/sample_data/examples/market_data_sample.db` 的最终去向。
3. 决定哪些对象继续兼容保留，哪些对象可以迁入专门目录。

通过标准：

- 仓库里不再出现“看起来像正式主库，其实不是”的高误导对象。

### 第四步：处理外置 `market-data` 结构

目标结构：

```text
market-data/
  live/
  research/current/
  research/staging/
  research/archive/
  cache/
  artifacts/
  incoming/
```

执行顺序：

1. 先迁缓存和研究导出。
2. 先处理 `0B` 空壳和显式历史残留。
3. 再复核 `model_feature_store.db.backup_*`、`model_feature_store.db.repaired` 这种大副本。
4. 最后才碰正式主库的物理迁移。

通过标准：

- `market-data` 根目录不再同时堆正式库、缓存、专题 JSON、修复副本和空壳对象。

### 第五步：补反熵规则

目标：

1. 固化“新产物写到哪里”的规则。
2. 固化“新脚本什么时候能进正式入口”的规则。
3. 固化“完成后的变更卡什么时候归档”的规则。

最小规则：

1. 新正式库只能落到 `market-data/live` 或 `market-data/research/current`。
2. 新缓存只能落到 `market-data/cache`。
3. 新研究导出只能落到 `market-data/artifacts` 或 repo 明确约定的研究目录。
4. 未进入白名单的 `ops` / `backend/scripts` 默认按非正式入口处理。

## 10. 第一批低风险候选对象

下一轮优先复核以下对象，优先级从高到低：

1. `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db.backup_20260602_101012`
2. `/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db.repaired`
3. `/Users/dong/Desktop/AIGC/market-data/market_feature_store.db`
4. `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
5. `fine_theme_member_daily` 的正式表表达与旧独立文件表达冲突
6. `/Users/dong/Desktop/AIGC/market-data/incoming/`

## 11. 验收标准

- Given 上一轮真相治理已完成，但目录观感仍混乱。
- When 完成 repo 目录分层、`market-data` 结构方案冻结、低风险对象审计和待办回写。
- Then 应能明确回答：
  1. repo 内两个大库为什么还在；
  2. `market-data` 里哪些是正式主库、哪些是缓存、哪些是疑似冗余；
  3. Mac / Windows / NAS 现在如何对齐；
  4. 后续应该按什么顺序继续做物理整理。

## 12. 当前已落地结果

`2026-06-06` 本轮已经先完成第一批低风险结构治理：

1. `docs/changes` 顶层已缩到只保留 6 个文件：
   - `MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
   - `MOD-20260606-10-repo-and-market-data-structure-governance-plan.md`
   - `MOD-20260606-11-repo-and-market-data-governance-handoff.md`
   - `README.md`
   - `README_STAGE_SUMMARY.md`
   - `TEMPLATE_CHANGE_CARD.md`
2. 已完成的执行卡、清理卡、功能交付卡已下沉到 `docs/archive/changes/`。
3. `market-data/artifacts/model_feature_store/` 已建立，并下沉：
   - `selection/model_feature_store.db.backup_20260602_101012`
   - `selection/model_feature_store.db.repaired`
4. 已删除两个明确 `0B` 空壳：
   - `/Users/dong/Desktop/AIGC/market-data/market_feature_store.db`
   - `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
5. `market-data/artifacts/market_heat/` 已建立，并把 `market_heat/` 根目录中的专题 `json/md` 导出下沉过去。

当前 `market_heat/` 根目录已明显收紧，只保留：

1. 正式库：
   - `fine_theme_heat_daily.db`
   - `fine_theme_heat_daily_v2.db`
   - `fine_theme_heat_forecast.db`
   - `stock_sector_map.db`
   - `tradable_theme_map.db`
   - `hot_theme_low_position_l2_samples.db`
2. 正式元数据：
   - `latest.json`
   - `stock_sector_map_latest.json`
   - `sector_boards_latest.json`
   - `tradable_theme_map_latest.json`
3. `hot_theme_low_position_l2_samples_2025-04-16_2026-04-28.csv` 也已下沉到 `artifacts/market_heat/`

6. `backend/scripts` 已完成第二批最小物理分层：
   - `backend/scripts/maintenance/l2_repair/`
     - `l2_wait_then_backfill.py`
     - `l2_repair_failed_samples.py`
     - `l2_repair_missing_daily_symbols.py`
     - `l2_review_empty_samples.py`
   - `backend/scripts/legacy/history_repair/`
     - `backfill_history.py`
     - `backfill_history_1m.py`
     - `backfill_local_history.py`
     - `backfill_local_symbol_from_windows_raw.py`
     - `build_atomic_trade_from_history.py`
7. 第二批新迁脚本已同步修正仓库根路径解析，避免迁目录后仍按旧层级计算 `ROOT_DIR / REPO_ROOT` 而跑错库或跑错导入根。
8. `build_cycle_return_snapshot.py`、`build_cycle_return_sector_report.py` 已从默认读取 repo `data/selection/selection_research.db` 改成默认跟随 `RESEARCH_CURRENT_ROOT/selection/selection_research.db`，只在未显式注入时才按统一 resolver 解释。
9. `atomic_facts/shadow/` 已复核，不是空目录；当前是指向 `../market_atomic_mainboard_compact_current.db` 的符号链接壳，现阶段只记为兼容对象，不再按“可直接删除空壳”处理。

## 13. 当前仍保留的边界

这轮故意没有继续动以下对象：

1. repo 内 `data/market_data.db`
2. repo 内 `data/selection/selection_research.db`
3. `/Users/dong/Desktop/AIGC/market-data/incoming`
4. `backend/sample_data/shadow/market.db`、`backend/sample_data/shadow/market_data.db`、`backend/sample_data/examples/market_data_sample.db`

## 14. 本轮新增实质结果

除了前面的 `docs/changes` 与 `market-data` 结构治理，本轮还完成了：

1. 将后端最误导的 shadow/sample 库从原位置下沉：
   - `backend/market.db` -> `backend/sample_data/shadow/market.db`
   - `backend/app/db/market_data.db` -> `backend/sample_data/shadow/market_data.db`
   - `backend/app/market_data.db` -> `backend/sample_data/examples/market_data_sample.db`
2. 已同步更新核心文档，不再把这些对象写成后端目录里的活跃运行库。
3. 已确认 `fine_theme_member_daily` 当前作为正式表存在于 `market_heat/fine_theme_heat_daily.db` 内，而不是依赖一个独立的 `fine_theme_member_daily.db` 文件。
4. `ops` 已完成第一批“物理迁移后路径收口”：
   - `ops/nas/*` 与 `ops/legacy/*` 已修正根目录解析，不再因迁目录导致脚本天然找错仓库根路径。
   - NAS 发布链、crawler 链、旧兼容链的脚本内部互调路径已改到 `ops/nas/*`、`ops/legacy/*`、`ops/windows/*` 新结构。
   - `sync_to_windows.sh` 与 `backend/scripts/run_daily_new_framework.py` 也已改到新的脚本路径。
5. 活跃入口文档已完成第一批回写：
   - `docs/04_OPS_AND_DEV.md`
   - `docs/AI_QUICK_START.md`
   - `docs/ops/mac-local-research.md`
   - `docs/ops/windows-data-station.md`
   - `docs/ops/postclose-l2-runbook.md`
   - `docs/ops/nas-crawler-cutover-runbook.md`
   - `docs/ops/nas-research-release-runbook.md`
   - `docs/ops/nas-public-domain-cloudflare.md`
   - `docs/ops/nas-migration-execution-plan.md`
   - `docs/ops/atomic-script-families-boundary.md`
   - `docs/ops/backend-script-families-boundary.md`
6. 外置 `market-data` 又完成一批低风险对象下沉：
   - `legacy_market_merge_report_20260425.json` -> `artifacts/reports/`
   - `selection/model_market_index_daily_validation_20260523.json` -> `artifacts/selection/`
   - 清掉了根目录、`atomic_facts/`、`market_heat/` 下的 `.DS_Store`

原因：

1. 前两者仍是兼容 / fallback 副本，不能在未补迁移方案前直接动。
2. `incoming` 属于正式结构的一部分，只是当前为空。
3. `backend/*market*.db` 仍需和 `T-034` 一起决定最终目录去向。

## 15. 当前真实进度

到这一步，这张治理卡的真实状态是：

1. `docs/changes` 顶层归档收口，已完成；当前保留 6 个文件，其中 `MOD-20260606-11` 是接手交接入口。
2. 外置 `market-data` 第一批低风险结构治理，已完成。
3. `ops` 物理迁移后的路径与文档收口，已完成第一批闭环。
4. repo 内 fallback 库最终边界，未完成。
5. `backend/scripts` 物理分层或最小迁移，已完成两批低风险对象。
6. `market-data` 的 `cache / latest.json / models / shadow symlink / wal-shm` 后续收口，未完成。

下一轮建议顺序：

1. 先决定 repo 内 `data/market_data.db`、`data/selection/selection_research.db` 的最终保留策略。
2. 继续处理 `market-data` 下仍显眼但不属于正式主库的一批对象：
   - `market_heat/cache/`
   - `market_heat/eastmoney_sector_cache/`
   - `market_heat/models/`
   - `market_heat/*_latest.json`
   - `atomic_facts/shadow/`
   - `*.db-wal / *.db-shm`
3. 继续 `backend/scripts` 的最小物理迁移，当前已完成：
   - `benchmark_atomic_*` -> `backend/scripts/maintenance/bench/`
   - `audit_l2_order_event_codes.py` -> `backend/scripts/maintenance/audit/`
   - `l2_wait_then_backfill.py`、`l2_repair_failed_samples.py`、`l2_repair_missing_daily_symbols.py`、`l2_review_empty_samples.py` -> `backend/scripts/maintenance/l2_repair/`
   - `build_local_research_snapshot.py` -> `backend/scripts/legacy/compat/`
   - `backfill_history.py`、`backfill_history_1m.py`、`backfill_local_history.py`、`backfill_local_symbol_from_windows_raw.py`、`build_atomic_trade_from_history.py` -> `backend/scripts/legacy/history_repair/`
   - `merge_historical_db.py`、`merge_historical_db_local.py` -> `backend/scripts/legacy/history_merge/`
   下一步再考虑是否继续收 `cycle return`、`report builder`、`watchlist snapshot` 这类仍有活跃研究入口引用的脚本。

## 16. 2026-06-06 续接总控点评

本轮接手复核后的判断：

1. 前序工作方向正确：已经先把运行真相、三端职责、NAS 发布链和高误导对象下沉做完，没有把清理动作建立在猜测上。
2. 当前风险已经从“系统口径混乱”转为“物理搬迁未收口”：`git status` 里仍有大量 `D` + `??`，说明目录迁移需要形成可审计闭环后再扩大范围。
3. 文档体系整体有效，但维护成本高：主卡、交接文档、`07_PENDING_TODO`、`AI_HANDOFF_LOG` 必须一起更新，否则真相会再次分叉。
4. `07_PENDING_TODO` 曾保留已完成项，和“只保留 ACTIVE/BLOCKED”的规则不一致；续接时已把 `T-033`、`T-035` 从活跃待办中移出。
5. `market-data` 缺少数据根自描述入口；已补 `/Users/dong/Desktop/AIGC/market-data/README.md`，用于防止新 AI 把正式库、缓存、artifacts 和运行期临时文件混看。

## 17. 下一轮推进计划

下一轮按“先收口，后扩张”推进。
本轮已先把 active residual fallback 收紧到 `ops/start_local_research_station.sh`、`ops/run_model_feature_store_batch.sh`、`backend/app/services/intraday_evolution_lab.py` 这类少数入口。

### P0. 先固定当前迁移闭环

目标：

1. 不再扩大物理迁移范围。
2. 先复核当前 `backend/scripts`、`ops`、`docs/archive/changes` 的删除和新增是否一一对应。
3. 形成可提交、可回滚、可审计的结构治理批次。
4. 本轮已顺手修掉 3 个活跃旧路径残留：
   - `backend/scripts/run_daily_new_framework.py` -> `ops/nas/nas_run_phase_b_release.sh`
   - `backend/scripts/run_postclose_l2_daily.py` -> `ops/windows/win_prepare_l2_day.bat`、`ops/windows/win_run_l2_shard.bat`
   - `docs/AI_HANDOFF_LOG.md` 中对应旧入口描述
5. `2026-06-09` 已把 `backend/scripts/run_daily_new_framework.py` 补成“研究主链成功后，默认继续触发本地 `postclose_l2` L2 历史补齐 + `stock_universe_meta` 刷新”的后处理闭环；但这一步仍只落在 Mac 本地 `live/market_data.db`，没有把 NAS `live` 同步重新抬回 `--sync-nas` 主语义。

验收：

1. `git status` 能按主题分组解释。
2. 新迁脚本语法检查通过。
3. 活跃文档不再引用已迁旧路径。

### P1. repo fallback 库边界

先只做引用审计和文档定性，不直接删库。

当前重点对象：

1. `data/market_data.db`
2. `data/user_data.db`
3. `data/selection/selection_research.db`
4. `data/market_data_history.db`
5. `data/market_data_history_202602_fix.db`
6. `data/legacy/root_market_data*.db`

本轮已完成的入口收紧：

1. `backend/app/services/intraday_evolution_lab.py`：去掉显式 repo `data/...` 候选
2. `ops/start_local_research_station.sh`：缺 formal 根时不再静默落到 repo `data/`
3. `ops/run_model_feature_store_batch.sh`：缺 formal 根时不再静默落到 repo `data/`
4. `backend/scripts/run_postclose_l2_daily.py`：本地默认根改为 formal root，cloud 校验 / failure summary / merge 改为显式解析云端正式 `market_data.db`
5. `ops/legacy/start_local_backend_with_atomic.sh`：不再静默回 repo `data/`，缺 formal 根或缺 DB 时直接失败
6. `backend/app/core/config.py`：默认 resolver 先跟随显式 DB 路径与 formal root，不再隐式落回 repo `data/`
7. repo `data/` 已补 `README.md` 与 `data/selection/README.md`，把三类兼容库和研究产物边界写死

当前 active residual fallback：

1. 已清零；下一步不再继续找“默认入口 fallback”，转回 repo fallback 库的保留策略与脚本族边界。

### P2. market-data 第二批对象

先分类，不删正式库。

当前对象：

1. `market_heat/cache/`：页面快照缓存，约 `291M`
2. `market_heat/eastmoney_sector_cache/`：接口缓存，约 `17M`
3. `market_heat/models/`：模型产物，约 `24M`
4. `market_heat/shadow_candidates/`：shadow 候选产物，约 `80K`
5. `market_heat/*_latest.json`：运行元数据，当前保留
6. `atomic_facts/shadow/`：兼容 symlink 壳，当前保留
7. `*.db-wal / *.db-shm`：SQLite 运行期文件，不当长期资产解释

本轮新增落地：

1. `/Users/dong/Desktop/AIGC/market-data/live/market_data.db`
2. `/Users/dong/Desktop/AIGC/market-data/live/user_data.db`
3. `/Users/dong/Desktop/AIGC/market-data/research/current/{atomic_facts,selection,market_heat}`
4. `/Users/dong/Desktop/AIGC/market-data/cache/{market_heat,eastmoney_sector_cache}`
5. `/Users/dong/Desktop/AIGC/market-data/artifacts/market_heat/models`

说明：

1. `2026-06-07` 已完成 Mac 本地最终物理搬迁：`live/` 与 `research/current/` 当前承载正式库实体。
2. `2026-06-08` 已删除 root 旧入口 `market_data.db / user_data.db / atomic_facts / selection / market_heat`，不再继续保留兼容软链。
3. `market_heat/*_latest.json` 继续保留在 `research/current/market_heat/` 旁，按运行元数据理解。
4. `atomic_facts/shadow/` 继续保留为兼容壳。
5. `*.db-wal / *.db-shm` 继续按 runtime residue 处理，不纳入长期资产主清单。

### P3. 反熵规则落地

规则先写入文档，再改代码默认值。

最小规则：

1. 新正式轻量库只能进入 `market-data/live/`。
2. 新正式研究库只能进入 `market-data/research/current/` 或当前兼容正式目录，不能写回 repo `data/` 当默认真相。
3. 新缓存进入 `market-data/cache/`。
4. 新研究导出进入 `market-data/artifacts/` 或已有 repo 研究目录，并必须标明非正式主库。
5. 新脚本进入 `backend/scripts` 前必须有角色分类：runtime、research、maintenance、legacy。
6. 旧 repo-data / flat-data 脚本若仍需保留，必须在文件头显式标注“兼容链，不是当前默认正式入口”。

补充：

1. `ops/bench`、`ops/windows` 当前已复核为纯结构迁移。
2. `docs/archive/changes` 已通过恢复 `MOD-20260606-02` 的 archive 内容为原始归档版本，补齐纯结构闭环。
3. `README`、`AI_QUICK_START`、`01_SYSTEM_ARCHITECTURE`、`04_OPS_AND_DEV`、`mac-nas-collaboration` 已补齐五段式数据根规则。
4. `deploy/docker-compose.yml`、`deploy/docker-compose.nas-lite.yml`、`sync_cloud_db.sh`、`sync_local_to_cloud.sh`、`deploy_to_cloud.sh` 已加“旧 flat-data 兼容链”提醒。

## 18. 2026-06-08 三线收口结果

本轮按“云端线 -> report 线 -> 删库后的文档闭环”收口，当前真实状态如下：

1. NAS 已明确为唯一正式线上主链；old cloud 只按 `legacy/emergency` 理解。
2. Windows crawler 默认 ingest 目标已统一到 NAS；旧 `CLOUD_API_URL` 只保留历史变量名，不再代表默认 cloud 目标。
3. report / research 产出边界已固定：
   - `market-data/research/current/` = 正式研究真相
   - `docs/selection/*`、`docs/strategy-rework/*` = 人读结论
   - `market-data/artifacts/*` = 仓外导出
   - `.run / logs / public/research / dist/research` = 运行态与页面副产物
4. repo 内 `data/market_data.db`、`data/user_data.db`、`data/selection/selection_research.db` 当前默认不存在；只有显式 legacy 兼容链才允许重建。
5. `market-data` root 旧入口已删除；当前正式库实体只承认 `live/` 与 `research/current/`。
6. 本轮之后，结构治理的主风险不再是“默认入口走错”，而是后续是否还要继续做更深的脚本物理分层和旧 cloud 彻底退役。
