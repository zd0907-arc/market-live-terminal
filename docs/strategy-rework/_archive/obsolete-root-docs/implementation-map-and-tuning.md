# 三层方案实现地图 + 调参切入点

## 1. 先说现状

当前项目里其实有两套东西：

### A. 旧前端已接入链路（v1）

- 后端入口：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/app/services/selection_research.py`
- 前端页面：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/src/components/selection/SelectionResearchPage.tsx`
- 右侧复盘：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/src/components/selection/SelectionDecisionPanel.tsx`

它的核心是 3 个分数：

- `stealth_score`
- `breakout_score`
- `distribution_score`

### B. 当前在做的三层重构实验链路（v2）

- 后端入口：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/app/services/selection_strategy_v2.py`
- CLI：`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/scripts/run_selection_strategy_v2.py`

它的核心是：

```text
Layer 1 量化候选
→ Layer 2 公司/事件研究卡片
→ Layer 3 状态机 + 进出场回放 + 区间回测
```

当前三层方案主要还在后端实验层，前端还没有接到 v2。

---

## 2. 数据源从哪里来

### 2.1 v2 量化主数据

#### 表 1：`atomic_trade_daily`

来源文件定义：

- `/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/scripts/sql/atomic_fact_p0_schema.sql`

核心字段：

- `open/high/low/close`
- `total_amount`
- `total_volume`
- `trade_count`
- `l1_main_net_amount`
- `l2_main_net_amount`
- `l1_super_net_amount`
- `l2_super_net_amount`
- `l1_buy_ratio/l1_sell_ratio`
- `l2_buy_ratio/l2_sell_ratio`
- `positive_l2_net_bar_count`
- `negative_l2_net_bar_count`

字段含义：

- `l1_*`：基于 L1 口径归集的大单/超大单结果
- `l2_*`：基于逐笔成交/L2 还原的大单/超大单结果
- `*_net_amount = buy_amount - sell_amount`
- `positive_l2_net_bar_count`：日内 5m/子区间里净流入为正的桶数

#### 表 2：`atomic_order_daily`

核心字段：

- `add_buy_amount`
- `add_sell_amount`
- `cancel_buy_amount`
- `cancel_sell_amount`
- `cvd_delta_amount`
- `oib_delta_amount`
- `buy_support_ratio`
- `sell_pressure_ratio`
- `order_event_count`

字段含义：

- `add_buy_amount`：新增买单金额
- `add_sell_amount`：新增卖单金额
- `cancel_buy_amount`：撤买金额
- `cancel_sell_amount`：撤卖金额
- `cvd_delta_amount`：主动成交差额
- `oib_delta_amount`：订单流不平衡差额
- `buy_support_ratio`：买盘承接强度
- `sell_pressure_ratio`：卖盘压单强度

#### Layer 2 研究补充表

- `stock_universe_meta`
- `stock_events`
- `sentiment_events`
- `sentiment_daily_scores`

当前只做基础卡片，不参与量化买卖。

---

## 3. v2 Layer 1 现在怎么算

### 3.1 基础衍生指标

实现位置：

- `/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/app/services/selection_strategy_v2.py`
- 函数：`compute_v2_metrics`

核心公式：

```text
return_1d_pct = (close / prev_close - 1) * 100
return_3d_pct = (close / close.shift(3) - 1) * 100
return_5d_pct = (close / close.shift(5) - 1) * 100
return_10d_pct = (close / close.shift(10) - 1) * 100
return_20d_pct = (close / close.shift(20) - 1) * 100

amount_anomaly_20d = total_amount / MA20(total_amount)
volume_anomaly_20d = total_volume / MA20(total_volume)
trade_count_anomaly_20d = trade_count / MA20(trade_count)

breakout_vs_prev20_high_pct = (close / prev20_high - 1) * 100
max_drawdown_from_20d_high_pct = (close / recent20_high - 1) * 100

l2_main_net_ratio = l2_main_net_amount / total_amount
l2_super_net_ratio = l2_super_net_amount / total_amount
l1_l2_divergence = l2_main_net_amount - l1_main_net_amount

main_net_3d = rolling_sum(l2_main_net_amount, 3d)
main_net_5d = rolling_sum(l2_main_net_amount, 5d)

active_buy_strength = l2_buy_ratio - l2_sell_ratio
positive_l2_bar_ratio = positive_l2_net_bar_count / (positive_l2_net_bar_count + negative_l2_net_bar_count)

order_imbalance_ratio = oib_delta_amount / total_amount
cvd_ratio = cvd_delta_amount / total_amount

add_buy_ratio = add_buy_amount / total_amount
add_sell_ratio = add_sell_amount / total_amount
cancel_buy_ratio = cancel_buy_amount / total_amount
cancel_sell_ratio = cancel_sell_amount / total_amount

support_pressure_spread = buy_support_ratio - sell_pressure_ratio
```

### 3.2 候选类型

当前候选类型：

- `accumulation_candidate`
- `launch_candidate`
- `event_spike_candidate`
- `shakeout_repair_candidate`
- `second_wave_candidate`
- `distribution_watch_candidate`

这些不是靠单一字段，而是靠组合阈值。

---

## 4. v2 新增的“意图识别层”怎么算

这是当前调策略最重要的地方。

实现位置：

- `selection_strategy_v2.py`
- 函数：`_compute_intent_profile`

### 4.1 五个组合分数

#### `accumulation_score`

大意：

```text
近 5 日主力净流入
+ 正流入 bar 占比
+ 承接强于卖压
+ OIB 转强
+ CVD 转强
```

它更像回答：

```text
这票是不是在被慢慢吃货？
```

#### `attack_score`

大意：

```text
单日涨幅
+ 成交额异常
+ 平台突破
+ 主动买强度
+ L2 主力净流入占比
+ L2 超大单净流入占比
```

它更像回答：

```text
今天是不是主力在主动往上打？
```

#### `distribution_score`

大意：

```text
L2 主力净流出
+ 主动买转弱
+ 承接弱于卖压
+ 撤买放大
+ 加卖放大
+ OIB 转弱
+ CVD 转弱
```

它更像回答：

```text
今天是不是钱在往外跑？
```

#### `washout_score`

大意：

```text
单日大跌
+ 成交额放大
+ 但 L2 资金未明显恶化
+ 承接没有塌
+ 撤卖偏多
```

它更像回答：

```text
今天像不像洗盘，而不是出货？
```

#### `repair_score`

大意：

```text
前 3 日先出现急跌
+ 今天资金回补覆盖前面流出
+ 主动买回升
+ 承接修复
+ 量能恢复
```

它更像回答：

```text
洗盘之后，今天是不是在修复？
```

### 4.2 意图标签

在五个分数基础上再归类为：

- `accumulation`
- `launch_attack`
- `follow_through_attack`
- `washout`
- `shakeout_repair`
- `distribution`
- `panic_distribution`
- `pull_up_distribution`
- `sharp_rise_unclear`
- `sharp_drop_unclear`

这一步的意义是：

```text
不是直接说“买/卖”，而是先回答“主力今天到底在干嘛”
```

---

## 5. v2 Layer 3 现在怎么算

### 5.1 状态机

核心函数：

- `replay_symbol_v2`
- `replay_trade_date_v2`
- `backtest_range_v2`

当前状态：

- `watch`
- `accumulating`
- `event_spike`
- `shakeout`
- `shakeout_repair`
- `launching`
- `entry_signal`
- `entered`
- `holding`
- `distribution_warning`
- `exit_signal`
- `exit`
- `entry_blocked_limit_up`
- `exit_blocked_limit_down`

### 5.2 进场逻辑

不是单纯看 `launch_candidate`，而是：

```text
intent_profile.entry_signal = true
或状态落在 launching / event_spike / shakeout_repair
```

默认执行口径：

```text
信号日后下一交易日开盘买
```

### 5.3 出场逻辑

当前是三条主线：

```text
1. stop_loss
2. distribution_warning 连续确认
3. panic_distribution_exit
```

其中最重要的是：

```text
panic_distribution_exit
```

它代表：

```text
不仅跌了，而且组合指标判断更像主力在逃，而不是普通洗盘
```

---

## 6. 当前最应该怎么调

不是每个字段都乱调。

应该分 3 层调：

### 第一层：先调“意图分类阈值”

这是最大抓手。

优先参数：

- `accumulation_score_min`
- `attack_score_min`
- `repair_score_min`
- `distribution_score_warn`
- `panic_distribution_score_exit`

逻辑影响：

- `attack_score_min` 提高：
  - 进场更少
  - 更保守
  - 一日游会少，但可能错过早期启动

- `distribution_score_warn` 提高：
  - 出货预警更慢
  - 更能拿住趋势票
  - 但真出货时可能回撤更大

- `panic_distribution_score_exit` 提高：
  - 只在很强的逃跑信号才卖
  - 解决“过早卖飞”
  - 但也更容易在真出货时晚一步

- `repair_score_min` 提高：
  - 洗盘修复必须更强才重回可买
  - 能减少假修复
  - 但会错过一些 V 形强修

### 第二层：再调“分数构成权重”

这层不要一开始就动。

比如：

- `distribution_score` 里到底是 `cancel_buy_ratio` 权重大，还是 `l2_main_net_ratio` 权重大
- `washout_score` 里到底更看重承接，还是更看重大跌后的资金没跑

这层是“微调逻辑结构”。

### 第三层：最后再调基础指标窗口

比如：

- 3 日还是 5 日
- 20 日还是 30 日
- 平台突破看前 20 日还是前 15 日

这层最细，应该最后动。

---

## 7. 我建议的调参顺序

### Step 1

先固定基础字段公式不动，只调 5 个关键阈值：

- `attack_score_min`
- `distribution_score_warn`
- `panic_distribution_score_exit`
- `repair_score_min`
- `distribution_confirm_days`

### Step 2

用利通 + 反例票做案例复盘：

- 哪天识别成启动
- 哪天识别成洗盘
- 哪天识别成出货
- 是否卖飞
- 是否卖晚

### Step 3

只有在发现“方向判断错了”时，才去改分数权重。

### Step 4

最后再改底层窗口和更细的字段组合。

---

## 8. 现在怎么把结果给你看

当前还没有把 v2 接到前端。

所以现在主要有 3 种方式：

### 方式 A：对话里直接汇总

适合快速看一只票某段时间的结论。

### 方式 B：CLI 跑 JSON

命令：

```bash
python3 backend/scripts/run_selection_strategy_v2.py day-replay ...
python3 backend/scripts/run_selection_strategy_v2.py symbol-replay ...
python3 backend/scripts/run_selection_strategy_v2.py range-backtest ...
python3 backend/scripts/run_selection_strategy_v2.py research-card ...
```

适合看完整明细。

### 方式 C：我把结果落成文档 / JSON 文件

适合做案例复盘和留档。

如果你要看利通最近几个月，我现在最合适的方式是：

```text
symbol-replay + day-replay + range-backtest
→ 产出 JSON
→ 我再给你整理成一份案例文档
```

---

## 9. 2026-04-26 当前前端接入状态

v2 已经接入选股页：

- 左侧 `V2 实验验证`：调用 `/api/selection/candidates?strategy=v2&limit=10`。
- 后端内部先扫描不少于 120 个候选，再按 `layer3_live_lifecycle_score` 排序，只返回前 10。
- 左侧只展示：`排序分 / 生命周期阶段 / 动作`，详细解释放右侧。
- 右侧波段复盘：`30/60/90/120/180天` 按钮固定以系统最新可用交易日为结束日往前回推，并默认展示完整区间。

注意：

- `layer3_live_lifecycle_score` 不使用未来收益。
- `layer3_replay_validation` 只保留为历史验证思路，不作为实盘排序。

## 10. v2 策略评估接口

新增接口：

```text
GET /api/selection/v2/evaluate?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&top_n=10
```

评估逻辑：

```text
对区间内每个交易日：
1. 用当前 v2 实时生命周期排序选出 TopN。
2. 对每只候选从信号日往后回放。
3. 次日开盘入场。
4. 根据出货/止损/最大持有窗口找出场点。
5. 记录每笔交易收益。
6. 汇总整体胜率、平均收益、中位收益、最大/最小收益、平均持有天数。
```

当前默认参数入口：

- `build_selection_v2_page_params()`
- `attack_score_min = 65`
- `repair_score_min = 60`
- `distribution_score_warn = 70`
- `panic_distribution_score_exit = 80`
- `entry_attack_cvd_floor = -0.08`
- `entry_return_20d_cap = 80`

当前出场参数仍来自 `SelectionV2Params`：

- `stop_loss_pct = -8`
- `max_holding_days = 40`
- `distribution_confirm_days = 2`
- `panic_distribution_score_exit = 80`

2026-04-26 快速验证样本：

```text
区间：2026-03-25 ~ 2026-03-27
TopN：10
交易数：26
胜率：26.92%
平均收益：-1.77%
中位收益：-8.18%
最大收益：52.12%
最小收益：-13.24%
平均持有：6.58 天
```

结论：

```text
当前参数组合不是可直接实盘的策略。
它已经具备了可调参、可回测、可逐票追踪收益的闭环。
下一步应该基于这个评估接口调入场过滤和出场条件，而不是围绕单个案例调排名。
```
