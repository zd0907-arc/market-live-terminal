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

## T-006 Sandbox V2 股票池首构建（数据源短时断连）
- 状态：`DONE`（2026-03-11）
- 当前事实：
  - V2 代码与接口已就绪（`/api/sandbox/pool` + 1m 分库存储）。
  - 已新增 fallback（`stock_info_a_code_name/stock_zh_a_spot` + `stock_individual_info_em`）并在 Windows 成功落地。
- 结果回填：
  1. 股票池数量：`2788`（`as_of_date=2026-03-11`）；
  2. 冒烟回放：`run_id=1`，`symbol_count=20`，`total_rows=1317759`，`failed_count=0`；
  3. 当前样本占用：`data/sandbox` 约 `231.25MB`。
- 关联任务：`CHG-20260311-09`

## T-007 Sandbox V2 全量回放与云端可用打通
- 状态：`DONE`
- 当前事实：
  - Windows 已完成 `2025-01-01 ~ 2026-02-28` 全量 5m 回放，总控状态为 `done`；
  - 云端已完成 `data/sandbox/review_v2/` 首轮全量同步，`/api/sandbox/pool` 与 `/api/sandbox/review_data` 均可返回真实数据；
  - 已定位并修复“云端数据文件存在但接口空数组”的根因：容器内仍加载旧版 1m 查询模块，重建前后端容器后恢复正常。
- 解除条件：
  1. Windows 完成全量 `sandbox_review_v2_run_all_months.py`（一次启动、逐月逆序、按 `symbol+trade_date` 续跑），失败清单可追溯；
  2. `data/sandbox/review_v2/` 首轮同步到云端完成；
  3. 云端部署后 `/api/sandbox/pool` 与 `/api/sandbox/review_data` 可用，复盘页可正常查询。
- 结果回填：
  1. 股票池固定为 `2788`（`as_of_date=2026-03-11`），云端 symbol 分库首轮同步数为 `2789`（额外包含人工补跑样本 `sz000759`）；
  2. 云端目录 `data/sandbox/review_v2/` 占用约 `7.9G`；
  3. `sz000833/sz000759` 在 `2026-01-01 ~ 2026-02-28` 查询已可正常返回真实 5m 数据（接口层去重后为 `1666` 条）。
- 关联任务：`CHG-20260311-09`

## T-008 生产盯盘二态发布联动
- 状态：`ACTIVE`
- 当前事实：
  - 云端前后端已发布到 `v4.2.12`，其中 sandbox review 模块保持线上沙盒可用，周末“当日分时”回溯空白问题已修复。
  - Windows `live_crawler_win.py` 已同步到新的 `focus=5秒 / warm=30秒 / watchlist=15分钟` 逻辑，并于 `2026-03-14 14:05` 重启计划任务 `ZhangDataLiveCrawler` 生效。
  - 当前剩余的是前端体验层的人工确认：静默刷新时是否达到你主观上“丝滑、不闪”的标准。
- 解除条件：
  1. 生产实测确认实时页在周期刷新时无“先清空后回显”闪烁。
- 关联任务：`CHG-20260312-02`

## T-009 每日盘后 L2 日包融合方案
- 状态：`ACTIVE`
- 当前事实：
  - 已在 Windows 验证 `2026-03-11` 新日日包存在：`D:\\MarketData\\20260311\\20260311\\{symbol}`。
  - 抽样 `000833.SZ` 已确认三类文件齐全：`行情.csv`、`逐笔成交.csv`、`逐笔委托.csv`。
  - 样本成交文件包含 `叫买序号/叫卖序号`，且与委托文件 `交易所委托号` 可对齐，具备真实 L2 母单聚合前提。
  - 当前代码对该格式仍不兼容：`extract_date_from_path` 无法从该嵌套目录提取交易日，`sandbox_review_etl.py` 也未识别 `成交数量/叫买序号/叫卖序号` 这套中文列名。
  - `2026-03-14` 已冻结总方案：生产正式历史层固定为 `5m + daily`，并要求同源同时产出 L1/L2 双派生；复盘页未来并库到生产 L2 底座，sandbox 回归实验用途。
- 下一步：
  1. Phase 1（已完成）：`history_5m_l2/history_daily_l2/回补状态表` schema 与 `YYYYMM/YYYYMMDD` 目录 helper 已落代码并通过测试；
  2. Phase 2（已完成单日回补链路）：`l2_daily_backfill.py` 已支持把新日日包映射为 L1/L2 的 `5m + daily` 双派生并写入正式表；
  3. Phase 3（已完成后端查询切换）：`/api/history/trend` 与 `/api/history_analysis` 已优先读取 `history_5m_l2/history_daily_l2`，并补充 `source/is_finalized/fallback_used`；
  4. Phase 3.5（已完成）：历史日期回溯分时图已优先读取正式 `history_5m_l2`，`2026-03-11` 这类历史日期可直接在盯盘分时里看到 5m 的 L2 派生结果；
  5. 当前重点：继续打磨盯盘页的历史/回溯细节与来源显示正确性；
  6. Phase 4（已后置）：复盘页并库到生产 L2 底座，等盯盘页相关细节打磨稳定后再做，sandbox 继续保留实验用途。
- 关联任务：`CHG-20260314-02`
