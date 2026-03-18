# MOD-20260318-02-market-session-states-and-intraday-defaults

## 1. 基本信息
- 标题：当日分时市场状态机收口与盘后查看新股票默认逻辑修复
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260318-02`
- 关联 CAP：`CAP-MKT-TIME`, `CAP-REALTIME-FLOW`
- 关联 STG：无

## 2. 背景与目标
- 用户在 `2026-03-18 22:00`（周三夜间复盘）打开“当日分时”查看新股票 `网宿科技（sz300017）` 时，页面仍显示“实时交易中”，且一直没有正确切换到盘后复盘语义。
- 该问题暴露出两层缺口：
  1. 前端状态展示依赖数据返回，导致“状态检测中 / 状态未知”体验；
  2. 后端只粗略区分“今天是不是交易日”，没有形成可直接驱动 UI 的明确市场状态机。
- 目标：把市场状态、默认展示日期、是否应走实时路径、盘后查看新股票的同日补抓逻辑统一收口。

## 3. 方案与边界
- 做什么：
  - 后端新增统一 `market_context`，明确区分 `盘前 / 盘中 / 午间休市 / 盘后 / 休盘日`；
  - `/api/realtime/dashboard` 返回显式状态字段：`market_status / market_status_label / default_display_scope / view_mode`；
  - 盘后查看“今天”的新股票时，若本地无当日分时，允许按需补抓当天 full-day ticks 再聚合；
  - 前端状态 badge 先本地判定，再由后端权威状态覆盖，图表区域独立显示“正在获取分时数据...”。
- 不做什么：
  - 本卡不改历史多维业务口径；
  - 不改数据库 schema；
  - 不把“盘后查看新股票”的按需补抓扩展成新的后台常驻采集策略。

## 4. 执行步骤（按顺序）
1. 把 `MarketClock` 从“是否交易时间”升级为“市场状态机 + 默认展示语义”。
2. 修改 `/api/realtime/dashboard`：严格按 `market_context` 决定默认日期与实时/回放路径。
3. 为“今天但本地无该股票数据”的场景增加按需补抓与本地 1m 聚合。
4. 前端改为先显示临时状态，再单独加载图表，避免“状态检测中 / 状态未知”。
5. 补测试并跑 baseline。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-18 22:00`（北京时间，交易日盘后），When 打开 `sz300017` 当日分时，Then 顶部状态应显示“盘后复盘”，而不是“实时交易中”。
- Given `2026-03-18 22:00` 页面刚切到新股票、后端数据尚未返回，When 前端开始请求，Then 顶部状态应已先显示市场状态，图表区显示“正在获取分时数据...”。
- Given `2026-03-18 22:00` 该股票本地尚无当天 ticks，When 请求 `/api/realtime/dashboard?symbol=sz300017`，Then 后端应允许按需补抓当天数据并返回可展示结果；若外部源不可用，则至少返回明确的盘后语义而不是“实时交易中”。

## 6. 风险与回滚
- 风险：
  - 盘后按需补抓依赖外部源可用性；若外部源超时，页面仍可能暂无当日数据，但状态语义应保持正确。
  - 前端临时状态与后端权威状态存在一个很短的覆盖窗口；但两者现在语义保持一致，不再出现“状态未知”。
- 回滚：
  1. 回退 `MarketClock.get_market_context()` 与 `/api/realtime/dashboard` 新字段；
  2. 恢复前端原“等数据后再判断状态”的逻辑；
  3. 取消盘后同日按需补抓逻辑。

## 7. 结果回填
- 实际改动：
  - `backend/app/core/http_client.py`：新增统一 `market_context`；
  - `backend/app/routers/market.py`：按状态机决定默认展示日期、实时路径与盘后同日按需补抓；
  - `src/components/dashboard/RealtimeView.tsx`：状态先判定、图表独立加载态、显示后端权威状态；
  - `src/types.ts`：补市场状态相关字段；
  - `backend/tests/test_market_clock.py`、`backend/tests/test_realtime_dashboard_router.py`：补状态机与盘后默认语义测试。
- 验证结果：
  - `python3 -m pytest -q backend/tests/test_market_clock.py backend/tests/test_realtime_dashboard_router.py` 通过（`11 passed`）；
  - `bash scripts/check_baseline.sh` 通过；
  - 本地前端构建通过，后端测试总数更新为 `66 passed`。
- 遗留问题：
  - 盘后同日按需补抓目前属于“请求触发式”补抓；若后续需要更强体验，可考虑为热门切换股票增加短时缓存或进度提示。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
