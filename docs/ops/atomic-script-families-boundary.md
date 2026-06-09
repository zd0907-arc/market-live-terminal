# Atomic 历史脚本族边界

> 这份文档只回答一个问题：`ops/` 里哪些脚本是当前正式默认入口，哪些只是历史治理、专项补数、排查验证或性能 bench 工具。
> 当前正式入口先看：`docs/04_OPS_AND_DEV.md`
> 当前正式盘后日跑先看：`docs/ops/postclose-l2-runbook.md`

## 1. 一句话边界

当前日常正式操作，只允许从白名单脚本进入；`full_reverse / atomic backfill / bench / snapshot` 相关脚本默认都不是正式日常入口。

## 2. 当前正式默认入口

以下脚本属于当前正式默认入口：

| 用途 | 脚本 |
|---|---|
| Mac 首次全量同步 | `ops/bootstrap_mac_full_processed_sync.sh` |
| Mac 本地后端启动 | `ops/start_local_research_station.sh` |
| Mac 本地前端启动 | `ops/start_local_research_frontend.sh` |
| 每日盘后正式主链 | `ops/run_daily_new_framework.sh` |
| 盘后状态查看 | `ops/legacy/check_postclose_l2_status.sh` |
| Windows 实时 crawler 任务注册 | `ops/windows/win_register_live_crawler_tasks.ps1` |

补充：
- repo 根目录的 `sync_to_windows.sh`、`deploy_to_cloud.sh`
- `scripts/check_baseline.sh`

也属于正式默认入口，但不在 `ops/` 目录内。

## 3. 历史脚本族定义

### 3.1 `full_reverse`

典型对象：
- `ops/legacy/start_atomic_backfill_full_reverse.sh`
- `ops/legacy/start_atomic_backfill_full_reverse_direct.sh`
- `ops/legacy/start_atomic_backfill_mainboard_full_reverse.sh`
- `ops/legacy/check_atomic_backfill_full_reverse.sh`

语义：
- 对应旧 atomic 主库命名和治理迁移阶段的历史操作。
- 主要用于旧阶段补数、兼容验证、迁移追溯。

当前边界：
- 不等于当前正式默认数据库入口。
- 不应出现在当前 runbook 的日常操作步骤里。

### 3.2 `atomic backfill`

典型对象：
- `ops/windows/start_atomic_backfill_job.ps1`
- `ops/legacy/check_atomic_backfill_status.sh`
- `ops/legacy/check_atomic_backfill_status.py`
- `ops/legacy/check_atomic_backfill_status_brief.sh`
- `ops/windows/get_atomic_backfill_status.ps1`
- `ops/windows/win_run_atomic_backfill.bat`
- `ops/windows/win_prepare_l2_day.bat`
- `ops/windows/win_run_l2_shard.bat`

语义：
- 历史补数、专项治理、大窗口重跑、Windows 分片执行。
- 主要服务补历史窗口、核查覆盖、专项训练准备，不是当前每天盘后的标准日跑。

当前边界：
- 默认按二线工具处理。
- 只有在专项补数、数据治理、覆盖审计任务里才应显式调用。

### 3.3 `bench`

典型对象：
- `ops/bench/bench_7z_extract.ps1`
- `ops/bench/bench_extract_backend.ps1`
- `ops/bench/bench_extract_drive_compare.ps1`
- `ops/bench/measure_full_extract.ps1`
- `ops/bench/run_short_atomic_bench.ps1`

语义：
- 性能测试、预演、磁盘/解压对比、局部压测。

当前边界：
- 不能当正式数据源构建步骤。
- 不能当正式运行步骤。

### 3.4 `snapshot / atomic 兼容启动`

典型对象：
- `ops/legacy/sync_windows_research_snapshot.sh`
- `backend/scripts/legacy/compat/build_local_research_snapshot.py`
- `ops/legacy/start_local_backend_with_atomic.sh`

语义：
- 过渡验证、旧链路兼容、本地排查。

当前边界：
- 不是当前正式默认入口。
- 只有在明确说明“本轮任务是旧快照验证或兼容排查”时才应使用。
- 其中 `backend/scripts/legacy/compat/build_local_research_snapshot.py` 默认也应优先跟随当前 `compact_current` atomic 解析链，而不是再把旧 `full_reverse` 当正式底座理解。

### 3.5 `run_postclose_l2`

典型对象：
- `ops/legacy/run_postclose_l2.sh`
- `ops/legacy/check_postclose_l2_status.sh`

语义：
- 旧盘后 L2 / cloud 同步兼容链路。

当前边界：
- 不再作为当前正式日常主链。
- 只有在兼容旧链路、追溯历史或处理特殊回退任务时才应使用。

## 4. 允许使用的例外场景

只有以下场景可以跳出白名单：

1. 当前任务本身就是历史补数、覆盖审计、专项治理或 compact / atomic 迁移验证。
2. 对应 change card 或 runbook 已明确指定具体脚本。
3. 需要复现旧阶段结论，且正式入口无法提供同等上下文。

如果不满足这三条，就回到白名单脚本。

## 5. 追溯入口

需要追溯历史治理时，再看：

- `docs/archive/changes/MOD-20260411-14-market-data-governance-current-state.md`
- `docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md`
- `docs/changes/MOD-20260519-02-process-material-risk-grading-batch1.md`
