# 数据表与存储边界

## 1. 当前正式数据载体
| 载体 | 用途 |
|---|---|
| `market-data/market_data.db` | Mac 正式主读轻量消费库；Windows 正式产出后同步到这里 |
| repo 内 `data/market_data.db` | 本地回退 / 兼容副本，不是默认正式研究主库 |
| `atomic_compact_main` | 当前正式盘后明细底座；Windows 当前实际主写物理名仍可能是 `compact_smoke_*`，Mac 主读 `market_atomic_mainboard_compact_current.db` |
| `selection_research_main` | 当前正式每日选股研究库；Windows 主写 `selection_research_windows.db`，Mac 主读 `market-data/selection/selection_research.db` |
| `model_feature_store_main` | 当前正式模型训练特征库；Windows 当前实际主写物理名仍可能是 `model_feature_store_smoke_*`，Mac 主读 `market-data/selection/model_feature_store.db` |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离域 |
| `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db` | shadow / sample / 排障对象；不进入正式主链 |

补充：
- 当前 Mac 正式研究根目录是 `/Users/dong/Desktop/AIGC/market-data`
- repo 内 `data/selection/selection_research.db` 只按回退 / 兼容副本理解，不再当跨端唯一正式名
- `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这些 Windows 物理名承担正式语义，但对外统一按 `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 理解
- `backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 只按 shadow / sample / 排障对象理解，不进入正式主链解释

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
- 其他研究派生结果（统一归属 `selection_research_main`；不要再把 `selection_research.db` 写成跨端唯一正式名）

### E. 模型训练特征
- `model_feature_build_runs`
- `model_feature_manifest`
- `model_market_state_daily_v1`
- `model_feature_daily_v1`
- `model_feature_intraday_shape_v1`
- `model_label_forward_return_v1`

## 3. 存储红线
1. 沙盒数据不得回写主业务库。
2. 选股研究结果不塞回主业务消费表。
3. 盘后明细底座的主消费路径是 `atomic_compact_main`，不要再把 `full_reverse` 讲成当前正式底座。
4. `model_feature_store_main` 不并回 `selection_research_main` 或 `market_data.db`。
