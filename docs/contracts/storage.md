# 数据表与存储边界

## 1. 当前正式数据载体
| 载体 | 用途 |
|---|---|
| `data/market_data.db` | 主业务消费库 |
| `data/atomic_facts/*` | 原子事实层与治理结果 |
| `data/selection/selection_research.db` | 选股研究独立库 |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离域 |

## 2. 主要表组
### A. 市场与历史
- `trade_ticks`
- `local_history`
- `history_30m`
- `history_5m_l2`
- `history_daily_l2`
- `realtime_5m_preview`
- `realtime_daily_preview`
- `stock_universe_meta`

### B. 散户情绪
- `sentiment_snapshots`
- `sentiment_events`
- `sentiment_*` 汇总表

### C. 官方事件层
- `stock_events`
- `stock_event_entities`
- `stock_symbol_aliases`
- `stock_event_ingest_runs`
- `stock_event_daily_rollup`

### D. 选股研究
- `selection_candidates`
- `selection_profiles`
- `selection_backtests`
- 其他研究派生结果（统一在 `selection_research.db`）

## 3. 存储红线
1. 沙盒数据不得回写主业务库。
2. 选股研究结果不塞回主业务消费表。
3. 原子事实层与旧兼容表并存时，必须明确主消费路径。
