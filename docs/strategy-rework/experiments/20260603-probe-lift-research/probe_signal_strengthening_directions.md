# 试盘信号接入盘后的价值与强化方向

## 结论

- 这套东西现在最有价值的接法，不是直接做“试盘当晚买入器”，而是先接成盘后的两层候选池：
  - `趋势高分池`：主用，负责筛“后面更可能走出一波”的票。
  - `首板高分池`：辅用，负责筛“后面更可能被点成首板”的票。
- 现在真正已经表现出明显交易价值的是 `趋势高分池`，不是 `首板高分池`。
- 后续强化空间，主要不在事件窗口，而在现有数据库已经有的四层数据：
  - `试盘后 1~3 日资金确认`
  - `盘口承接 / 撤卖结构`
  - `热点强度与热点位置`
  - `股价位置与是否过于极端`

## 1. 接进盘后后，你到底能得到什么

这里的口径统一按：

- 先识别到试盘；
- 再用现有概率框架给分；
- 最后看验证集 `2025-10-01 ~ 2025-12-31` 里，次日开盘买入后的真实路径。

### 趋势高分池

- 样本：`31`
- `20` 日内走到 `+20%` 的比例：`45.2%`
- `40` 日内走到 `+30%` 的比例：`48.4%`
- 次日开盘买入后：
  - `1` 日胜率：`64.5%`
  - `3` 日胜率：`74.2%`
  - `5` 日胜率：`83.9%`
  - `5` 日平均收益：`+10.34%`
  - `10` 日平均收益：`+13.91%`
  - `5` 日内最低打到 `-5%` 的概率：`19.4%`
  - `10` 日内最高摸到 `+5%` 的概率：`90.3%`

业务解释：

- 如果把它接进盘后，它最直接的价值不是“明天一定涨停”，而是帮你把“后面可能走出一波”的票提前筛出来。
- 这组票的短线体验已经明显强于普通试盘样本，尤其是 `5` 日胜率、`5~10` 日平均收益、以及 `10` 日内给冲高空间的概率。

### 首板高分池

- 样本：`31`
- `20` 日内出现涨停收盘的比例：`54.8%`
- 首板后继续走成 `2/3` 板延续的比例：`16.1%`
- 次日开盘买入后：
  - `1` 日胜率：`61.3%`
  - `3` 日胜率：`64.5%`
  - `5` 日胜率：`61.3%`
  - `5` 日平均收益：`+6.88%`
  - `10` 日平均收益：`+7.56%`
  - `5` 日内最低打到 `-5%` 的概率：`38.7%`
  - `10` 日内最高摸到 `+5%` 的概率：`83.9%`

业务解释：

- 它确实能把首板候选筛得比低分样本好很多；
- 但这条线的回撤还是更粗，不能把它理解成“高分就能放心直接上”。
- 所以它更适合做 `首板优先级排序`，不适合先拿来当单一硬买点。

### 低分池对比

- `趋势低分池` 次日开盘买后，`5` 日平均收益是 `-3.74%`，`5` 日内打到 `-5%` 的概率是 `64.5%`。
- `首板低分池` 次日开盘买后，`5` 日平均收益是 `-1.42%`，`5` 日内打到 `-5%` 的概率是 `51.6%`。

这说明这套框架至少已经能做一件很实用的事：

- 把“看起来像试盘，但后面大概率不舒服”的票先往后排。

## 2. 它现在能不能直接给赚钱策略

结论是：

- `趋势线` 已经够资格进入盘后演练；
- `首板线` 还不够资格单独做强交易策略。

更合理的用法是：

1. `T 日盘后`
   - 先识别试盘，生成初筛池。
2. `T+1 / T+3 盘后`
   - 再看资金确认、盘口承接、热点位置有没有跟上。
3. 最后输出两类结果
   - `趋势候选`
   - `首板候选`

也就是说，这套东西当前更像：

- `试盘 -> 确认 -> 概率 -> 候选池`

而不是：

- `试盘 -> 立刻买`

## 3. 继续强化，优先往哪几层做

### 方向 A：强化“试盘后确认”

这是当前空间最大的一层。

证据最明显的是 `D3` 确认：

- 在 `首板高分池` 里，`D3` 资金确认仍为正的子集：
  - 样本 `8`
  - 首板命中率 `87.5%`
  - `5` 日平均收益 `+22.59%`
- 在 `趋势高分池` 里，`D3` 资金确认仍为正的子集：
  - 样本 `10`
  - `20` 日走到 `+20%` 的比例 `70.0%`
  - `5` 日平均收益 `+22.25%`

这说明：

- 真正决定“试盘后会不会成”的，不只是试盘当天，而是试完后 `1~3` 天主导资金有没有继续留下来。

下一步最值得强化的字段：

- `d1_oib_ratio`
- `d3_oib_ratio`
- `d1_l2_super_net_ratio`
- `d3_l2_super_net_ratio`
- `d1_l2_main_net_ratio`
- `d3_l2_main_net_ratio`

### 方向 B：强化“盘口承接 / 撤卖结构”

这层更像压回撤、改善买入体验。

当前已经看到一些方向性信号：

- `趋势高分池` 里，撤卖更强的子集：
  - `10` 日内摸到 `+5%` 的比例 `100%`
  - `5` 日平均收益 `+13.10%`
- `首板高分池` 里，托举减抛压差更强的子集：
  - 首板命中率 `61.5%`
  - `5` 日平均收益 `+9.82%`

这说明：

- 盘口不只是辅助解释字段，后面大概率可以作为第二层过滤器；
- 它更可能帮你解决的是“明明试盘对了，但买进去体验差”的问题。

优先字段：

- `support_pressure_spread`
- `buy_support_ratio`
- `cancel_sell_ratio`
- `close_book_imbalance_ratio`
- `close_bid_ask_amount_ratio`

### 方向 C：强化“热点强度与热点位置”

这一层当前结论是：

- 热点确实重要；
- 但更像一个底层分数，不像一个单独一刀切规则。

原因是：

- 在当前模型里，`hot_theme_score`、`hot_theme_best_rank` 一直排在前列；
- 但到了高分池内部，单独再切一个“热点前十”，提升没有 `D1/D3` 资金确认那么大。

这说明：

- 热点应该保留；
- 但更适合放在综合打分里，而不是简单写成“热点前十就买”。

优先字段：

- `hot_theme_score`
- `hot_theme_best_rank`
- `hot_theme_is_top10`
- `hot_theme_is_continuing_hot`

### 方向 D：强化“股价位置结构”

这层对 `趋势线` 很关键。

当前已经看到两个方向：

- 不是位置越高越好；
- 也不是越极端放量越好。

在 `趋势高分池` 里：

- `20` 日位置处于中间带的子集：
  - 样本 `10`
  - `20` 日走到 `+20%` 的比例 `60.0%`
  - `5` 日内打到 `-5%` 的概率只有 `10.0%`
  - `10` 日平均收益 `+22.53%`
- 放量不过于极端的子集：
  - 样本 `19`
  - `5` 日平均收益 `+10.60%`
  - `20` 日走到 `+20%` 的比例 `47.4%`

这说明：

- 更像有效试盘的，不一定是最极端那一下；
- 很多失败样本反而更容易出现在“拉得过猛、放得过大、位置过高”的状态。

优先字段：

- `price_position_20d`
- `price_position_60d`
- `drawdown_from_20d_high_pct`
- `breakout_vs_prev20_high_pct`
- `amount_vs_day_median`

## 4. 我建议的下一版盘后框架

### 第一层：初筛

- 只识别 `试盘事件`
- 输出：
  - 首次 / 第二次 / 第三次试盘
  - 试盘强度
  - 初始热点位置

### 第二层：确认

- 等 `T+1 / T+3`
- 看：
  - `OIB` 是否继续为正
  - 超大单 / 主力净流入是否延续
  - 盘口撤卖、托单是否改善
  - 热点是否还在前排

### 第三层：分池

- `趋势高分池`
  - 现在就值得优先做盘后演练
- `首板高分池`
  - 先做排序，不直接当硬买点

## 5. 当前结论里最重要的一句话

- 现在这套框架已经足够证明：`试盘` 不是无效噪音，它对后续走势是有分层能力的。
- 但最强的不是“试盘当天”，而是“试盘后 1~3 天的资金确认 + 热点位置 + 盘口承接 + 位置结构”。
- 所以下一阶段最值得做的，不是再去补事件窗口，而是先把这四层现有库内数据继续做深。

## 6. 对应产物

- [probe_signal_bucket_trade_metrics.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_bucket_trade_metrics.csv)
- [probe_signal_rule_exploration.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_rule_exploration.csv)
- [probe_signal_enriched_candidate_pool.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_enriched_candidate_pool.csv)
- [research_probe_signal_postclose_value.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/scripts/research_probe_signal_postclose_value.py)

## 7. 强化后和现状对比

这一轮已经实际跑过一版强化对比，结论不是“全部都更强”，而是要分开看：

### 首板线

- 基线验证 AUC：`0.6033`
- 强化版验证 AUC：`0.7206`
- 高分池首板命中率：`54.8% -> 61.3%`
- 高分池二三板延续率：`16.1% -> 25.8%`
- 高分池 `5` 日平均收益：`+6.88% -> +7.12%`
- 高分池 `10` 日平均收益：`+7.56% -> +11.33%`

结论：

- `首板线` 这次强化是有效的，而且提升不小，应该采用增强版。

### 趋势线

- 基线验证 AUC：`0.7042`
- 强化版验证 AUC：`0.7132`
- 但高分池 `20` 日走到 `+20%` 的比例：`45.2% -> 38.7%`
- 高分池 `5` 日平均收益：`+10.34% -> +8.35%`
- 高分池 `10` 日平均收益：`+13.91% -> +11.28%`
- 高分池 `5` 日内打到 `-5%` 的概率：`19.4% -> 25.8%`

结论：

- `趋势线` 虽然 AUC 略有上升，但高分池真实交易体验变差了。
- 这说明直接往趋势主模型里继续堆特征，当前更像过拟合，不像有效强化。

### 趋势线更合理的强化方式

- 保留原 `trend_base` 主模型；
- 再在高分池外面叠加确认过滤。

当前已经验证过比较有价值的两种过滤：

- `趋势高分池 + D3 资金确认为正`
  - `20` 日走到 `+20%` 的比例：`70.0%`
  - `5` 日平均收益：`+22.25%`
- `趋势高分池 + 20日位置中间带`
  - `20` 日走到 `+20%` 的比例：`60.0%`
  - `5` 日内打到 `-5%` 的概率：`10.0%`
  - `10` 日平均收益：`+22.53%`

这说明：

- 趋势线下一步不是换主模型，而是保留主模型，再叠加确认型二次过滤。

### 当前建议采用的版本

- `首板线`：升级到增强版 `limitup_strengthened_v2`
- `趋势线`：保留当前 `trend_base`
- `趋势聚焦池`：在 `trend_base` 高分池上，再叠加 `D3` 确认或位置过滤

补充产物：

- [probe_signal_strengthening_compare.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_compare.md)
- [probe_signal_strengthening_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_model_compare.csv)
- [probe_signal_strengthening_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_bucket_compare.csv)
- [probe_signal_strengthening_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_overlay_compare.csv)
- [research_probe_signal_strengthening_compare.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/scripts/research_probe_signal_strengthening_compare.py)
