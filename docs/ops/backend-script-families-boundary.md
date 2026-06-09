# backend/scripts 脚本族边界

> 这份文档只回答一个问题：`backend/scripts/` 里的脚本，哪些是当前正式主链配套，哪些只是研究、分析、补数、导出或历史兼容工具。
> 当前正式默认入口仍然先看 `docs/04_OPS_AND_DEV.md` 和 `docs/ops/atomic-script-families-boundary.md`。
> 各类 report / artifacts 的落点边界，补充看 `docs/ops/report-and-artifact-boundary.md`。

## 1. 一句话边界

当前日常操作不要直接从 `backend/scripts/` 里随手挑脚本执行。  
默认应该先走 `ops/` 白名单入口；只有 runbook 或专项任务明确要求时，才直接执行 `backend/scripts/`。

## 2. 当前盘点结论

`2026-06-06` 复核结果：

- `backend/scripts` 顶层共有 `202` 个文件；完成两批物理分层后，当前已降到约 `185`
- 其中按前缀粗分大致是：
  - `research_*`：`34`
  - `build_*`：`31`
  - `analyze_*`：`31`
  - `run_*`：`21`
  - `export_*`：`11`
  - `backfill_*`：`10`
  - 其他 `merge / l2 / sandbox / backtest / benchmark / audit / validate / dump ...`：其余

这说明它本质上已经不是“几个运行脚本”，而是“正式主链 + 研究实验室 + 历史补数工具箱”的混合目录。

当前又已完成第一批最小物理分层：

- `backend/scripts/maintenance/bench/`
  - `benchmark_atomic_detailed_profile.py`
  - `benchmark_atomic_process_shards.py`
  - `benchmark_atomic_stage_profile.py`
  - `benchmark_atomic_writer_modes.py`
- `backend/scripts/maintenance/audit/`
  - `audit_l2_order_event_codes.py`
- `backend/scripts/legacy/compat/`
  - `build_local_research_snapshot.py`
- `backend/scripts/legacy/history_merge/`
  - `merge_historical_db.py`
  - `merge_historical_db_local.py`

这批对象已经不再占用 `backend/scripts` 顶层默认认知。

`2026-06-06` 本轮又完成第二批低风险物理分层：

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

## 3. 当前正式主链配套对象

这些脚本当前仍属于正式链路的重要配套对象，但也不建议脱离 `ops/` 直接裸跑：

| 脚本 | 当前角色 |
|---|---|
| `backend/scripts/run_daily_new_framework.py` | 每日盘后正式主链总控程序入口 |
| `backend/scripts/live_crawler_win.py` | Windows 实时 crawler 主程序 |
| `backend/scripts/run_selection_research.py` | 选股研究链程序入口 |
| `backend/scripts/run_daily_model_signals.py` | 每日模型信号链程序入口 |
| `backend/scripts/build_model_feature_store.py` | 模型特征主构建脚本 |

边界：

1. 它们是正式链的一部分。
2. 但默认仍应通过 `ops/run_daily_new_framework.sh`、`ops/windows/win_register_live_crawler_tasks.ps1` 这类入口调度，而不是人工直接拼参数运行。

## 4. 研究 / 分析脚本

以下家族默认按研究脚本理解，不是正式日常入口：

- `research_*`
- `analyze_*`
- `backtest_*`
- `benchmark_*`
- `compare_*`
- `explore_*`
- `quick_*`
- `train_*`

语义：

1. 用于策略研究、样本分析、专题验证、性能测试、训练实验。
2. 可以保留，但不应混入“今天正式该跑哪条链”的默认认知。

## 5. 数据修复 / 导出 / 兼容工具

以下家族默认按二线工具理解：

- `backfill_*`
- `merge_*`
- `export_*`
- `dump_*`
- `audit_*`
- `validate_*`
- `inspect_*`
- `append_*`
- `promote_*`
- `finalize_*`
- `refresh_*`
- `cleanup_*`
- `fetch_*`
- `crawl_*`
- `etl_*`
- `init_*`
- `sync_*`
- `postclose_*`
- `l2_*`

语义：

1. 服务补历史、修复、导出、对账、排障、兼容链。
2. 不是默认日常入口。
3. 只有在 change card、runbook 或专项治理明确要求时才应使用。

其中当前已先物理下沉的典型对象包括：

- `backend/scripts/maintenance/bench/*`
- `backend/scripts/maintenance/audit/audit_l2_order_event_codes.py`
- `backend/scripts/maintenance/l2_repair/*`
- `backend/scripts/legacy/compat/build_local_research_snapshot.py`
- `backend/scripts/legacy/history_repair/*`
- `backend/scripts/legacy/history_merge/merge_historical_db.py`
- `backend/scripts/legacy/history_merge/merge_historical_db_local.py`

## 6. `build_*` 家族的特殊边界

`build_*` 有 `31` 个，是最容易混淆的一组。

它们要分两类理解：

1. 少数是正式主链的构建步骤，例如模型特征、热点页面、快照等正式产物构建。
2. 大多数其实是专题页、研究页面、一次性报表或实验产物生成器。

因此当前规则是：

- 没有进入 runbook 白名单的 `build_*`，默认按研究或专题构建工具处理。
- 如果 `build_*` 的主要结果是 `md/json/csv/html`，默认再按 `report / artifact builder` 处理，而不是正式运行脚本处理。

## 7. 当前推荐规则

以后默认按这 4 条执行：

1. 日常正式运行只认 `ops/` 白名单，不从 `backend/scripts/` 随手挑。
2. 新增脚本如果没有被 runbook、`04_OPS_AND_DEV` 或白名单文档接纳，就默认按研究脚本处理。
3. 研究 / 导出 / 修复脚本可以继续放在 `backend/scripts/`，但后续应逐步分层。
4. 后续如果要做物理目录重构，优先考虑拆成：
   - `backend/scripts/runtime/`
   - `backend/scripts/research/`
   - `backend/scripts/maintenance/`
   - `backend/scripts/legacy/`

## 8. 这份文档的直接用途

这份文档先冻结“认知边界”，不是立刻搬文件。

后续目录治理时，默认先按这份边界做两件事：

1. 先分类 inventory；
2. 再决定哪些脚本要物理迁移，哪些只需文档降噪。
