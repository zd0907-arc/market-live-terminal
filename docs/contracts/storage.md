# 数据表与存储边界

## 1. 当前正式数据载体
| 载体 | 用途 |
|---|---|
| `market-data/live/market_data.db` | `market_data_main`；Mac/NAS 当前正式轻量消费库 |
| `market-data/live/user_data.db` | `user_data_main`；Mac/NAS 当前正式用户态配置库 |
| repo 内 `data/market_data.db` | 当前默认不存在；只有旧 compose / old cloud / 显式兼容脚本重建时才允许出现 |
| repo 内 `data/user_data.db` | 当前默认不存在；只有旧 compose / lite / 显式兼容脚本重建时才允许出现 |
| `atomic_compact_main` | 当前正式盘后明细底座；Windows 现役物理名是 `market_atomic_mainboard_compact_current.db`；Mac 主读 `market_atomic_mainboard_compact_current.db` |
| `selection_research_main` | 当前正式每日选股研究库；Windows 现役物理名是 `selection_research.db`；Mac/NAS 主读 `market-data/research/current/selection/selection_research.db` |
| `model_feature_store_main` | 当前正式模型训练特征库；Windows 现役物理名是 `model_feature_store.db`；Mac 主读 `market-data/research/current/selection/model_feature_store.db` |
| repo 内 `data/selection/selection_research.db` | 当前默认不存在；只有显式兼容链重建时才允许出现 |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离域 |
| `backend/sample_data/shadow/market.db` / `backend/sample_data/shadow/market_data.db` / `backend/sample_data/examples/market_data_sample.db` | shadow / sample / 排障对象；不进入正式主链 |

补充：
- 当前 Mac 正式研究根目录是 `/Users/dong/Desktop/AIGC/market-data`
- 正式数据根统一按 `live / research/current / cache / artifacts / incoming` 收口
- `market-data` 根目录旧正式路径兼容入口已删除；真实物理位置固定在 `live/` 与 `research/current/`
- repo 内 `data/selection/selection_research.db` 只按回退 / 兼容副本理解，不再当跨端唯一正式名
- repo 内 `data/market_data.db`、`data/user_data.db` 当前不再默认常驻；只有 old cloud / lite / 兼容脚本显式重建时才允许出现
- `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这些 Windows 旧物理名已退休到冷备区；对外统一按 `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 的 canonical 名解释
- `backend/sample_data/shadow/market.db`、`backend/sample_data/shadow/market_data.db`、`backend/sample_data/examples/market_data_sample.db` 只按 shadow / sample / 排障对象理解，不进入正式主链解释

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
