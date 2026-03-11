# 07_PENDING_TODO（阻塞与待办）

> 只记录阻塞项、待办项与状态推进；不写长方案。

## T-001 Windows SSH 免密
- 状态：`DONE`（2026-03-08）
- 结果：`authorized_keys` 已配置，`sync_to_windows.sh` 可执行。
- 关联任务：`CHG-20260308-02`

## T-002 Windows ETL 产物回传与云端 merge
- 状态：`BLOCKED`
- 当前事实：
  - Windows `202602` ETL 已完成（15/15 DONE, 0 FAILED）。
  - 源文件：`D:\market-live-terminal\market_data_history_202602_fix.db`（约 95MB）。
  - 阻塞原因：Tailscale/SSH 连接抖动导致大文件回传中断。
- 下一步：
  1. 回传完整文件到 Mac（需校验大小一致）；
  2. 云端执行 `merge_historical_db.py`；
  3. 复核 `sz000833` 在 `2026-02-13` 的 30m 数据。
- 关联任务：`CHG-20260308-01`, `CHG-20260309-03`

## T-003 Windows 架构稳定性评估
- 状态：`TODO`
- 目标：评估“active但不通、DERP长传中断、睡眠后不可达”对生产流程的影响，并给出改造路线。
- 交付：`docs/10_WINDOWS_STABILITY_REVIEW_YYYY-MM-DD.md`（问题、根因、方案、优先级）。
- 关联任务：`CHG-20260309-03`

## T-004 协作约定：Windows链路改动前置检查
- 状态：`ACTIVE`
- 规则：凡涉及 `live_crawler_win.py`、`start_live_crawler.bat`、Windows ingest 调度改动，必须先检查 Windows 同步状态并记录在 handoff。

## T-005 Sandbox 复盘数据准备就绪（评审阻塞）
- 状态：`BLOCKED`
- 当前事实：
  - 复盘模块代码与文档已完成分支级收口，当前以 Draft PR 方式供评审与联调。
  - 真实效果验收仍依赖稳定的 sandbox 数据集（`sh603629` 2026-01~02）持续可复现。
- 解除条件：
  1. Windows 源目录 `D:\\MarketData` 可稳定重跑并产出一致的 `sandbox_review.db`；
  2. 本地 `/api/sandbox/review_data` 连续返回真实区间数据（无 404 / 无预置回退）；
  3. 复盘页主区与累计区在 1-2 月窗口通过一次回归冒烟。
- 关联任务：`CHG-20260311-08`
