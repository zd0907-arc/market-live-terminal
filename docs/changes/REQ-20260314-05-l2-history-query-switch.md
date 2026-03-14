# REQ-20260314-05-l2-history-query-switch

## 1. 基本信息
- 标题：Phase 3｜生产历史查询切换到 L2 正式底座
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260314-05`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-REALTIME-FLOW`
- 关联 STG：`STG-20260314-01`

## 2. 背景与目标
- 数据底座准备完成后，需要把生产“历史查询”切换到正式 L2 历史层，同时保持当天实时体验不受影响。

## 3. 方案与边界
- 做什么：
  - 盯盘页历史模式改查 `history_5m_l2`；
  - 日K资金博弈分析改为“当天腾讯、历史 L2 正式值”；
  - `15m/30m/1h` 查询统一由 `5m` 聚合；
  - 响应中显式携带 `source/is_finalized/fallback_used`。
  - 历史日期分时回溯优先读取正式 L2 `5m`。
- 不做什么：
  - 不在本阶段落前端复杂的 L1/L2 对比交互；
  - 不在本阶段处理复盘页并库。

## 4. 执行步骤
1. 后端接口增加正式历史源与 fallback 标记。
2. 盯盘页历史查询切到 `history_5m_l2`。
3. 日K资金博弈历史查询切到 `history_daily_l2`。
4. 保持当天实时路径不变。

## 5. 验收标准（Given/When/Then）
- Given `2026-03-14 18:40`，When 次日从盯盘页查看前一交易日，Then 查询来自 `history_5m_l2`。
- Given `2026-03-14 18:45`，When 在日K模块查看历史日期，Then 返回正式 L2 历史口径而非腾讯当天实时拼接。
- Given `2026-03-14 18:50`，When 历史 L2 缺数时触发 fallback，Then 响应中必须显式带 `fallback_used=true`。

## 6. 风险与回滚
- 风险：若查询切换时不加显式 source/fallback 标记，后续会很难判断页面展示的是正式值还是兜底值。
- 回滚：可按接口开关暂时回退旧查询源，但契约必须保留标记字段。

## 7. 结果回填
- 实际改动：
  - `backend/app/db/l2_history_db.py` 新增正式 L2 历史查询与 `5m→15m/30m/1h/1d` 聚合 helper；
  - `backend/app/routers/analysis.py` 已切换：
    - `/api/history/trend` 优先查询 `history_5m_l2`，默认 `30m`，支持 `granularity=5m|15m|30m|1h|1d`；
    - `/api/history_analysis` 历史日期优先查询 `history_daily_l2`；
    - 两接口均补充 `source/is_finalized/fallback_used`；
    - 当天继续允许实时 ticks 覆盖未结算值。
  - `backend/app/routers/market.py` + `backend/app/services/analysis.py` 已补历史分时回溯链路：
    - 优先 `history_1m`
    - 若缺失则读正式 `history_5m_l2`
    - 再缺失才回退 `trade_ticks`
  - `src/services/stockService.ts` 已补 `history/trend` 的 `granularity` 参数透传。
  - `src/components/dashboard/RealtimeView.tsx`、`HistoryView.tsx` 已改为显示接口真实 source，而非写死的 `Local DB`。
- 验证结果：
  - 当前相关回归测试通过，覆盖：
    - 历史 30m 查询切换；
    - 历史日线分析切换；
    - 历史分时回溯切换；
    - 当天实时覆盖不变；
  - 本地手动 smoke：
    - `2026-03-11 / sz000833`：历史 30m 与历史分时均返回 `source=l2_history`；
    - `2026-03-11 / sh600519`：历史 30m 与历史分时均返回 `source=l2_history`。
- 遗留问题：
  - 历史页主数据源选择器本身仍保留旧的 `Sina/Local` 交互语义，后续如果要彻底收口成“正式历史/实验源”，还需进一步调整交互；
  - `granularity=15m/1h` 已有后端能力，前端选择器后续再细化。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
