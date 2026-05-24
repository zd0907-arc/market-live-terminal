# MOD-20260519-02-process-material-risk-grading-batch1

## 1. 基本信息
- 标题：过程材料风险分级与第一批降噪对象清单
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260519-02-process-material-risk-grading-batch1`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 关联 STG：`N/A`

## 2. 背景与目标
- `T-033` 当前第一批工作不是删文件，而是先回答一个更关键的问题：
  - 仓库里哪些过程材料会**直接误导当前实现**；
  - 哪些只是**高噪音但暂不致命**；
  - 哪些虽然历史很多，但其实已经处在合理归档层。
- 本卡只做**风险分级**和**第一批降噪目标识别**，不做删除执行。

## 3. 分级规则

### P0：高误导风险
满足任一条件即归为 `P0`：
1. 标题/文件名像“当前状态 / current / final / roadmap / project status / release / integration plan”；
2. 正文仍大量使用“当前分支 / 当前 worktree / 当前默认入口 / 当前方案”这类口径；
3. 但实际上已经被更高层母卡或核心入口覆盖；
4. 且当前文件没有明显提示“先看当前母卡 / 当前真相入口”。

### P1：高噪音风险
满足以下特征的归为 `P1`：
1. 不一定直接误导，但很容易被误当成现行入口；
2. 更像阶段性实验、执行记录、专题研究沉淀、脚本族集合；
3. 需要后续降级、归档或从默认入口移开。

### P2：可保留历史资料
满足以下特征的归为 `P2`：
1. 已在 `_archive/`、`archive/` 或明显历史目录；
2. 已经具备明确的“历史/归档”标识；
3. 虽然内容旧，但默认误导风险不高。

## 4. 体量盘点
- `docs/changes/`：`116` 个文件
- `docs/selection/`：`81` 个文件
- `docs/strategy-rework/`：`39` 个文件
- `ops/`：`25` 个脚本

结论：
- 第一批降噪必须先盯这 4 个区域；
- 其中优先级顺序应为：
  1. `docs/changes/`
  2. `docs/strategy-rework/`
  3. `docs/selection/`
  4. `ops/`

## 5. 各区域风险分级

### 5.1 `docs/changes/`

#### P0
1. [STG-20260516-01-atomic-db-governance-compact-rollout-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md)
   - 原因：正文大量写“当前默认读取已切 compact / 当前 worktree / 当前验证状态”，很像现行操作手册，但缺少先看项目级 / 数据治理母卡的提示。
2. [REQ-20260429-05-market-heat-project-status-and-validation.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/REQ-20260429-05-market-heat-project-status-and-validation.md)
   - 原因：标题就是项目状态卡，极易被当成热点模块当前真相。
3. [REQ-20260513-01-hot-theme-forecasting-roadmap.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/REQ-20260513-01-hot-theme-forecasting-roadmap.md)
   - 原因：标题是 roadmap，但正文像正在实施中的现行方案，容易误判边界。
4. [REQ-20260425-02-selection-strategy-rework.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/REQ-20260425-02-selection-strategy-rework.md)
   - 原因：顶层直接写分支/worktree 和“重构”入口，容易盖过选股当前真相母卡。
5. [MOD-20260411-03-litong-review-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260411-03-litong-review-current-state.md)
   - 原因：名字带 `current-state`，但只是单票专项，容易被误当成全局现状。

#### P1
1. [MOD-20260415-01-atomic-release-readiness.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260415-01-atomic-release-readiness.md)
2. [MOD-20260415-02-local-research-station-architecture.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260415-02-local-research-station-architecture.md)
3. [STG-20260415-03-local-research-station-rollout-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/STG-20260415-03-local-research-station-rollout-plan.md)
4. [STG-20260411-02-market-data-processing-master.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/STG-20260411-02-market-data-processing-master.md)
5. [MOD-20260425-05-realtime-and-postclose-runtime-contract.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260425-05-realtime-and-postclose-runtime-contract.md)
6. [MOD-20260507-01-repo-consolidation-cloud-lite-freeze.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260507-01-repo-consolidation-cloud-lite-freeze.md)
7. [REL-20260507-v5.1.3-cloud-lite-production.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/REL-20260507-v5.1.3-cloud-lite-production.md)
8. [REL-20260512-v5.1.4-market-heat-mainline-dashboard.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/REL-20260512-v5.1.4-market-heat-mainline-dashboard.md)

#### P2
1. [MOD-20260404-01-selection-research-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260404-01-selection-research-current-state.md)
2. [MOD-20260417-01-local-research-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260417-01-local-research-current-state.md)
3. [MOD-20260411-14-market-data-governance-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260411-14-market-data-governance-current-state.md)
4. [MOD-20260424-01-stock-events-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260424-01-stock-events-current-state.md)
5. [MOD-20260324-01-retail-sentiment-v2-current-state.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/changes/MOD-20260324-01-retail-sentiment-v2-current-state.md)

判断：
- `docs/changes/` 第一批不该删文件，先该做的是：
  - 给 `P0` 卡统一补“先看母卡”的提示；
  - 把默认阅读路径从这些卡移开。

### 5.2 `docs/strategy-rework/`

#### P0
1. [README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/README.md)
2. [LONG_MEMORY.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/LONG_MEMORY.md)
3. [current-research-operating-summary.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/current-research-operating-summary.md)
4. [current-strategy-conclusion.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/current-strategy-conclusion.md)
5. [current-research-operating-summary.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/current-research-operating-summary.md)
6. [handoff-for-next-ai.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/handoff-for-next-ai.md)

其中第一批最危险的是：
- [handoff-for-next-ai.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/handoff-for-next-ai.md)
  - 原因：仍写旧 worktree、旧必读顺序、旧主链判断，与当前系统现状直接冲突。

#### P1
1. [strategies/S01-capital-trend-reversal/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/S01-capital-trend-reversal/README.md)
2. [archive-index.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/archive-index.md)
3. [strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-current-candidate/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-current-candidate)
4. [strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-quality-callback-long-2026q1q2/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-quality-callback-long-2026q1q2)
5. [strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-buy-point-v1/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/S02-capital-breakout-continuation/experiments/EXP-20260427-trend-continuation-buy-point-v1)
6. [evolution-lab/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/evolution-lab/README.md)
7. [strategies/aggressive-10cm/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/aggressive-10cm)
8. [experiments/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/experiments)

#### P2
1. [_archive/early-experiments/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/_archive/early-experiments)
2. [_archive/obsolete-root-docs/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/_archive/obsolete-root-docs)
3. [_archive/obsolete-strategy-dirs/](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/_archive/obsolete-strategy-dirs)
4. [notes/20260425-conversation-memory.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/notes/20260425-conversation-memory.md)
5. [strategies/S03-news-event-revaluation/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/strategy-rework/strategies/S03-news-event-revaluation/README.md)

判断：
- `strategy-rework` 当前最大风险不是“文件太多”，而是**入口竞争**和**未归档实验目录看起来像现行策略线**。
- `2026-05-19` 第三批已开始执行：`current-inventory.md` 已迁入 archive，并新增 `current-research-operating-summary.md` 作为顶层运营摘要入口。

### 5.3 `docs/selection/`

#### P0（应保留为当前入口）
1. [daily_candidate_source_contract.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/daily_candidate_source_contract.md)
2. [selection_research_master.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/selection_research_master.md)
3. [research_watchlist/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/research_watchlist/README.md)
4. [long_term_trends/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/long_term_trends/README.md)
5. [market_heat/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/market_heat/README.md)

#### P1（研究沉淀 / 案例库 / 清理记录）
1. [opportunity_discovery_model_final.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/opportunity_discovery_model_final.md)
2. [model_development_sop.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/model_development_sop.md)
3. [daily_selection_workbench_integration_plan_2026-05-16.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/daily_selection_workbench_integration_plan_2026-05-16.md)
4. [selection_research_archive_decision_summary.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/selection_research_archive_decision_summary.md)
8. [doublers/CASE_LIBRARY_USAGE.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/doublers/CASE_LIBRARY_USAGE.md)
9. [cycle_returns/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/cycle_returns/README.md)
10. [litong_similarity/README.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/litong_similarity/README.md)

以及以下目录整体都更像研究沉淀：
- `docs/selection/doublers/2026-ytd/top20/*`
- `docs/selection/market_heat/backtests/*`
- `docs/selection/long_term_trends/cases/*`
- `docs/selection/long_term_trends/*/tracking_report_*.md`

#### P2（已在第二批迁 archive 的对象）
1. [opportunity_discovery_model_final.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/opportunity_discovery_model_final.md)
2. [daily_selection_workbench_integration_plan_2026-05-16.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/daily_selection_workbench_integration_plan_2026-05-16.md)
3. [ARC-LEG-20260519-selection-research-cleanup-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/archive/ARC-LEG-20260519-selection-research-cleanup-plan.md)
4. [ARC-LEG-20260519-selection-cleanup-execution-todo.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/archive/ARC-LEG-20260519-selection-cleanup-execution-todo.md)
5. [ARC-LEG-20260519-selection-cleanup-deleted-manifest.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/archive/ARC-LEG-20260519-selection-cleanup-deleted-manifest.md)
6. [ARC-LEG-20260519-opportunity-discovery-research-archive-summary.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/archive/ARC-LEG-20260519-opportunity-discovery-research-archive-summary.md)

补充判断：
- [selection_research_master.md](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/docs/selection/selection_research_master.md) 不该删，但后续必须瘦身，否则它自己也会继续制造入口竞争。
- `2026-05-19` 第二批已执行：`cleanup plan / execution todo / deleted manifest / opportunity archive summary` 已迁入 `docs/archive/`，顶层改为只保留压缩摘要。

### 5.4 `ops/`

#### P0（正式入口，应保留）
1. [bootstrap_mac_full_processed_sync.sh](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/bootstrap_mac_full_processed_sync.sh)
2. [start_local_research_station.sh](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/start_local_research_station.sh)
3. [start_local_research_frontend.sh](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/start_local_research_frontend.sh)
4. [run_postclose_l2.sh](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/run_postclose_l2.sh)
5. [check_postclose_l2_status.sh](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/check_postclose_l2_status.sh)
6. [win_register_live_crawler_tasks.ps1](/Users/dong/Desktop/AIGC/market-live-terminal-governance-pass2/ops/win_register_live_crawler_tasks.ps1)

补充：
- repo 根目录的 `sync_to_windows.sh`、`deploy_to_cloud.sh`
- `scripts/check_baseline.sh`

也属于正式默认入口，但不在 `ops/` 目录内。

#### P1（历史脚本族 / 高噪音）
1. `start_*atomic*full_reverse*`
2. `check_*atomic*full_reverse*`
3. `win_run_atomic_backfill.bat`
4. `start_atomic_backfill_job.ps1`
5. `check_atomic_backfill_status*.{sh,py,ps1}`
6. `bench_*`
7. `measure_full_extract.ps1`
8. `run_short_atomic_bench.ps1`
9. `start_local_backend_with_atomic.sh`
10. `sync_windows_research_snapshot.sh`

这些对象的问题不是一定没用，而是：
- 文件名仍在强调 `full_reverse`
- 或者明显属于 bench / backfill / 验证阶段脚本族
- 很容易盖过正式入口

#### P2（第一批最适合先做入口收口和命名降噪）
1. `start_atomic_backfill_full_reverse.sh`
2. `start_atomic_backfill_full_reverse_direct.sh`
3. `start_atomic_backfill_mainboard_full_reverse.sh`
4. `check_atomic_backfill_full_reverse.sh`
5. `bench_7z_extract.ps1`
6. `bench_extract_backend.ps1`
7. `bench_extract_drive_compare.ps1`
8. `measure_full_extract.ps1`
9. `run_short_atomic_bench.ps1`
10. `start_local_backend_with_atomic.sh`

判断：
- `ops/` 第一批不该删脚本，先该做的是：
  - 通过文档和入口把正式脚本收束出来；
  - 把 full_reverse / bench / 历史 backfill 脚本族降为二线工具。

## 6. 第一批降噪目标（建议执行顺序）

### Batch 1A：先补入口提示
优先给以下对象补“先看当前母卡 / 当前入口”的提示：
1. `docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md`
2. `docs/changes/REQ-20260429-05-market-heat-project-status-and-validation.md`
3. `docs/changes/REQ-20260513-01-hot-theme-forecasting-roadmap.md`
4. `docs/changes/REQ-20260425-02-selection-strategy-rework.md`
5. `docs/changes/MOD-20260411-03-litong-review-current-state.md`
6. `docs/strategy-rework/handoff-for-next-ai.md`

### Batch 1B：再做顶层入口收缩
重点收缩以下目录的默认入口暴露：
1. `docs/strategy-rework/`
2. `docs/selection/`
3. `ops/`

方法：
1. 明确每个目录“唯一先读文件”
2. 其余文件降成专题资料 / 清理记录 / 归档摘要

### Batch 1C：最后再做归档/迁移判断
等入口清晰后，再决定：
1. 哪些文件只是改提示；
2. 哪些需要迁移到 `archive/`；
3. 哪些可以从顶层移到子目录；
4. 哪些后续可以删。

## 7. 当前建议
- 当前不直接进入文件删除。
- 当前先做“入口降级”和“风险提示补齐”。
- 但终局不应停在“加提示”这一层，而应继续进入：
  1. 历史材料真实归档；
  2. 阶段汇总文档补齐；
  3. 让少数汇总文档承接仍有价值的信息。
- 当前第一批最值得处理的是：
  1. `docs/changes` 的 P0 现状型过程卡
  2. `docs/strategy-rework/handoff-for-next-ai.md`
  3. `docs/selection` 顶层那些名字像 `final / plan / cleanup / execution` 的文件
  4. `ops` 里名称仍高频暴露 `full_reverse / bench` 的脚本族

后续第二批应直接进入：
1. 把已确认的历史材料迁移到 `docs/archive/` 或专题 archive 子目录；
2. 补 3~6 份阶段汇总文档，承接 v2/v3、v4、v5 以及选股/热点/数据治理几个大主题的历史价值。

## 8. 结果回填
- 已完成第一批风险分级；
- 已明确第一批不删文件，只做入口降噪；
- 已明确终局目标不是“保留旧文件加提示”，而是“先降噪，再归档，再阶段汇总”；
- 已完成 Batch 1A / 1B 的实际执行，当前已落地的入口降噪对象包括：
  1. `docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md`
  2. `docs/changes/REQ-20260429-05-market-heat-project-status-and-validation.md`
  3. `docs/changes/REQ-20260513-01-hot-theme-forecasting-roadmap.md`
  4. `docs/changes/REQ-20260425-02-selection-strategy-rework.md`
  5. `docs/changes/MOD-20260411-03-litong-review-current-state.md`
  6. `docs/strategy-rework/handoff-for-next-ai.md`
  7. `docs/strategy-rework/README.md`
  8. `docs/selection/selection_research_master.md`
  9. `docs/04_OPS_AND_DEV.md`
- 已完成第二批真实归档：
  1. `docs/selection/selection_research_cleanup_plan.md` -> `docs/archive/ARC-LEG-20260519-selection-research-cleanup-plan.md`
  2. `docs/selection/selection_cleanup_execution_todo_2026-05-16.md` -> `docs/archive/ARC-LEG-20260519-selection-cleanup-execution-todo.md`
  3. `docs/selection/selection_cleanup_deleted_manifest_2026-05-16.md` -> `docs/archive/ARC-LEG-20260519-selection-cleanup-deleted-manifest.md`
  4. `docs/selection/opportunity_discovery_archive_summary.md` -> `docs/archive/ARC-LEG-20260519-opportunity-discovery-research-archive-summary.md`
  5. 新增 `docs/selection/selection_research_archive_decision_summary.md` 承接压缩结论。
- 已开始第三批 `strategy-rework` 顶层收缩：
  1. `docs/strategy-rework/current-inventory.md` -> `docs/archive/ARC-LEG-20260519-strategy-research-current-inventory.md`
  2. 新增 `docs/strategy-rework/current-research-operating-summary.md` 作为当前阶段运营摘要
  3. `README / AI_QUICK_START / handoff` 已开始改向新的“三件套”入口
- 已补 `strategy-rework` 顶层追溯材料降级提示：
  1. `LONG_MEMORY.md`
  2. `docs/archive/ARC-LEG-20260519-strategy-research-project-status-20260427.md`
  3. `docs/archive/ARC-LEG-20260519-strategy-research-experiment-decision-log.md`
  4. `archive-index.md`
- 已补 `ops` 正式脚本白名单与入口约束：
  1. `docs/04_OPS_AND_DEV.md`
  2. `docs/ops/development-workflow.md`
- 已补 `ops` 历史脚本族边界总表：
  1. `docs/ops/atomic-script-families-boundary.md`
  2. `docs/changes/README.md`
  3. `docs/ops/postclose-l2-runbook.md`
  4. `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`
  5. `docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md`
- 当前阶段已经从“风险识别”推进到“入口已止血 + 顶层已减薄”；下一步不再新增大量提示文件，而是继续进入 `strategy-rework` 与 `ops` 的真实归档和阶段摘要压缩。
