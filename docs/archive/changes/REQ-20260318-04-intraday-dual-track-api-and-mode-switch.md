# REQ-20260318-04-intraday-dual-track-api-and-mode-switch

## 1. 基本信息
- 标题：Phase 2｜统一双轨接口与盘中/盘后/历史模式切换
- 状态：ACTIVE
- 负责人：Codex / 前后端 AI
- 关联 Task ID：`CHG-20260319-01`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-L2-HISTORY-FOUNDATION`
- 关联 STG：`STG-20260318-03`

## 2. 背景与目标
- 当前当日分时页的数据来源分裂：主力动态走 `/api/realtime/dashboard`，资金博弈走 `/api/sentiment*`；
- 盘中、盘后、历史三种查看语义尚未形成统一模式字段；
- 本阶段目标是提供一个页面级统一接口，让 `主力动态 + 资金博弈分析` 共享同一组 5m bars 与同一个模式判定。

## 3. 方案与边界
- 做什么：
  - 冻结统一正式接口：`GET /api/realtime/intraday_fusion`；
  - 冻结模式枚举与自动切换规则；
  - 明确旧 `/api/sentiment*` 从本页正式主路径退场。
- 不做什么：
  - 本阶段不实现前端双轨 UI；
  - 本阶段不增加手动模式开关；
  - 本阶段不把复盘页一起切到该接口。

## 4. 接口契约（冻结）
### 4.1 请求
- 路径：`GET /api/realtime/intraday_fusion?symbol=sz000833&date=2026-03-18`
- 参数：
  - `symbol`：必填
  - `date`：选填；为空时仍由后端按 `MarketClock` 决定展示日
  - `include_today_preview`：选填，默认 `true`

### 4.2 响应顶层字段
- `symbol`
- `trade_date`
- `mode`：`intraday_l1_only | postclose_dual_track | historical_dual_track`
- `mode_label`
- `bucket_granularity`：固定 `5m`
- `is_l2_finalized`
- `source`
- `fallback_used`
- `bars[]`

### 4.3 `bars[]` 统一字段
- 基础量价：`datetime/open/high/low/close/total_amount/total_volume`
- L1：`l1_main_buy/l1_main_sell/l1_super_buy/l1_super_sell/l1_net_inflow`
- L2：`l2_main_buy/l2_main_sell/l2_super_buy/l2_super_sell/l2_net_inflow`
- 订单事件：`add_buy_amount/add_sell_amount/cancel_buy_amount/cancel_sell_amount`
- 资金博弈：`l2_cvd_delta/l2_oib_delta`
- 元数据：`is_finalized/preview_level/source/fallback_used`

### 4.4 模式切换规则（必须写死）
1. `intraday_l1_only`
   - 条件：`query_date = 当天交易日` 且 `finalized L2 尚未到位`
   - 行为：只返回 L1 可用字段；L2 字段允许 `null`；前端不触发撤单/隐藏单信号。
2. `postclose_dual_track`
   - 条件：`query_date = 当天交易日` 且 `finalized L2 已到位`
   - 行为：返回同一交易日的 L1/L2 完整 5m bars；页面自动双轨。
3. `historical_dual_track`
   - 条件：`query_date < 当天展示日` 或手动指定历史日期
   - 行为：优先读取 finalized 历史 L1/L2，同页双轨展示。

## 5. 数据源优先级（冻结）
- 盘中当天：`realtime_5m_preview` / 实时 L1 聚合
- 当天盘后已 finalized：`history_5m_l2`（同日 finalized）
- 历史日期：`history_5m_l2`
- 旧 `/api/sentiment*`：仅保留兼容/过渡，不得再被当日分时页正式主链路依赖

## 6. 执行步骤（按顺序）
1. 新增统一接口与模式判定层；
2. 让主力动态与资金博弈都从同一 `bars[]` 取数；
3. 把盘中/盘后/历史切换收口到后端，不允许前端再靠本地时间猜模式；
4. 旧资金博弈调用链改为兼容态/待下线态，并在文档中明确降级地位。

## 7. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-18 10:00`，When 请求 `/api/realtime/intraday_fusion?symbol=sz000833`，Then `mode=intraday_l1_only` 且 `bars[*].cancel_buy_amount`、`bars[*].cancel_sell_amount` 为 `null` 或缺省不可用值，不得伪造 0 信号。
- Given `2026-03-18 22:00`，When 同样请求当天日期且 finalized L2 已到位，Then `mode=postclose_dual_track`，`bars[*]` 同时包含 L1/L2 与 `add/cancel` 字段。
- Given `2026-03-17 14:00`，When 请求历史日期，Then `mode=historical_dual_track`，且 `source` 明确指向 finalized 历史表。
- Given 前端仍误调用旧 `/api/sentiment/history`，When 做联调审计，Then 该路径只能被标记为 legacy，不得再作为当前页主路径验收通过。

## 8. 风险与回滚
- 风险：
  1. 若模式判定仍分散在前后端，极易出现同一日期一半单轨一半双轨；
  2. 若接口不统一，主力动态和资金博弈会继续各算各的时间轴与来源标签；
  3. 若盘后自动切换没有 `is_l2_finalized` 明示，前端无法做稳定空态与标题态。
- 回滚：
  - 文档阶段不涉及代码；
  - 实施阶段若新接口不稳定，可短期保留旧接口兜底，但不得回滚模式定义与字段契约。

## 9. 结果回填
- 实际改动：当前仅冻结接口路径、模式枚举与来源优先级。
- 验证结果：盘中/盘后/历史三态与统一 `bars[]` 契约已写死。
- 遗留问题：接口是否同时返回页面标题文案、旧接口下线窗口、与 `/api/realtime/dashboard` 的过渡关系。

## 10. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
