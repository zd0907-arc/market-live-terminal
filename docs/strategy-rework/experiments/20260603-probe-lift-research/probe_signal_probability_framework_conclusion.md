# 试盘信号概率框架结论

## 结论

- 这一阶段已经不只是“研究试盘现象”，而是正式做成了一个 `试盘 -> 特征 -> 概率` 的框架。
- 不是看到试盘就直接买，而是：
  1. 先识别试盘
  2. 再看同日特征和试盘后确认特征
  3. 最后输出后续首板或冲高的条件概率

当前先做了两条概率线：

1. `首板概率线`
   - 目标：试盘后 `20` 日内是否会出现涨停收盘
2. `趋势概率线`
   - 目标：试盘后 `20` 日内最高涨幅是否能达到 `+20%`

## 1. 样本与验证方式

- 试盘样本总数：`858`
- 训练区间：`2024-09-02 ~ 2025-09-30`
- 验证区间：`2025-10-01 ~ 2025-12-31`

这个切法的目的不是追求多复杂的模型，而是避免只做全样本回看。

## 2. 当前模型效果

### 首板概率线

- 验证集 AUC：`0.6033`
- 验证集基准命中率：`40.86%`

这说明：

- 试盘后的首板本身就不算很稀有；
- 用现有特征可以做出一定区分，但区分度还不算强；
- 这条线更适合做“候选优先级”，暂时还不适合单独强决策。

### 趋势概率线

- 验证集 AUC：`0.7042`
- 验证集基准命中率：`23.66%`

这说明：

- 对“20 日内能否走出一波明显冲高”，试盘后的特征解释力明显比首板更强；
- 也就是说，试盘更适合先拿来判断“后面会不会有一波”，再进一步细分是不是会板。

## 3. 哪些特征最重要

### 首板概率线前列特征

按当前线性原型的系数强度看，比较靠前的是：

- `d3_oib_ratio`
- `hot_theme_score`
- `d1_l2_super_net_ratio`
- `hot_theme_best_rank`
- `day_gap_pct`

业务解释：

- 试盘后第 `3` 日订单失衡是否还强，很关键；
- 热点位置越好，后面被正式点火的概率越高；
- 试盘后第 `1` 日超大单是否继续流入，也有明显区分度；
- 跳空位置也重要，过于极端的缺口并不一定是好事。

### 趋势概率线前列特征

比较靠前的是：

- `d3_oib_ratio`
- `amount_vs_day_median`
- `hot_theme_score`
- `d1_oib_ratio`
- `price_position_20d`

业务解释：

- 趋势线里，试盘后第 `1~3` 日订单失衡延续，比试盘当天更重要；
- 热点强度仍然是核心特征；
- 价格所处位置也重要，太高、太极端的位置并不占优；
- 单纯放量过猛，并不天然等于后面更容易走趋势。

## 4. 概率框架告诉我们的事

### 4.1 试盘当天重要，但试盘后的确认更重要

当前结果最明确的一点是：

- 真正有区分度的，不只是试盘当天 `OIB` 强不强；
- 而是试盘后 `1~3` 天，资金有没有继续留下来。

这和你的业务理解是对齐的：

- 试盘只是一个动作；
- 真正关键是，试完以后主导资金是否继续做确认。

### 4.2 热点位置是必须保留的一层

不管是首板还是趋势：

- `hot_theme_score`
- `hot_theme_best_rank`

都排在比较靠前的位置。

说明：

- 只研究试盘本身还不够；
- 试盘如果叠加热点回流或热点前排，后续成功率会明显不同。

### 4.3 趋势线比首板线更容易做出解释力

当前 AUC 对比：

- 首板：`0.6033`
- 趋势：`0.7042`

这说明：

- 试盘信号本身，更像“后面可能会有一波”的前置信号；
- 它对趋势启动的解释力，强于对首板点火的解释力。

## 5. 现阶段该怎么用

### 首板线

更适合当：

- 首板候选优先级
- 盘后复盘排序
- “值得盯一周”的跟踪池

补充：

- 这一条线已经完成了一轮只基于库内数据的强化，增强版验证 AUC 已提升到 `0.7206`；
- 当前应采用增强版，而不是停留在最初的 17 个特征基线。

不适合直接当：

- 单一买入触发器

### 趋势线

更适合当：

- 试盘后趋势候选优先级
- 短线波段观察池
- 题材内“被资金盯上但未正式点火”的中间状态提示

补充：

- 趋势线也试过直接堆更多库内特征，AUC 虽然略有上升，但高分池的真实收益与回撤体验反而变差；
- 所以趋势线当前更合理的做法，是保留原主模型，再叠加 `D3` 资金确认、位置中间带这类确认型过滤。

## 6. 当前正式产物

- [probe_feature_dictionary.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_feature_dictionary.csv)
- [probe_limitup_target_definition.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_limitup_target_definition.md)
- [probe_trend_target_definition.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_trend_target_definition.md)
- [probe_limitup_probability_table.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_limitup_probability_table.csv)
- [probe_trend_probability_table.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_trend_probability_table.csv)
- [probe_limitup_feature_importance.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_limitup_feature_importance.csv)
- [probe_trend_feature_importance.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_trend_feature_importance.csv)
- [probe_limitup_candidate_pool.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_limitup_candidate_pool.csv)
- [probe_trend_candidate_pool.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_trend_candidate_pool.csv)
- [probe_limitup_success_failure_review.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_limitup_success_failure_review.csv)
- [probe_trend_success_failure_review.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_trend_success_failure_review.csv)
- [probe_signal_scoring_blueprint.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_scoring_blueprint.md)
- [probe_signal_probability_summary.json](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_probability_summary.json)

## 7. 还没做完的部分

这一版还不够终局，但下一阶段的优先级已经更明确：

1. 先强化现有数据库里的确认层
   - `D1/D3` 的 OIB、超大单、主力净流入延续
2. 先强化盘口结构层
   - 托举、抛压、撤卖、盘口失衡
3. 先强化热点与位置层
   - 热点前排强度、20 日位置、距前高距离、是否过于极端放量
4. 再做数值稳健化
   - 更稳的分箱、截尾和校准

现阶段不把事件窗口作为下一轮优先项，原因不是它没用，而是现有库内数据已经足够继续把这套框架往前推一大步。

但对当前阶段来说，已经足够回答你的核心业务问题：

- 试盘不是直接买点；
- 试盘后的资金确认、热点位置和盘口延续，确实能显著改变后面首板或冲高的概率；
- 后面实盘演练时，可以先拿这套概率框架作为解释器，而不是只看一个试盘信号。
