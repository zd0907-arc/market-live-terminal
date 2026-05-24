# 模型训练特征层需求规格 v1

更新时间：2026-05-17

## 结论

本需求给数据库/特征层实现会话使用。目标不是立刻训练模型，而是先把后续模型训练需要的数据底座补齐。

核心要求：

1. 原子事实层继续以 compact atomic DB 为主，不恢复 `atomic_limit_state_5m`。
2. 5分钟是主粒度，不建设全市场 1分钟主表。
3. 新增独立的模型特征库，不把模型训练字段继续塞进 atomic 事实库。
4. 新买的 `2024-09 ~ 2026-02` 完整 L2 数据跑完后，必须补齐历史 `order/book/auction`。
5. 市场环境表必须加入“中证1000是否在20日线上方”。
6. 所有训练特征必须有 coverage flag，不能把“数据缺失”静默填成 0。

推荐新库：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
```

该库是模型训练/研究层，不是 atomic 原子层，不直接服务普通页面读原始行情。

## 实现会话边界

建议新开数据库实现会话，从当前 `main` 新开：

```text
worktree: /Users/dong/Desktop/AIGC/market-live-terminal-model-feature-store
branch: codex/model-feature-store-v1
```

实现会话负责：

- 建 schema。
- 写特征构建脚本。
- 跑小样本。
- 输出验证报告。

实现会话不负责：

- 训练星火模型。
- 改 PPO 页面主入口。
- 大范围重构每日 postclose 跑数。
- 合并/恢复旧 full reverse DB。
- 恢复 `atomic_limit_state_5m`。

## 当前数据链路

### 当前事实

```text
Windows 下载/解压/跑原始 L2
-> 产出 atomic daily / 5m / order / book / auction / limit daily
-> Mac 读取 compact atomic DB
-> selection DB / market_heat / workbench 使用加工结果
```

当前 Mac compact atomic 入口：

```text
/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db
```

当前 compact DB 状态：

| 表 | 覆盖 |
|---|---|
| `atomic_trade_5m` | 2025-01-02 ~ 2026-05-15 |
| `atomic_trade_daily` | 2025-01-02 ~ 2026-05-15 |
| `atomic_limit_state_daily` | 2025-01-02 ~ 2026-05-15 |
| `atomic_order_5m` | 2026-03-02 ~ 2026-05-15 |
| `atomic_order_daily` | 2026-03-02 ~ 2026-05-15 |
| `atomic_book_state_5m` | 2026-03-02 ~ 2026-05-15 |
| `atomic_book_state_daily` | 2026-03-02 ~ 2026-05-15 |

关键缺口：

```text
2024-09 ~ 2026-02 的 order/book/auction 还没进入 compact DB。
```

### 旧方案

旧星火 v1.0 训练方式：

- 训练脚本临时 join `atomic + selection + heat`。
- 默认硬编码旧 full reverse DB。
- `order/book` 作为 shadow features，默认不进入训练。
- 没有独立稳定的模型特征库。
- 市场环境特征较弱。
- 持仓/卖点模型主要基于研究产物，没有生产级输入表。

### 新方案

新方案增加一层模型特征库：

```text
compact atomic DB
selection_research.db
market_heat/*.db
market/index data
        |
        v
model_feature_store.db
        |
        v
模型训练 / 回测 / 每日候选适配器
```

训练时优先读取特征库，而不是每次扫 5m 原子表。

## 命名和单位约定

### 字段命名

- `_pct`：百分比单位，例如 `5.2` 表示 `5.2%`。
- `_ratio`：小数比例，例如 `0.052` 表示 `5.2%`。
- `_yi`：亿元单位。
- `_flag`：0/1。
- `_count`：计数。
- `_min`：分钟偏移，通常从 09:30 起算。

### 点时安全

盘后候选模型只允许使用 `trade_date` 收盘后已经存在的数据。

允许：

- `trade_date` 当天收盘价、成交、委托、盘口、涨跌停状态。
- `trade_date` 当天收盘后可计算的市场环境。
- `trade_date` 当天的热点主题状态。

禁止：

- `trade_date + 1` 的开盘价参与晚间候选模型。
- 未来 5/10/22 日收益参与候选特征。
- 未来高低点参与候选特征。
- 用回测输出 CSV 伪装每日候选。

训练标签和买点确认表可以使用未来数据，但必须放在独立 label / entry 表，不能混入生产候选特征表。

## 新增表总览

建议在 `model_feature_store.db` 新建：

| 表 | 粒度 | 用途 |
|---|---|---|
| `model_feature_build_runs` | run | 构建任务记录 |
| `model_feature_manifest` | table/version/date | 数据血缘和覆盖 |
| `model_market_index_daily` | index_code + trade_date | 指数行情，至少中证1000 |
| `model_market_state_daily_v1` | trade_date | 市场环境 |
| `model_feature_daily_v1` | symbol + trade_date | 日级主特征宽表 |
| `model_feature_intraday_shape_v1` | symbol + trade_date | 5m 压缩形态特征 |
| `model_feature_entry_window_v1` | symbol + signal_date + entry_date | 次日买点确认研究表 |
| `model_feature_exit_daily_v1` | symbol + entry_date + holding_date | 持仓/卖点训练表 |
| `model_label_forward_return_v1` | symbol + trade_date + horizon | 训练标签表 |

P0 必做：

- `model_feature_build_runs`
- `model_feature_manifest`
- `model_market_index_daily`
- `model_market_state_daily_v1`
- `model_feature_daily_v1`
- `model_feature_intraday_shape_v1`
- `model_label_forward_return_v1`

P1 再做：

- `model_feature_entry_window_v1`
- `model_feature_exit_daily_v1`

## 表 1：`model_feature_build_runs`

用途：记录每次构建，方便追溯。

建议字段：

```sql
run_id TEXT PRIMARY KEY,
feature_version TEXT NOT NULL,
date_from TEXT NOT NULL,
date_to TEXT NOT NULL,
status TEXT NOT NULL,
source_atomic_db TEXT NOT NULL,
source_selection_db TEXT NOT NULL,
source_heat_db TEXT,
source_market_db TEXT,
git_commit TEXT,
config_json TEXT NOT NULL,
row_counts_json TEXT,
validation_json TEXT,
started_at TEXT NOT NULL,
finished_at TEXT,
error_message TEXT
```

要求：

- 每次构建必须写入。
- 小样本失败也要记录。
- `source_atomic_db` 应指向 compact current 或实际 compact 文件，不能指向旧 full reverse 默认路径。

## 表 2：`model_feature_manifest`

用途：记录每张特征表的覆盖范围和质量。

建议字段：

```sql
table_name TEXT NOT NULL,
feature_version TEXT NOT NULL,
date_from TEXT NOT NULL,
date_to TEXT NOT NULL,
trade_day_count INTEGER NOT NULL,
row_count INTEGER NOT NULL,
symbol_count INTEGER,
coverage_json TEXT NOT NULL,
source_tables_json TEXT NOT NULL,
generated_at TEXT NOT NULL,
PRIMARY KEY(table_name, feature_version, date_from, date_to)
```

`coverage_json` 至少包含：

```json
{
  "trade_daily_days": 327,
  "order_daily_days": 49,
  "book_daily_days": 49,
  "heat_days": 325,
  "market_index_days": 327
}
```

## 表 3：`model_market_index_daily`

用途：为市场状态提供指数行情。至少要支持中证1000。

建议字段：

```sql
index_code TEXT NOT NULL,
index_name TEXT NOT NULL,
trade_date TEXT NOT NULL,
open REAL,
high REAL,
low REAL,
close REAL NOT NULL,
volume REAL,
amount REAL,
source TEXT NOT NULL,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(index_code, trade_date)
```

最低要求：

| 指数 | 建议 code | 必需 |
|---|---|---|
| 中证1000 | `000852.SH` 或项目统一格式 | 是 |
| 中证500 | `000905.SH` | 建议 |
| 沪深300 | `000300.SH` | 建议 |
| 上证指数 | `000001.SH` | 建议 |
| 创业板指 | `399006.SZ` | 建议 |

如果项目已有指数日线来源，可以从现有库同步；如果没有，先新增该表。

中证1000字段不得缺失：

- `csi1000_close`
- `csi1000_ma20`
- `csi1000_above_ma20`
- `csi1000_dist_ma20_pct`

前 20 个交易日因为均线 warmup 可以为空，之后不能为空。

## 表 4：`model_market_state_daily_v1`

粒度：

```text
trade_date
```

用途：

- 判断当天是否适合进攻。
- 避免模型只学习强市场。
- 给选股模型和仓位/持仓模型提供市场状态闸门。

建议字段：

```sql
trade_date TEXT PRIMARY KEY,
feature_version TEXT NOT NULL,

market_total_amount_yi REAL,
market_total_amount_ma20_yi REAL,
market_amount_ratio_20d REAL,
market_mean_return_pct REAL,
market_median_return_pct REAL,
market_advancer_ratio REAL,
market_decliner_ratio REAL,
market_up_gt3_count INTEGER,
market_down_lt_minus3_count INTEGER,

limit_up_count INTEGER,
limit_down_count INTEGER,
touch_limit_up_count INTEGER,
broken_limit_up_count INTEGER,
sealed_limit_up_count INTEGER,
broken_limit_up_ratio REAL,

csi1000_close REAL,
csi1000_ma20 REAL,
csi1000_above_ma20 INTEGER,
csi1000_dist_ma20_pct REAL,
csi1000_ma20_slope_5d_pct REAL,
csi1000_return_1d_pct REAL,
csi1000_return_5d_pct REAL,
csi1000_return_20d_pct REAL,

csi500_above_ma20 INTEGER,
hs300_above_ma20 INTEGER,
sh_index_above_ma20 INTEGER,
gem_index_above_ma20 INTEGER,

hot_theme_top1_score REAL,
hot_theme_top5_avg_score REAL,
hot_theme_top10_amount_ratio REAL,
hot_theme_top10_l2_net_yi REAL,
hot_theme_new_count INTEGER,
hot_theme_continuing_count INTEGER,
hot_theme_climax_count INTEGER,
hot_theme_fading_count INTEGER,
hot_theme_concentration_top3 REAL,

has_index_data INTEGER NOT NULL DEFAULT 0,
has_heat_data INTEGER NOT NULL DEFAULT 0,
has_order_data INTEGER NOT NULL DEFAULT 0,
has_book_data INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

字段来源：

| 字段 | 来源 |
|---|---|
| 市场成交额、涨跌中位数、涨跌家数 | `atomic_trade_daily` |
| 涨停/炸板/跌停 | `atomic_limit_state_daily` |
| order/book coverage | `atomic_order_daily` / `atomic_book_state_daily` |
| 中证1000等指数 | `model_market_index_daily` |
| 热点集中度 | `fine_theme_heat_daily_v2` 优先，必要时回退 `fine_theme_heat_daily` |

计算要求：

- `csi1000_above_ma20 = close > ma20`。
- `csi1000_dist_ma20_pct = (close / ma20 - 1) * 100`。
- `csi1000_ma20_slope_5d_pct = (ma20 / ma20.shift(5) - 1) * 100`。
- `broken_limit_up_ratio = broken_limit_up_count / nullif(touch_limit_up_count, 0)`。
- `hot_theme_concentration_top3` 建议用 Top3 主题成交额占 Top10 主题成交额比例。

## 表 5：`model_feature_daily_v1`

粒度：

```text
symbol + trade_date
```

用途：

- 22日机会发现模型主输入。
- 5/10日短线机会模型主输入。
- 每日候选解释字段来源。

主键：

```sql
PRIMARY KEY(symbol, trade_date, feature_version)
```

建议字段：

```sql
symbol TEXT NOT NULL,
trade_date TEXT NOT NULL,
feature_version TEXT NOT NULL,
name TEXT,
board_type TEXT,
risk_flag_type TEXT,
market_cap REAL,

open REAL,
high REAL,
low REAL,
close REAL,
prev_close REAL,
return_1d_pct REAL,
return_3d_pct REAL,
return_5d_pct REAL,
return_10d_pct REAL,
return_20d_pct REAL,
volatility_10d REAL,
volatility_20d REAL,
ma20 REAL,
ma60 REAL,
dist_ma20_pct REAL,
dist_ma60_pct REAL,
price_position_20d REAL,
price_position_60d REAL,
breakout_vs_prev20_high_pct REAL,
drawdown_from_20d_high_pct REAL,
amount_yi REAL,
amount_ratio_20d REAL,
trade_count INTEGER,
trade_count_ratio_20d REAL,

l1_main_net_yi REAL,
l1_super_net_yi REAL,
l2_main_net_yi REAL,
l2_super_net_yi REAL,
l1_main_net_ratio REAL,
l1_super_net_ratio REAL,
l2_main_net_ratio REAL,
l2_super_net_ratio REAL,
active_buy_strength REAL,
open_30m_l2_main_net_ratio REAL,
last_30m_l2_main_net_ratio REAL,
am_l2_main_net_ratio REAL,
pm_l2_main_net_ratio REAL,
positive_l2_bar_ratio REAL,

oib_delta_yi REAL,
cvd_delta_yi REAL,
oib_ratio REAL,
cvd_ratio REAL,
add_buy_ratio REAL,
add_sell_ratio REAL,
cancel_buy_ratio REAL,
cancel_sell_ratio REAL,
open_60m_oib_ratio REAL,
last_30m_oib_ratio REAL,
open_60m_cvd_ratio REAL,
last_30m_cvd_ratio REAL,
positive_oib_bar_ratio REAL,
positive_cvd_bar_ratio REAL,
positive_oib_streak_max INTEGER,
oib_top3_concentration_ratio REAL,
buy_support_ratio REAL,
sell_pressure_ratio REAL,
support_pressure_spread REAL,

avg_book_imbalance_ratio REAL,
close_book_imbalance_ratio REAL,
avg_book_depth_ratio REAL,
close_book_depth_ratio REAL,
bid_dominant_bar_ratio REAL,
ask_dominant_bar_ratio REAL,
thin_book_bar_ratio REAL,
close_bid_resting_amount_yi REAL,
close_ask_resting_amount_yi REAL,
close_bid_ask_amount_ratio REAL,

touch_limit_up INTEGER,
touch_limit_down INTEGER,
is_limit_up_close INTEGER,
is_limit_down_close INTEGER,
broken_limit_up INTEGER,
broken_limit_down INTEGER,
limit_state_label TEXT,
first_touch_limit_up_min INTEGER,
last_touch_limit_up_min INTEGER,

hot_theme_best_rank INTEGER,
hot_theme_score REAL,
hot_theme_persistence_score REAL,
hot_theme_member_count INTEGER,
hot_theme_is_top10 INTEGER,
hot_theme_is_new_hot INTEGER,
hot_theme_is_continuing_hot INTEGER,
hot_theme_is_climax_hot INTEGER,
hot_theme_is_fading INTEGER,
hot_theme_l2_main_net_yi REAL,

csi1000_above_ma20 INTEGER,
csi1000_dist_ma20_pct REAL,
market_advancer_ratio REAL,
market_median_return_pct REAL,
market_total_amount_yi REAL,
market_amount_ratio_20d REAL,
market_limit_up_count INTEGER,
market_broken_limit_up_ratio REAL,
hot_theme_concentration_top3 REAL,

has_trade_daily INTEGER NOT NULL DEFAULT 0,
has_trade_5m INTEGER NOT NULL DEFAULT 0,
has_order_daily INTEGER NOT NULL DEFAULT 0,
has_order_5m INTEGER NOT NULL DEFAULT 0,
has_book_daily INTEGER NOT NULL DEFAULT 0,
has_book_5m INTEGER NOT NULL DEFAULT 0,
has_limit_daily INTEGER NOT NULL DEFAULT 0,
has_heat INTEGER NOT NULL DEFAULT 0,
has_market_state INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

计算要求：

- `*_ratio` 类资金字段分母优先用 `total_amount`。
- `support_pressure_spread = buy_support_ratio - sell_pressure_ratio`。
- `bid_dominant_bar_ratio = bid_dominant_bar_count / valid_bucket_count`。
- `thin_book_bar_ratio = thin_book_bar_count / valid_bucket_count`。
- `first_touch_limit_up_min` 用 `atomic_limit_state_daily.first_touch_limit_up_time` 转换为从 09:30 起的分钟偏移；无触板为空。
- 不能从 `atomic_limit_state_5m` 取任何字段。
- `has_order_daily=0` 时，order 字段可以为空或 0，但必须保留 flag。

## 表 6：`model_feature_intraday_shape_v1`

粒度：

```text
symbol + trade_date
```

用途：

- 把 5m 序列压缩为模型可直接吃的形态特征。
- 避免训练时每次扫 5m 大表。

主键：

```sql
PRIMARY KEY(symbol, trade_date, feature_version)
```

建议字段：

```sql
symbol TEXT NOT NULL,
trade_date TEXT NOT NULL,
feature_version TEXT NOT NULL,

valid_bar_count INTEGER,
missing_bar_count INTEGER,
first_bar_time TEXT,
last_bar_time TEXT,

intraday_range_pct REAL,
intraday_close_position REAL,
high_time_min INTEGER,
low_time_min INTEGER,
high_before_1030 INTEGER,
low_after_1430 INTEGER,

open_5m_return_pct REAL,
open_15m_return_pct REAL,
open_30m_return_pct REAL,
open_60m_return_pct REAL,
open_15m_high_from_open_pct REAL,
open_15m_low_from_open_pct REAL,
open_30m_amount_ratio REAL,
open_60m_amount_ratio REAL,

open_15m_l2_main_net_ratio REAL,
open_30m_l2_main_net_ratio REAL,
open_60m_l2_main_net_ratio REAL,
open_15m_l2_super_net_ratio REAL,
open_15m_oib_ratio REAL,
open_15m_cvd_ratio REAL,
open_15m_book_imbalance_avg REAL,

last_15m_return_pct REAL,
last_30m_return_pct REAL,
last_60m_return_pct REAL,
last_30m_amount_ratio REAL,
last_30m_l2_main_net_ratio REAL,
last_30m_l2_super_net_ratio REAL,
last_30m_oib_ratio REAL,
last_30m_cvd_ratio REAL,
last_30m_book_imbalance_avg REAL,

l2_main_net_positive_bar_ratio REAL,
l2_super_net_positive_bar_ratio REAL,
oib_positive_bar_ratio REAL,
cvd_positive_bar_ratio REAL,
longest_l2_main_positive_streak INTEGER,
longest_oib_positive_streak INTEGER,

l2_main_net_curve_slope REAL,
oib_curve_slope REAL,
cvd_curve_slope REAL,
front_loaded_l2_flow INTEGER,
back_loaded_l2_flow INTEGER,
late_day_reversal_up INTEGER,
late_day_distribution INTEGER,

has_order_5m INTEGER NOT NULL DEFAULT 0,
has_book_5m INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

计算要求：

- open window 以连续竞价开始为准，不把集合竞价混入 09:30 bar。
- 如果当前原子层没有 session phase，先按 `bucket_start >= 09:30` 处理，并在 manifest 记录。
- `intraday_close_position = (close - intraday_low) / (intraday_high - intraday_low)`。
- 曲线 slope 可先用累计净额按 bar index 做一阶线性拟合斜率。
- `front_loaded_l2_flow=1` 表示前半日累计净额占全天净额比重过高且尾盘回落；阈值写入 config。
- `late_day_distribution=1` 表示尾盘价格不弱但 L2/OIB 明显走弱；阈值写入 config。

## 表 7：`model_feature_entry_window_v1`

粒度：

```text
symbol + signal_date + entry_date
```

用途：

- 训练“次日是否适合买”的买点确认模型。
- 不作为晚间候选模型的输入。

建议字段：

```sql
symbol TEXT NOT NULL,
signal_date TEXT NOT NULL,
entry_date TEXT NOT NULL,
feature_version TEXT NOT NULL,

signal_close REAL,
entry_open REAL,
open_gap_pct REAL,
entry_open_limit_up INTEGER,
entry_open_near_limit_up INTEGER,
entry_unbuyable_limit_up INTEGER,

first_5m_return_pct REAL,
first_15m_return_pct REAL,
first_15m_high_from_open_pct REAL,
first_15m_low_from_open_pct REAL,
first_15m_amount_yi REAL,
first_15m_l2_main_net_ratio REAL,
first_15m_l2_super_net_ratio REAL,
first_15m_oib_ratio REAL,
first_15m_cvd_ratio REAL,
first_15m_book_imbalance_avg REAL,

confirm_0945_price REAL,
confirm_0945_allowed INTEGER,
confirm_block_reason TEXT,

has_entry_5m INTEGER NOT NULL DEFAULT 0,
has_order_5m INTEGER NOT NULL DEFAULT 0,
has_book_5m INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(symbol, signal_date, entry_date, feature_version)
```

点时说明：

- 该表使用 `entry_date` 开盘后数据。
- 只能用于“开盘后确认买入”研究和回测。
- 不能作为前一晚 `signal_date` 候选模型输入。

## 表 8：`model_feature_exit_daily_v1`

粒度：

```text
symbol + entry_date + holding_date
```

用途：

- 训练盘后持仓/卖点模型。
- 生产时输入真实或模拟持仓，输出 `hold / watch_risk / sell_next_open`。

建议字段：

```sql
symbol TEXT NOT NULL,
entry_date TEXT NOT NULL,
holding_date TEXT NOT NULL,
feature_version TEXT NOT NULL,
holding_day INTEGER NOT NULL,

entry_price REAL NOT NULL,
close REAL,
high REAL,
low REAL,
unrealized_close_return_pct REAL,
max_runup_so_far_pct REAL,
max_drawdown_so_far_pct REAL,
drawdown_from_peak_pct REAL,

day_return_pct REAL,
intraday_close_position REAL,
last_30m_return_pct REAL,
last_30m_l2_main_net_ratio REAL,
last_30m_oib_ratio REAL,
l2_main_net_ratio REAL,
l2_super_net_ratio REAL,
oib_ratio REAL,
cvd_ratio REAL,
buy_support_ratio REAL,
sell_pressure_ratio REAL,
close_book_imbalance_ratio REAL,
thin_book_bar_ratio REAL,

touch_limit_up INTEGER,
is_limit_up_close INTEGER,
broken_limit_up INTEGER,
is_limit_down_close INTEGER,
limit_state_label TEXT,

hot_theme_best_rank INTEGER,
hot_theme_is_climax_hot INTEGER,
hot_theme_is_fading INTEGER,
csi1000_above_ma20 INTEGER,
market_advancer_ratio REAL,
market_broken_limit_up_ratio REAL,

has_order_daily INTEGER NOT NULL DEFAULT 0,
has_book_daily INTEGER NOT NULL DEFAULT 0,
has_intraday_shape INTEGER NOT NULL DEFAULT 0,
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(symbol, entry_date, holding_date, feature_version)
```

生成范围：

- 不建议为全市场所有可能 entry_date 直接生成 22 日路径，体积会膨胀。
- P1 阶段先为模型候选池、规则候选池、训练样本池生成。
- 后续真实持仓生产动作按 positions 输入即时生成。

## 表 9：`model_label_forward_return_v1`

粒度：

```text
symbol + trade_date + horizon_days
```

用途：

- 训练标签。
- 严禁生产候选读取。

建议字段：

```sql
symbol TEXT NOT NULL,
trade_date TEXT NOT NULL,
entry_date TEXT,
horizon_days INTEGER NOT NULL,
feature_version TEXT NOT NULL,

signal_close REAL,
entry_open REAL,
entry_gap_pct REAL,
entry_buyable INTEGER,
entry_block_reason TEXT,

max_high REAL,
min_low REAL,
exit_close REAL,
max_runup_pct REAL,
max_drawdown_pct REAL,
close_return_pct REAL,
hit_5pct INTEGER,
hit_8pct INTEGER,
hit_10pct INTEGER,
hit_15pct INTEGER,
hit_20pct INTEGER,
first_hit_8pct_day INTEGER,
first_hit_15pct_day INTEGER,
worst_before_first_hit_15pct REAL,

created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
PRIMARY KEY(symbol, trade_date, horizon_days, feature_version)
```

支持 horizon：

```text
3, 5, 10, 22
```

标签口径：

- 信号日：`trade_date` 盘后。
- 入场日：下一个交易日。
- 入场价：默认 `entry_open`，后续买点模型可以替换为确认价。
- 买不到：次日一字涨停或开盘接近涨停时 `entry_buyable=0`。
- `max_runup_pct = (未来窗口最高价 / entry_price - 1) * 100`。
- `max_drawdown_pct = (未来窗口最低价 / entry_price - 1) * 100`。

## 需要从 atomic 派生但不要新增到 atomic 的字段

这些字段应进入模型特征库，不要加回 atomic 原子层：

| 字段方向 | 原因 |
|---|---|
| 日内资金曲线斜率 | 模型特征，不是事实 |
| front/back loaded flow | 模型解释特征 |
| late day distribution | 策略/模型语义 |
| market regime | 市场环境层 |
| candidate label | 训练标签，含未来 |
| entry confirmation | 买点研究，含次日数据 |
| exit path features | 持仓训练路径 |

atomic 只保留事实；模型特征库保留模型需要的可重复派生结果。

## 中证1000市场环境要求

用户明确要求加入：

```text
中证1000是否在20日线以上
```

实现要求：

1. 建立或复用指数日线表。
2. 至少覆盖模型训练窗口。
3. `model_market_state_daily_v1` 必须产出：

```text
csi1000_close
csi1000_ma20
csi1000_above_ma20
csi1000_dist_ma20_pct
csi1000_ma20_slope_5d_pct
```

4. `model_feature_daily_v1` 必须 join：

```text
csi1000_above_ma20
csi1000_dist_ma20_pct
```

5. 验收时，20日 warmup 后这些字段不允许为空。

## market_heat 要求

当前问题：

- `fine_theme_heat_daily_v2` 覆盖到 `2026-05-13`。
- 如果训练窗口扩到 `2024-09`，现有 heat 数据不覆盖 `2024-09 ~ 2024-12`。

要求：

1. 如果训练窗口从 `2024-09` 开始，market_heat 需要同步回建。
2. 如果暂时不能回建，特征库必须显式写：

```text
has_heat = 0
```

3. 不能把缺失 heat 默默填成 “没有热点”。
4. 热点特征优先读 `fine_theme_heat_daily_v2`，不足时回退 `fine_theme_heat_daily`。

## coverage 要求

所有模型主表必须有 coverage flags。

最低 flags：

```text
has_trade_daily
has_trade_5m
has_order_daily
has_order_5m
has_book_daily
has_book_5m
has_limit_daily
has_heat
has_market_state
```

规则：

- 缺数据时 flag = 0。
- 数值字段可为空或 0，但模型训练必须看到 flag。
- 不允许把 `2025-01 ~ 2026-02` 的 order/book 缺失当成真实 0。

## 小样本验证要求

正式大批量跑之前，先做小样本。

建议窗口：

```text
2024-10-08 ~ 2024-10-14
2026-02-02 ~ 2026-02-06
2026-03-02 ~ 2026-03-06
```

说明：

- 2024-10 用于验证新增历史 full L2。
- 2026-02 用于验证新买数据和 2026-03 之间的连续性。
- 2026-03 用于对照已有完整 order/book 口径。

如果某些日期不是交易日，构建脚本应自动按实际交易日处理。

## 验收 SQL

### 1. 表存在

```sql
SELECT name
FROM sqlite_master
WHERE type='table'
ORDER BY name;
```

必须包含：

```text
model_feature_build_runs
model_feature_manifest
model_market_index_daily
model_market_state_daily_v1
model_feature_daily_v1
model_feature_intraday_shape_v1
model_label_forward_return_v1
```

### 2. 覆盖范围

```sql
SELECT
  MIN(trade_date),
  MAX(trade_date),
  COUNT(*),
  COUNT(DISTINCT trade_date)
FROM model_feature_daily_v1
WHERE feature_version = 'v1';
```

小样本必须覆盖请求区间内的实际交易日。

### 3. 中证1000字段

```sql
SELECT
  trade_date,
  csi1000_close,
  csi1000_ma20,
  csi1000_above_ma20,
  csi1000_dist_ma20_pct
FROM model_market_state_daily_v1
WHERE trade_date >= '2026-03-02'
ORDER BY trade_date
LIMIT 30;
```

验收：

- warmup 后 `csi1000_ma20` 非空。
- `csi1000_above_ma20` 只能是 0 或 1。

### 4. order/book coverage

```sql
SELECT
  trade_date,
  COUNT(*) AS rows,
  SUM(has_order_daily) AS order_daily_rows,
  SUM(has_book_daily) AS book_daily_rows,
  SUM(has_order_5m) AS order_5m_rows,
  SUM(has_book_5m) AS book_5m_rows
FROM model_feature_daily_v1
GROUP BY trade_date
ORDER BY trade_date;
```

验收：

- 2026-03 样本应有大量 order/book coverage。
- 2026-02 在新买数据跑完后也应有 coverage。
- 如果 2024-10 小样本已跑 full L2，也应有 coverage。

### 5. 不依赖 `atomic_limit_state_5m`

代码检查：

```bash
rg -n "atomic_limit_state_5m|limit_state_5m" backend scripts docs
```

验收：

- 新增构建脚本不得引用 `atomic_limit_state_5m`。
- 允许历史文档和 legacy schema 出现，但新增实现不允许依赖。

### 6. 不硬编码旧 full reverse DB

代码检查：

```bash
rg -n "market_atomic_mainboard_full_reverse.db" backend/scripts backend/app docs/selection
```

验收：

- 新增模型特征构建脚本不得硬编码该路径。
- 应使用环境变量、显式参数，或 `candidate_atomic_db_paths()`。

### 7. 标签表不混入特征表

```sql
PRAGMA table_info(model_feature_daily_v1);
```

验收：

- 不允许出现 `future_*`。
- 不允许出现 `max_runup_*`。
- 不允许出现 `hit_15pct`。
- 这些只能在 `model_label_forward_return_v1`。

## 交付物要求

数据库实现会话完成 P0 后，至少交付：

```text
backend/scripts/sql/model_feature_store_schema.sql
backend/scripts/build_model_feature_store.py
backend/scripts/validate_model_feature_store.py
docs/selection/model_feature_store_implementation_notes.md
```

本地数据产物：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
```

验证报告：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_YYYYMMDD.json
```

报告必须包含：

- 构建窗口。
- 各表行数。
- coverage 摘要。
- 中证1000字段完整性。
- order/book 覆盖检查。
- 是否发现缺失交易日。
- 是否发现 `atomic_limit_state_5m` 依赖。

## 后续训练会话如何使用

模型训练会话在特征层验收通过后，执行：

1. 读取 `model_feature_daily_v1`。
2. join `model_feature_intraday_shape_v1`。
3. join `model_label_forward_return_v1`。
4. 对比：
   - 不含 order/book。
   - 含 order/book。
   - 加市场状态闸门。
   - 22日机会模型。
   - 5/10日短周期模型。
   - 持仓/卖点模型。

训练产物版本建议：

```text
source_id: spark_opportunity_selector
source_name: 星火机会模型 1.1
source_version: 1.1
artifact_version: opportunity_discovery_full_l2_compact_v1_1
```

正式冻结前，不要把 v1.1 写入 `active`；先以 `watch_only` 或研究状态回测。

## 给实现会话的短指令

可以直接把下面这段给数据库实现会话：

```text
请从 main 新开 worktree/分支 codex/model-feature-store-v1。
按 docs/selection/model_feature_store_requirements_v1_2026-05-17.md 实现模型特征库。
不要恢复 atomic_limit_state_5m。
不要硬编码 market_atomic_mainboard_full_reverse.db。
不要改每日 postclose 主流程。
先实现 schema + 小样本构建 + 验证报告。
小样本窗口：2024-10-08~2024-10-14、2026-02-02~2026-02-06、2026-03-02~2026-03-06。
完成后提交分支，并把 model_feature_store.db 的表结构、行数、coverage 和验证报告发回。
```
