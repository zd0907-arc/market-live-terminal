# MOD-20260314-01-weekend-intraday-backfill-fix

## 1. 基本信息
- 标题：修复非交易日“当日分时”回溯为空
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260314-01`
- 关联 CAP：`CAP-MKT-TIME`

## 2. 背景与目标
- 用户反馈：`2026-03-14`（周六）打开生产“当日分时”时，页面应进入回溯模式并展示 `2026-03-13`（周五）分时，但实际为空。
- 目标：在不改变现有 UI 行为的前提下，确保周末/节假日/盘前回溯时始终走历史 1m 回放数据，而不是误走“实时 ticks 聚合”。

## 3. 根因
- `/api/realtime/dashboard` 之前以 `query_date == MarketClock.get_display_date()` 作为“是否走实时路径”的判断。
- 在周六场景下：
  - `display_date = 2026-03-13`
  - `query_date` 缺省也等于 `2026-03-13`
  - 结果被误判成“实时当天”，从 `trade_ticks` 走 `calculate_realtime_aggregation`
- 但周末并不在实时采集窗口，应该读取 `history_1m` 的上一个交易日静态回放，因此导致图表为空。

## 4. 改动内容
1. `backend/app/routers/market.py`
   - 新增“自然日 today”与“display_date”分离判断。
   - 仅当 `query_date == natural_today` 且 `natural_today` 为交易日时，才走实时 ticks 聚合。
   - 周末/节假日/盘前回溯到上一交易日时，优先走 `get_history_1m_dashboard()`。
   - 若该日 `history_1m` 尚未补齐，但 `trade_ticks` 已存在，则自动回退到“按该日 ticks 现场聚合”，避免回溯页空白。
2. `backend/tests/test_realtime_dashboard_router.py`
   - 新增周末回溯场景测试；
  - 新增正常交易日当天仍走实时路径测试；
  - 新增“周末回溯日无 history_1m 时，自动回退到该日 ticks 聚合”的兜底测试。

## 5. 验证记录
- `2026-03-14 13:15`：`PYTHONPATH=/Users/dong/Desktop/AIGC/market-live-terminal ./.venv/bin/pytest -q backend/tests/test_market_clock.py backend/tests/test_realtime_dashboard_router.py backend/tests/test_monitor_heartbeat.py backend/tests/test_sandbox_review_v2.py` 通过（15/15）。
- `2026-03-14 13:16`：`npm run build` 通过。
- `2026-03-14 13:46`（云端）：`/api/health` 返回 `{"status":"ok"}`。
- `2026-03-14 13:47`（云端）：周末回溯冒烟通过：`/api/realtime/dashboard?symbol=sz000833` 返回 `code=200`、`display_date=2026-03-13`、`chart_data=241`、`latest_ticks=50`。

## 6. 风险与回滚
- 风险：
  - 若用户手动显式传入“自然日今天但该日不是交易日”的日期，接口将走历史回放并在无数据时返回 404，这符合当前契约。
- 回滚：
  1. 回退 `backend/app/routers/market.py` 的自然日判断；
  2. 恢复原逻辑 `query_date == display_date` 即走实时路径；
  3. 同时删除新增测试文件。

## 7. 结果回填
- 预期结果：周末/节假日打开“当日分时”时，页面显示回溯模式标签，并正常展示上一交易日分时；若该交易日尚未预聚合到 `history_1m`，也不会再空白。
- 联动说明：该改动不影响 sandbox review 模块；仅修复生产分时主链路的日期判定。
- 发布结果：已随 `v4.2.12` 发到云端生产；线上 sandbox review 入口与现有功能保持不变。
