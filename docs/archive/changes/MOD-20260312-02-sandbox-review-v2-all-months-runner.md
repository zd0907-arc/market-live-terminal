# MOD-20260312-02-sandbox-review-v2-all-months-runner

## 1. 基本信息
- 标题：Sandbox Review V2 全月份自动串行总控任务
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260312-04`
- 关联 CAP：`CAP-SANDBOX-REVIEW`, `CAP-WIN-PIPELINE`

## 2. 背景与目标
- 当前 V2 全量回放数据范围为 `2025-01-01 ~ 2026-02-28`，总股票池约 2788 只。
- 之前按“单月手工拉起”会造成强人工依赖：2月跑完还需要人工再起 1 月、12 月……不适合长任务。
- 目标是提供一个“一次启动、逐月逆序、自动续跑、完成即停机”的总控任务，让 Windows 节点可以无人值守地把整段数据跑完，但不自动同步云端、不自动发布版本。

## 3. 方案与边界
- 做什么：
  - 新增总控脚本 `backend/scripts/sandbox_review_v2_run_all_months.py`。
  - 按月份逆序自动调用 `sandbox_review_v2_backfill.py`，默认覆盖 `2026-02 -> 2025-01`。
  - 每月结束后读取 `meta.db::sandbox_backfill_month_runs` 最新状态，只有 `done` 才继续下个月；`partial_done` 默认停机等待人工，也可通过参数允许继续。
  - 持续写出状态文件 `data/sandbox/review_v2/logs/run_all_months_latest.json` 供外部查看当前月、已完成月份、失败月份。
- 不做什么：
  - 不自动同步云端；
  - 不自动发布生产；
  - 不并发启动多个“整段总控”实例；
  - 不中断当前已在运行的单月任务。

## 4. 执行步骤（按顺序）
1. 在 `sandbox_review_v2_db.py` 增加查询最新月份 run 结果的 helper，供总控脚本读取月状态。
2. 实现 `sandbox_review_v2_run_all_months.py`：月列表生成、单月子进程拉起、状态文件写入、失败停机策略。
3. 增补单元测试与文档，明确“完成后仅停在 done 态，等待页面校验后再做数据同步/版本发布”。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-12 23:30`，When 运行 `sandbox_review_v2_run_all_months.py D:\MarketData --resume`，Then 脚本会按 `2026-02 -> 2025-01` 逆序逐月调用单月 backfill，而不是只跑一个月份后退出。
- Given `2026-03-12 23:31`，When 某个月份最新 run 状态为 `done`，Then 总控会自动进入下一个月份，无需人工再次启动。
- Given `2026-03-12 23:32`，When 某个月份状态为 `partial_done` 或子进程返回非零，Then 总控默认停机并把失败信息写入 `run_all_months_latest.json`，避免静默跳过异常。
- Given `2026-03-12 23:33`，When 全部月份完成，Then 状态文件为 `done`，且不自动执行云端同步与生产发布。

## 6. 风险与回滚
- 风险：
  - 若同时运行“单月任务”和“全月份总控”，可能对同一月份产生资源竞争；因此切换前应确认旧任务结束或手动停掉旧任务。
  - 当前总控默认对 `partial_done` 采取保守停机；若要无脑继续，需要显式打开 `--continue-on-partial`。
- 回滚：
  1. 停止并删除新的总控计划任务；
  2. 回到旧模式，继续使用 `sandbox_review_v2_backfill.py --months YYYY-MM` 单月拉起；
  3. 保留 `meta.db` 历史 run 记录不删除，便于恢复。

## 7. 结果回填
- 实际改动：
  - `backend/scripts/sandbox_review_v2_run_all_months.py`：新增总控脚本。
  - `backend/app/db/sandbox_review_v2_db.py`：新增 `get_latest_month_run(month)`。
  - `backend/tests/test_sandbox_review_v2.py`：新增“最新月份 run 查询”和“月份范围 helper”测试。
  - 文档回填：`docs/02_BUSINESS_DOMAIN.md`, `docs/03_DATA_CONTRACTS.md`, `docs/04_OPS_AND_DEV.md`, `docs/07_PENDING_TODO.md`, `docs/AI_HANDOFF_LOG.md`。
- 验证结果：
  - `2026-03-12 23:22`：`python3 -m pytest backend/tests/test_sandbox_review_v2.py -q` 通过（7/7）。
  - `2026-03-12 23:22`：对 `sandbox_review_v2_run_all_months.py` / `sandbox_review_v2_db.py` / `test_sandbox_review_v2.py` 执行 `ast.parse` 语法检查通过。
  - `2026-03-13 00:03`（Windows）：已停掉并禁用 `SandboxBackfillMonth202602`，创建并启动 `SandboxBackfillAllMonths`。
  - `2026-03-13 00:05`（Windows）：`run_all_months_latest.json` 显示 `status=running,current_month=2026-02`，`run_all_months.out.log` 持续增长，说明总控已成功接管。
- 遗留问题：
  - `2026-03-13 00:03` 已在 Windows 完成从 `SandboxBackfillMonth202602` 到 `SandboxBackfillAllMonths` 的切换；当前总控仍在继续处理 `2026-02`，待全部月份完成后仍需做云端同步与页面联调。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
