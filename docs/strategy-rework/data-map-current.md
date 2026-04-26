# 现有选股策略字段与数据源盘点

## 1. 当前代码入口

- 策略计算：`backend/app/services/selection_research.py`
- 结果表结构：`backend/app/db/selection_db.py`
- API：`backend/app/routers/selection.py`
- 前端页面：`src/components/selection/SelectionResearchPage.tsx`
- 右侧决策视图：`src/components/selection/SelectionDecisionPanel.tsx`

## 2. 正式本地数据路径

正式本地研究站由 `ops/start_local_research_station.sh` 指向：

```text
/Users/dong/Desktop/AIGC/market-data/market_data.db
/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db
/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db
```

注意：项目内 `data/` 有旧/残缺数据，策略重构与回测默认应使用 `/Users/dong/Desktop/AIGC/market-data`。

## 3. 当前特征表

表：`selection_feature_daily`

来源字段：

| 特征域 | 字段 | 当前计算方式 | 上游表 |
| --- | --- | --- | --- |
| 价格收益 | `daily_return_pct`, `return_3d_pct`, `return_5d_pct`, `return_10d_pct`, `return_20d_pct` | `close / close.shift(n) - 1` | `local_history` 或 `atomic_trade_daily` |
| 均线位置 | `ma20`, `ma60`, `dist_ma20_pct`, `dist_ma60_pct` | close 滚动均线与偏离 | 同上 |
| 区间位置 | `price_position_20d`, `price_position_60d` | `(close - rolling_low) / (rolling_high - rolling_low)` | 同上 |
| 平台突破 | `breakout_vs_prev20_high_pct` | `close / 前20日最高收盘 - 1` | 同上 |
| L1资金 | `net_inflow_5d/10d/20d`, `positive_inflow_ratio_*`, `main_activity_20d`, `activity_ratio_*` | 日级净流入滚动和、正流入占比、主买+主卖活跃额 | `local_history` 或 `atomic_trade_daily` fallback |
| L2资金 | `l1_main_net_3d`, `l2_main_net_3d`, `l2_vs_l1_strength` | 3日滚动 L1/L2 主力净额与强度比 | `history_daily_l2` 或 `atomic_trade_daily` |
| L2挂撤单 | `l2_add_buy_3d`, `l2_add_sell_3d`, `l2_cancel_buy_3d`, `l2_cancel_sell_3d`, `l2_cvd_3d`, `l2_oib_3d`, `l2_order_event_available` | 5m聚合后3日滚动 | `history_5m_l2` 或 `atomic_trade_5m + atomic_order_5m` |
| 情绪 | `sentiment_event_count_5d/20d`, `sentiment_heat_ratio`, `sentiment_score` | 事件数量热度比、日评分 | `sentiment_events`, `sentiment_daily_scores` |
| 元数据 | `name`, `market_cap` | 合并元数据 | `stock_universe_meta`, `watchlist` |

## 4. 当前三类信号

表：`selection_signal_daily`

### 4.1 吸筹前置 `stealth`

字段：`stealth_score`, `stealth_signal`

核心因子：
- `positive_inflow_ratio_10d`
- `net_inflow_20d / main_activity_20d`
- `activity_ratio_20d`
- `dist_ma20_pct`
- `return_10d_pct`
- `volatility_20d`
- `price_position_60d`

触发：

```text
stealth_score >= 60
positive_inflow_ratio_10d >= 0.5
return_10d_pct <= 18
```

### 4.2 启动确认 `breakout`

字段：`breakout_score`, `confirm_signal`

核心因子：
- `stealth_score`
- `breakout_vs_prev20_high_pct`
- `return_5d_pct`
- `price_position_60d`
- `net_inflow_5d`
- `l2_vs_l1_strength` 或 `l2_main_net_3d`

触发：

```text
breakout_score >= 65
stealth_score >= 55
return_5d_pct >= 1.5
```

### 4.3 出货风险 `distribution`

字段：`distribution_score`, `exit_signal`

核心因子：
- `return_20d_pct`
- `-net_inflow_5d`
- `sentiment_heat_ratio`
- `l2_cancel_buy_3d`
- `l2_add_sell_3d`
- `-l2_oib_3d`
- `dist_ma20_pct`

触发：

```text
distribution_score >= 65
return_20d_pct >= 10
```

## 5. 当前数据现状快照

截至本次盘点：

### `/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db`

- `selection_feature_daily`：1,000,078 行，覆盖 `2025-01-02 ~ 2026-04-24`，约 3,222 只。
- `selection_signal_daily`：1,000,078 行，覆盖 `2025-01-02 ~ 2026-04-24`。
- 最新日 `2026-04-24`：吸筹 947、启动 22、出货 14。

### `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`

- `atomic_trade_daily`：1,000,078 行，覆盖 `2025-01-02 ~ 2026-04-24`。
- `atomic_trade_5m`：48,753,567 行，覆盖 `2025-01-02 ~ 2026-04-24`。
- `atomic_order_5m`：5,714,078 行，覆盖 `2026-03-02 ~ 2026-04-24`。
- `atomic_order_daily` 已有更适合策略的日级挂撤单聚合字段，但旧策略没有直接使用。

### 明显缺口

- `stock_universe_meta` 为空，名称/市值缺失。
- `stock_events` 为空。
- `sentiment_daily_scores` 只有 4 行，不适合作为核心因子。
- 当前策略把“吸筹、启动、出货”拆成三个平行分数，无法表达资金生命周期。
