# 模型训练数据准备盘点（compact DB 基线）

更新时间：2026-05-17

## 结论

当前主线已经切到 compact atomic DB。对后续“星火机会模型 v1.1 / 新选股模型”来说，主粒度仍建议保持 5 分钟，不建议全市场改成 1 分钟。

真正要补的是训练专用特征层：

1. 用新买的 `2024-09 ~ 2026-02` 完整 L2 数据补齐 `order/book/auction`。
2. 基于 5m 原子层生成盘后可用的日级训练宽表。
3. 基于 `atomic_trade_5m` 生成买点窗口、盘中形态、卖点/持仓窗口特征。
4. 涨跌停只依赖 `atomic_limit_state_daily`，不再依赖 `atomic_limit_state_5m`。
5. 旧星火训练脚本需要改成 compact DB resolver，不再硬编码 `market_atomic_mainboard_full_reverse.db`。

## 当前 worktree

| 项 | 值 |
|---|---|
| 主仓库基线 | `main @ 513119c chore: release 5.2.0 app baseline` |
| 新 worktree | `/Users/dong/Desktop/AIGC/market-live-terminal-model-data-audit` |
| 分支 | `codex/model-training-data-audit` |
| 任务边界 | 只做模型训练数据盘点，不处理日跑，不做 compact DB 改造 |

## 当前正式数据入口

本地研究站默认读取：

```text
/Users/dong/Desktop/AIGC/market-data
```

compact atomic 默认入口：

```text
/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db
```

这是一个软链接：

```text
market_atomic_mainboard_compact_current.db
-> market_atomic_mainboard_compact_20250102_20260514.db
```

真实文件约 `22G`，数据已补到 `2026-05-15`。旧 full reverse DB 已移入备份目录：

```text
/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307/
```

模型侧不要继续把旧 full reverse 路径当默认入口。

## 数据目录概览

| 路径 | 大小 | 作用 |
|---|---:|---|
| `/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow` | `22G` | compact atomic 主数据 |
| `/Users/dong/Desktop/AIGC/market-data/atomic_facts/backup_pre_compact_cutover_20260517_172307` | `40G` | 旧库备份，不作为正常训练入口 |
| `/Users/dong/Desktop/AIGC/market-data/selection` | `3.2G` | 选股特征、信号、候选池 |
| `/Users/dong/Desktop/AIGC/market-data/market_heat` | `364M` | 主题热度、主题映射、热点模型 |
| `/Users/dong/Desktop/AIGC/market-data/market_data.db` | `4.0G` | 旧主库 / 页面兼容库 |

## compact atomic DB 结构

### 表清单

| 表 | 是否存在 | 说明 |
|---|---|---|
| `atomic_trade_5m` | 是 | 5分钟成交事实主表 |
| `atomic_trade_daily` | 是 | 日级成交与资金聚合 |
| `atomic_order_5m` | 是 | 5分钟委托/撤单/OIB/CVD |
| `atomic_order_daily` | 是 | 日级委托/撤单/OIB/CVD |
| `atomic_book_state_5m` | 是 | 5分钟盘口厚度/买卖盘状态 |
| `atomic_book_state_daily` | 是 | 日级盘口状态聚合 |
| `atomic_limit_state_daily` | 是 | 日级涨跌停/触板/炸板状态 |
| `atomic_limit_state_5m` | 否 | compact 中已移除，模型不得依赖 |
| `atomic_data_manifest` | 是 | 数据覆盖与质量清单 |
| `atomic_compact_manifest` | 是 | compact 构建与增量清单 |
| `cfg_limit_rule_map` | 是 | 涨跌幅规则配置 |

### 覆盖范围

| 表 | 最早日期 | 最新日期 | 行数 | 交易日数 |
|---|---:|---:|---:|---:|
| `atomic_trade_5m` | 2025-01-02 | 2026-05-15 | 50,608,009 | 327 |
| `atomic_trade_daily` | 2025-01-02 | 2026-05-15 | 1,038,208 | 327 |
| `atomic_limit_state_daily` | 2025-01-02 | 2026-05-15 | 1,038,208 | 327 |
| `atomic_order_5m` | 2026-03-02 | 2026-05-15 | 7,570,362 | 49 |
| `atomic_order_daily` | 2026-03-02 | 2026-05-15 | 156,033 | 49 |
| `atomic_book_state_5m` | 2026-03-02 | 2026-05-15 | 7,457,644 | 49 |
| `atomic_book_state_daily` | 2026-03-02 | 2026-05-15 | 156,033 | 49 |

关键判断：

```text
trade + limit daily 已覆盖 2025-01 ~ 2026-05
order + book 仍只覆盖 2026-03 ~ 2026-05
```

所以新买的 `2024-09 ~ 2026-02` 完整 L2 数据，最重要的价值是补齐历史 `order/book/auction`，而不是改变 5m 主粒度。

### 主要表字段

#### `atomic_trade_5m`

核心字段：

```text
symbol, trade_date, bucket_start,
open, high, low, close,
total_amount, total_volume, trade_count,
l1_main_buy/sell_count,
l1_super_buy/sell_count,
l2_main_buy/sell_count,
l2_super_buy/sell_count,
l1_main_buy/sell/net_amount,
l1_super_buy/sell/net_amount,
l2_main_buy/sell/net_amount,
l2_super_buy/sell/net_amount,
max_trade_amount, avg_trade_amount,
max_parent_order_amount,
top5_parent_concentration_ratio,
source_type, quality_info
```

训练意义：

- 足够支撑 5日/22日机会发现、买点确认、持仓日终判断。
- 不建议改成全市场 1分钟主表。
- 可以从此表派生开盘/尾盘/盘中形态特征。

#### `atomic_trade_daily`

比 5m 多出日级窗口聚合：

```text
am_l2_main_net_amount,
pm_l2_main_net_amount,
open_30m_l2_main_net_amount,
last_30m_l2_main_net_amount,
positive_l2_net_bar_count,
negative_l2_net_bar_count
```

训练意义：

- 当前星火 v1.0 已主要依赖这类日级聚合。
- 后续应继续扩展更多“盘中形态压缩特征”，而不是让模型直接扫 5m 序列。

#### `atomic_order_5m`

字段：

```text
add_buy_amount, add_sell_amount,
cancel_buy_amount, cancel_sell_amount,
cvd_delta_amount, oib_delta_amount,
add_buy/sell_count,
cancel_buy/sell_count,
add_buy/sell_volume,
cancel_buy/sell_volume,
order_event_count,
buy_add_cancel_net_amount,
sell_add_cancel_net_amount
```

训练意义：

- 是买点、卖点、持仓模型最重要的新增信息。
- 当前历史覆盖严重不足，必须用新买数据补齐。

#### `atomic_order_daily`

已有日级关键特征：

```text
am_oib_delta_amount,
pm_oib_delta_amount,
open_60m_oib_delta_amount,
last_30m_oib_delta_amount,
open_60m_cvd_delta_amount,
last_30m_cvd_delta_amount,
positive_oib_bar_count,
negative_oib_bar_count,
positive_cvd_bar_count,
negative_cvd_bar_count,
oib_top3_concentration_ratio,
moderate_positive_oib_bar_count,
moderate_positive_oib_bar_ratio,
positive_oib_streak_max,
buy_support_ratio,
sell_pressure_ratio
```

训练意义：

- 这张表是模型训练最应该优先利用的日级 order 宽表。
- 新数据跑完后，选股模型应该默认纳入这些字段，而不是继续作为 shadow feature 排除。

#### `atomic_book_state_5m`

字段：

```text
snapshot_time,
quote_row_count_5m,
end_bid_resting_volume/amount,
end_ask_resting_volume/amount,
top1_bid/ask_volume,
top5_bid/ask_volume,
top1_bid/ask_amount,
top5_bid/ask_amount,
book_imbalance_ratio,
book_depth_ratio,
book_state_label
```

训练意义：

- 对“次日能不能追”“板前承接”“卖点是否该走”很有价值。
- 不一定直接全量进选股模型，建议先派生日级/窗口特征。

#### `atomic_book_state_daily`

字段：

```text
avg_bid_resting_amount,
avg_ask_resting_amount,
avg_book_imbalance_ratio,
avg_book_depth_ratio,
max_bid_resting_amount,
max_ask_resting_amount,
close_bid_resting_amount,
close_ask_resting_amount,
close_book_imbalance_ratio,
close_book_depth_ratio,
bid_dominant_bar_count,
ask_dominant_bar_count,
thin_book_bar_count,
balanced_bar_count,
valid_bucket_count
```

训练意义：

- 可直接进入日级特征层。
- 对卖点/持仓模型价值高于对 22日选股模型。

#### `atomic_limit_state_daily`

字段：

```text
board_type, risk_flag_type,
prev_close, up_limit_price, down_limit_price,
limit_pct, tick_size,
open_price, high_price, low_price, close_price,
touch_limit_up/down,
is_limit_up/down_close,
touch_limit_up/down_count_5m,
first/last_touch_limit_up/down_time,
broken_limit_up/down,
limit_state_label
```

训练意义：

- 替代旧 `atomic_limit_state_5m`。
- 能满足选股、买点、卖点对涨跌停状态的主要需求。
- 如果需要 5m 级别“触板发生在哪根 bar”，使用 `first_touch_limit_up_time / last_touch_limit_up_time` 和 `atomic_trade_5m` 派生，不恢复旧 5m 状态表。

## selection DB 结构

路径：

```text
/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db
```

### 覆盖范围

| 表 | 最早日期 | 最新日期 | 行数 | 交易日数 |
|---|---:|---:|---:|---:|
| `selection_feature_daily` | 2025-01-02 | 2026-05-15 | 1,585,246 | 328 |
| `selection_signal_daily` | 2025-01-02 | 2026-05-15 | 1,585,246 | 328 |
| `selection_candidate_daily` | 2026-03-02 | 2026-05-15 | 321 | 49 |
| `selection_candidate_sources` | 2026-03-02 | 2026-05-15 | 328 | 49 |

### `selection_feature_daily`

主要字段：

```text
价格/位置：
close, prev_close, daily_return_pct,
return_3d/5d/10d/20d_pct,
volatility_10d/20d,
ma20, ma60, dist_ma20_pct, dist_ma60_pct,
price_position_20d/60d,
breakout_vs_prev20_high_pct

资金：
net_inflow_5d/10d/20d,
positive_inflow_ratio_5d/10d/20d,
main_activity_20d,
activity_ratio_5d/20d,
l1_main_net_3d,
l2_main_net_3d,
l2_vs_l1_strength

L2 order：
l2_order_event_available,
l2_add_buy_3d,
l2_add_sell_3d,
l2_cancel_buy_3d,
l2_cancel_sell_3d,
l2_cvd_3d,
l2_oib_3d

情绪/市值：
sentiment_event_count_5d/20d,
sentiment_heat_ratio,
sentiment_score,
market_cap, name
```

判断：

- 这张表是当前工作台和老规则策略的核心。
- 新买历史完整 L2 跑完后必须重算，否则 `2025-01 ~ 2026-02` 的 `l2_order_event_available` 和 order 特征仍不完整。
- 如果补到 `2024-09`，这张表也要向前扩展，否则训练只看到 atomic，工作台/候选池看不到对应特征。

### `selection_signal_daily`

字段：

```text
stealth_score,
stealth_signal,
breakout_score,
confirm_signal,
distribution_score,
exit_signal,
stealth_reason_strength,
breakout_reason_strength,
distribution_reason_strength,
l2_confirm_bonus,
heat_risk_score,
price_extension_score,
inflow_quality_score,
outflow_pressure_score,
sentiment_heat_score,
l2_distribution_score
```

判断：

- 这是规则策略信号层，不是模型训练必需输入，但对解释和规则基线有价值。
- 如果底层 order/book 被补齐，信号层也要重算，避免模型 v1.1 训练使用新 atomic、工作台仍显示旧信号口径。

### 候选池表

`selection_candidate_sources` 和 `selection_candidate_daily` 已经是模型接入的正式契约表。

后续任何新模型必须输出标准候选记录，不能只写 `latest_candidates.csv`。

## market_heat 结构

路径：

```text
/Users/dong/Desktop/AIGC/market-data/market_heat
```

### 主题热度主表

`fine_theme_heat_daily.db`：

| 表 | 覆盖 |
|---|---|
| `fine_theme_heat_daily` | 2025-01-02 ~ 2026-04-30，319 天 |
| `fine_theme_member_daily` | 2025-01-02 ~ 2026-04-30，319 天 |
| `fine_theme_lifecycle_daily` | 2025-01-02 ~ 2026-04-30，319 天 |
| `fine_theme_forward_return` | 2025-01-02 ~ 2026-04-30，319 天 |

`fine_theme_heat_daily_v2.db`：

| 表 | 覆盖 |
|---|---|
| `fine_theme_heat_daily_v2` | 2025-01-02 ~ 2026-05-13，325 天 |

### 主题映射

| 表 | 数量 |
|---|---:|
| `stock_sector_memberships` | 49,579 条，3,180 只股票 |
| `sector_boards` | 972 个板块 |
| `tradable_themes` | 18 个可交易主题 |
| `tradable_theme_memberships` | 6,489 条，2,843 只股票 |
| `clean_stock_sector_memberships` | 36,541 条，3,180 只股票 |

判断：

- 主题热度对模型解释和过滤很重要。
- 但当前主题热度只从 2025-01 起，不能覆盖你新买的 `2024-09 ~ 2024-12`。
- 如果训练窗口扩到 2024-09，market_heat 也要同步回建，否则 2024-09 ~ 2024-12 要么丢失主题特征，要么训练时强制填空，容易影响模型对牛市启动段的学习。

## 旧星火模型脚本在新基线下的问题

### 仍硬编码旧路径

这些脚本仍默认使用：

```text
/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db
```

涉及：

```text
backend/scripts/research_opportunity_discovery_model.py
backend/scripts/research_opportunity_walk_forward.py
backend/scripts/research_opportunity_short_horizon.py
backend/scripts/research_opportunity_exit_audit.py
backend/scripts/research_opportunity_fusion_h5_22.py
backend/scripts/research_opportunity_postclose_exit_models.py
backend/scripts/research_opportunity_execution_models.py
```

这些脚本后续要统一改为：

```text
candidate_atomic_db_paths()
或显式 --atomic-db 指向 compact current
```

### 训练默认没有打开 order/book 特征

旧训练逻辑里有：

```python
feature_cols = available_feature_columns(data, include_orderbook=False)
```

这在旧数据缺 order/book 时是合理的。新买完整历史 L2 跑完后，v1.1 应该重新评估：

```python
include_orderbook=True
```

但前提是：

1. `2024-09 ~ 2026-02` 的 order/book 已补齐。
2. 对 `2024-09 ~ 2026-05` 的 coverage 做过验收。
3. order/book 缺失标记进入训练特征，不能隐式填 0。

## 是否需要改成 1分钟

结论：不建议把主链路改成全市场 1分钟。

理由：

1. 当前任务是盘后选股、次日开盘决策、盘后持仓判断，不是日内自动交易。
2. 5m 已经能表达开盘、尾盘、盘中承接、撤单、资金强弱。
3. 全市场 1m 会让存储和训练 IO 大幅增加，边际收益不确定。
4. 模型更需要的是稳定的窗口特征，而不是更细的 raw bar。

可以考虑的不是 1m 主表，而是事件窗口特征：

- 集合竞价摘要。
- 开盘 5/10/15/30/60 分钟窗口。
- 尾盘 15/30/60 分钟窗口。
- 首次触板前后窗口。
- 炸板/回封窗口。

这些可以从现有 raw / 5m / auction 表派生，不需要全市场长期维护 1m atomic 主表。

## 建议新增的训练专用特征层

后续训练不要每次直接扫 5m 原子表。建议新增或离线产出以下训练层。

### 1. `model_feature_daily_v1`

粒度：

```text
symbol + trade_date
```

来源：

```text
atomic_trade_daily
atomic_order_daily
atomic_book_state_daily
atomic_limit_state_daily
selection_feature_daily
selection_signal_daily
market_heat
```

字段方向：

- 价格位置：20/60日位置、突破距离、回撤、波动率。
- 成交资金：L1/L2 主力净额、超大单净额、活跃度。
- 委托行为：OIB/CVD、买盘承接、卖压、撤买/撤卖。
- 盘口状态：收盘盘口偏向、盘口薄厚、买盘/卖盘主导 bar 数。
- 涨跌停状态：触板、封板、炸板、首次触板时间。
- 热点主题：主题排名、主题生命周期、主题强度、是否高潮。
- 市场环境：市场赚钱效应、涨跌家数、涨停数、热点集中度。
- coverage：order/book/heat/sentiment 是否可用。

用途：

- 22日机会发现模型。
- 5/10日短周期机会模型。
- 每日候选解释。

### 2. `model_feature_intraday_shape_v1`

粒度：

```text
symbol + trade_date
```

来源：

```text
atomic_trade_5m
atomic_order_5m
atomic_book_state_5m
```

字段方向：

- 开盘 15/30/60 分钟收益、振幅、成交额占比。
- 开盘 15/30/60 分钟 L2 主力净额占比。
- 开盘 OIB/CVD 趋势。
- 尾盘 30/60 分钟资金回流/流出。
- 全天资金曲线斜率：前高后低、后高前低、持续流入。
- 正 L2 bar 占比、最长连续正流入 bar。
- OIB 连续性、CVD 连续性。
- 盘口偏向持续性。
- 日内高点出现时间、收盘位置。

用途：

- 买点模型。
- 卖点/持仓模型。
- 解释“资金是早盘冲高出货，还是尾盘回流”。

### 3. `model_feature_entry_window_v1`

粒度：

```text
symbol + signal_date + entry_date
```

来源：

```text
signal_date 的盘后数据
entry_date 的开盘 / 前15分钟窗口
```

注意：

- 如果用于真实盘后决策，`entry_date` 前15分钟是次日盘中才知道的信息，不能参与前一晚“是否推荐”。
- 但它可以用于研究“次日开盘后是否确认买入”的独立模型。

字段方向：

- 开盘跳空幅度。
- 是否涨停开盘 / 接近涨停。
- 前 5/15 分钟价格是否破开盘。
- 前 5/15 分钟 L2 主力净额。
- 前 5/15 分钟 OIB/CVD。
- 开盘盘口承接。

用途：

- 如果未来允许 9:45 决策，可训练买点确认模型。
- 如果坚持纯盘后决策，则只作为回测分析，不进入晚间候选模型。

### 4. `model_feature_exit_daily_v1`

粒度：

```text
position_id 或 symbol + entry_date + holding_date
```

来源：

```text
持仓路径上的 daily + intraday_shape
```

字段方向：

- 持仓天数。
- 当前收益、最大浮盈、从峰值回撤。
- 当日收盘位置。
- 当日 L2 主力/超大单净额。
- 当日 OIB/CVD 变化。
- 盘口买卖厚度变化。
- 是否触板、炸板、跌破关键均线。
- 热点主题是否退潮。
- 市场环境是否走弱。

用途：

- 守势持仓模型 v1.0 正式化。
- 每天盘后对已有持仓输出 `hold / watch_risk / sell_next_open`。

### 5. `model_market_state_daily_v1`

粒度：

```text
trade_date
```

字段方向：

- 全市场中位涨幅。
- 涨跌家数比例。
- 涨停数、跌停数、炸板率。
- 主板 10cm 赚钱效应。
- 成交额总量与变化。
- L2 主力净流入强度。
- 热点集中度。
- 主题生命周期分布。

用途：

- 防止模型只学习 2024-09 后偏强市场。
- 作为候选模型的市场状态闸门。
- 用于解释“今天适不适合进攻”。

## 新买历史数据跑数建议

### 先跑哪些

建议先跑 `2026-02` 完整月。

原因：

- 它紧挨现有完整 `2026-03+` order/book 覆盖。
- 最容易验证新旧月份字段是否连续。
- 跑完后可以马上做一次 v1.1-pre 训练，对比 order/book 新特征是否有增益。

然后按季度或 3个月一批往前跑：

```text
2025-12 ~ 2026-02
2025-09 ~ 2025-11
2025-06 ~ 2025-08
2025-03 ~ 2025-05
2024-09 ~ 2025-02
```

### 每批验收标准

每批跑完至少验：

1. `atomic_trade_daily / atomic_trade_5m` 行数和交易日数。
2. `atomic_order_daily / atomic_order_5m` 行数和交易日数。
3. `atomic_book_state_daily / atomic_book_state_5m` 行数和交易日数。
4. `atomic_limit_state_daily` 是否同步覆盖。
5. `atomic_data_manifest` 是否有该批次记录。
6. `selection_feature_daily` 是否重算到同样日期。
7. `market_heat` 是否覆盖同样日期。
8. order/book coverage 特征不能默默填 0，必须有 coverage flag。

### 跑完后训练顺序

1. 只用 `2026-02 + 2026-03~05` 做 v1.1-pre。
2. 比较：
   - 旧特征 vs 新增 order/book 特征；
   - 只选股模型 vs 选股 + 持仓模型；
   - 22日模型 vs 5/10日短线模型。
3. 如果新增 order/book 有稳定增益，再等全量 `2024-09~2026-05` 完成后冻结 v1.1。

## 训练前必须补齐的代码调整

这些不是数据库改造，是模型训练侧适配。

### P0：路径与 compact 兼容

- 训练脚本统一使用 `candidate_atomic_db_paths()`。
- 或者所有训练命令必须显式传入：

```text
--atomic-db /Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db
```

- 文档和 manifest 不再写旧 full reverse 文件名作为唯一数据源。

### P0：去掉 `atomic_limit_state_5m` 假设

- 训练脚本只能读 `atomic_limit_state_daily`。
- 需要 5m 触板窗口时，从 daily 的 first/last touch time + `atomic_trade_5m` 派生。

### P1：训练宽表构建器

新增模型侧构建器，产出稳定文件或数据库表：

```text
data/selection/model_features/spark_v1_1/
  model_feature_daily_v1.parquet
  model_feature_intraday_shape_v1.parquet
  model_market_state_daily_v1.parquet
  feature_manifest.json
```

如果继续用 SQLite，也应放到独立研究库，不直接塞进 atomic 原子库。

### P1：coverage 进入特征

必须显式包含：

```text
has_order_5m
has_order_daily
has_book_5m
has_book_daily
has_heat
has_sentiment
```

否则历史缺失期填 0 会让模型误以为“没有挂单行为”，而不是“数据不可用”。

### P2：模型训练版本

建议下一版命名：

```text
source_id: spark_opportunity_selector
source_name: 星火机会模型 1.1
source_version: 1.1
artifact_version: opportunity_discovery_full_l2_compact_v1_1
```

产物目录：

```text
data/selection/models/spark_opportunity_selector/1.1/
  source_manifest.json
  model.joblib
  feature_columns.json
  training_config.json
  label_spec.json
  backtest_summary.json
  sample_candidates.json
  README.md
```

## 对当前模型训练模块的影响

页面侧已经有“模型训练”模块框架，但目前主要展示 PPO 历史复盘。

模型侧后续应输出任务记录，页面才能展示：

- 数据集版本。
- 训练窗口。
- 特征版本。
- 模型版本。
- 回测摘要。
- 候选样例。
- 产物路径。

但本次盘点不改页面。

## 建议的下一步

1. 先让 Windows 跑 `2026-02` 完整 full L2。
2. merge/append 到 compact 后，验收 order/book/limit/selection/heat 覆盖。
3. 模型侧改训练脚本路径和 daily limit 状态依赖。
4. 构建 `model_feature_daily_v1` 和 `model_feature_intraday_shape_v1`。
5. 训练 `spark_opportunity_selector@1.1-pre`，与 1.0 做同窗口对比。
6. 再继续跑全量 `2024-09 ~ 2026-02`，最后冻结 1.1。
