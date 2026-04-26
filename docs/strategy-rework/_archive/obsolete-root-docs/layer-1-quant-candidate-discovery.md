# Layer 1：量化候选发现层

## 1. 定位

量化候选发现层回答一个问题：

```text
今天有哪些票出现了值得研究的资金动作？
```

它不直接决定买入，只负责从全市场中筛出候选 TopN，并说明候选属于哪类资金动作。

## 2. 输入

### 2.1 标的范围

默认范围：

- A股主板/创业板中小市值优先。
- 目标市值：约 50亿-500亿。
- 暂时排除明显流动性过差、ST、退市风险、停牌等标的。

当前 `stock_universe_meta` 为空，市值过滤后续需要补数据；短期可先按已有 atomic universe 跑，再标记 `market_cap_missing`。

### 2.2 数据表

优先使用：

- `atomic_trade_daily`
- `atomic_trade_5m`
- `atomic_order_daily`
- `atomic_order_5m`
- `atomic_book_state_daily`
- `atomic_limit_state_daily`

兼容/辅助：

- `selection_feature_daily`
- `selection_signal_daily`
- `history_daily_l2`
- `history_5m_l2`
- `local_history`

## 3. 核心候选类型

候选不再只分“吸筹/启动”，而是分资金动作类型。

| 类型 | 说明 | 典型用途 |
| --- | --- | --- |
| `accumulation_candidate` | 主力/超大资金持续参与，价格尚未完全加速 | 提前观察 |
| `launch_candidate` | 放量、突破、L2主动买增强 | 次日进场候选 |
| `event_spike_candidate` | 突发放量/涨停，未必有前置吸筹 | 交给公司研究层判断事件质量 |
| `shakeout_repair_candidate` | 急跌/分歧后资金回补、承接恢复 | 洗盘后机会 |
| `second_wave_candidate` | 第一波后回调不深，资金重新转强 | 二波机会 |
| `distribution_watch_candidate` | 高位卖压增强或承接变弱 | 持仓风险提示，不作为买入候选 |

当前 v0.1 已额外输出 `intent_profile`，先对单日意图做归类：

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

## 4. 基础衍生指标

### 4.1 资金强度

建议衍生：

```text
l2_main_net_ratio = l2_main_net_amount / total_amount
l2_super_net_ratio = l2_super_net_amount / total_amount
l1_l2_divergence = l2_main_net_amount - l1_main_net_amount
main_net_3d = sum(l2_main_net_amount, 3d)
super_net_3d = sum(l2_super_net_amount, 3d)
main_net_5d = sum(l2_main_net_amount, 5d)
super_net_5d = sum(l2_super_net_amount, 5d)
```

解释：

- `l2_main_net_ratio`：主力净买相对成交额强度。
- `l2_super_net_ratio`：超大资金参与强度。
- `l1_l2_divergence`：L1表象和L2真实资金的差异，可用于发现表层弱、真实承接强的票。

### 4.2 主动买卖强度

建议衍生：

```text
active_buy_strength = l2_buy_ratio - l2_sell_ratio
active_buy_strength_3d = avg(active_buy_strength, 3d)
positive_l2_bar_ratio = positive_l2_net_bar_count / (positive_l2_net_bar_count + negative_l2_net_bar_count)
```

解释：

- 只看净流入不够，还要看主动性。
- 启动日更关注主动买增强，而不是被动承接。

### 4.3 挂撤单/承接质量

优先从 `atomic_order_daily` 使用：

```text
order_imbalance_ratio = oib_delta_amount / total_amount
cvd_ratio = cvd_delta_amount / total_amount
add_buy_ratio = add_buy_amount / total_amount
add_sell_ratio = add_sell_amount / total_amount
cancel_buy_ratio = cancel_buy_amount / total_amount
cancel_sell_ratio = cancel_sell_amount / total_amount
support_pressure_spread = buy_support_ratio - sell_pressure_ratio
```

解释：

- `oib_delta_amount`：订单流不平衡。
- `cvd_delta_amount`：主动成交累积差。
- `buy_support_ratio`：买盘支撑。
- `sell_pressure_ratio`：卖盘压力。
- `cancel_buy_amount` 放大常用于识别买盘撤退。
- `add_sell_amount` 放大常用于识别卖压堆积。

当前 v0.1 已把上述字段进一步组合成：

```text
accumulation_score
attack_score
distribution_score
washout_score
repair_score
```

目的：让“吸筹 / 启动攻击 / 洗盘 / 修复 / 出货”先有一层可解释的组合意图。

### 4.4 量能/成交密度

建议衍生：

```text
amount_ma20 = avg(total_amount, 20d)
amount_anomaly_20d = total_amount / amount_ma20
volume_ma20 = avg(total_volume, 20d)
volume_anomaly_20d = total_volume / volume_ma20
trade_count_anomaly_20d = trade_count / avg(trade_count, 20d)
```

解释：

- 游资/机构开始组织行情时，成交额异常通常先出现。
- 中小票要过滤无效小成交额信号。

### 4.5 价格结构

建议衍生：

```text
return_1d_pct
return_3d_pct
return_5d_pct
return_10d_pct
return_20d_pct
price_position_20d
price_position_60d
breakout_vs_prev20_high_pct
max_drawdown_from_20d_high_pct
ma20_trend
ma60_trend
```

解释：

- 启动需要价格确认。
- 洗盘需要回撤幅度和修复结构。
- 二波需要第一波、回调、再启动的结构。

## 5. 候选类型判定草案

以下为初始规则草案，后续必须参数化回测调优。

### 5.1 吸筹/承接候选

目标：发现资金持续参与但未完全高潮的票。

候选条件候选：

```text
main_net_5d > 0
or super_net_5d > 0
positive_l2_bar_ratio_5d > threshold
support_pressure_spread > threshold
return_20d_pct 不极端过热
amount_anomaly_20d 温和放大
```

排除：

- 连续大跌且承接失败。
- 成交额过小。
- 已高位明显出货。

### 5.2 启动候选

目标：发现可在次日重点关注的进场候选。

候选条件候选：

```text
breakout_vs_prev20_high_pct > threshold
or close 站上关键平台
amount_anomaly_20d > threshold
active_buy_strength > threshold
l2_main_net_ratio 或 l2_super_net_ratio > threshold
positive_l2_bar_ratio 当日显著偏强
```

不应硬性要求：

```text
必须先有旧 stealth_score
```

### 5.3 事件突发候选

目标：捕捉没有明显前置吸筹，但因事件突然启动的票。

候选条件候选：

```text
return_1d_pct 大幅上涨或涨停
amount_anomaly_20d 明显放大
trade_count_anomaly_20d 明显放大
l2_buy_ratio 提升
```

该类型必须交给 Layer 2 判断：

- 是否有当时可见事件。
- 事件是否足以支撑中期逻辑。
- 是一日游还是可能进入资金接力。

### 5.4 洗盘修复候选

目标：识别“不是出货，而是洗盘后资金回补”的机会。

候选结构：

```text
前 N 日出现急跌/分歧
急跌日成交额不失控或缩量
急跌后 1-3 日 l2_main_net_amount / l2_super_net_amount 回补
回补金额覆盖急跌日流出的一定比例
价格收复关键位置
support_pressure_spread 修复
```

这是利通电子式强股的重要路径。

### 5.5 二波候选

目标：识别第一波后没有走坏、资金重新进场的票。

候选结构：

```text
前一阶段存在显著涨幅
回调幅度不超过第一波涨幅的一定比例
回调中卖压没有持续失控
随后 amount_anomaly_20d 放大
active_buy_strength 转正
l2_main_net_ratio / super_net_ratio 转强
```

### 5.6 出货观察候选

目标：不是买入，而是对持仓做风险提示。

候选结构：

```text
return_20d_pct 或 return_60d_pct 已高
价格推进效率下降
l2_main_net_ratio / super_net_ratio 连续转负
add_sell_ratio 上升
cancel_buy_ratio 上升
sell_pressure_ratio 上升
buy_support_ratio 下降
冲高回落或尾盘修复失败
```

## 6. 候选评分输出

每只候选至少输出：

```json
{
  "symbol": "sh603629",
  "trade_date": "2026-03-02",
  "candidate_types": ["launch_candidate", "event_spike_candidate"],
  "intent_profile": {
    "intent_label": "launch_attack",
    "accumulation_score": 42.1,
    "attack_score": 78.5,
    "distribution_score": 12.3,
    "washout_score": 8.0,
    "repair_score": 20.4
  },
  "quant_score": 82.5,
  "funding_score": 78,
  "activity_score": 85,
  "structure_score": 80,
  "support_score": 72,
  "risk_score": 35,
  "top_reasons": [
    "成交额较20日均值显著放大",
    "L2主动买强度转正",
    "价格突破前20日平台"
  ],
  "warnings": [
    "20日涨幅已较高，需要事件层确认持续性"
  ]
}
```

## 7. 与后续层关系

- Layer 1 只负责筛候选和资金动作分类。
- Layer 2 负责解释公司和事件逻辑。
- Layer 3 负责进场、持有、退出。

Layer 1 不能单独产生最终买入结论。
