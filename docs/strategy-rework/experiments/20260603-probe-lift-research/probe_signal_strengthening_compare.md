# 试盘信号强化对比结论

## 结论

- `首板线` 强化有效，应该升级成增强版。
- `趋势线` 直接塞更多特征并不划算，当前更优解是保留原主模型，再叠加确认型过滤。

## 1. 首板线：强化后提升多少

- 基线验证 AUC：`0.6033`
- 强化版验证 AUC：`0.7206`
- AUC 提升：`+0.1172`
- 高分池首板命中率：`54.8%` -> `61.3%`
- 高分池二三板延续率：`16.1%` -> `25.8%`
- 高分池 5 日平均收益：`+6.88%` -> `+7.12%`
- 高分池 10 日平均收益：`+7.56%` -> `+11.33%`

业务解释：

- 首板线这次强化，主要是把 `D1/D3` 资金确认、盘口撤卖、热点延续、位置结构一起纳进来，所以对“后面会不会被正式点板”这件事，区分度明显变强了。

## 2. 趋势线：强化后有没有提升

- 基线验证 AUC：`0.7042`
- 强化版验证 AUC：`0.7132`
- AUC 变化：`+0.0090`
- 但高分池 20 日走到 `+20%` 的比例：`45.2%` -> `38.7%`
- 高分池 5 日平均收益：`+10.34%` -> `+8.35%`
- 高分池 10 日平均收益：`+13.91%` -> `+11.28%`

业务解释：

- 趋势线当前已经不弱，再硬塞更多字段，AUC 虽然略涨，但高分池的真实交易体验反而变差了，这更像过拟合，不像有效强化。

## 3. 趋势线更合理的强化方式

- 不是重做主模型，而是在原趋势高分池上再叠加确认型过滤。
- `趋势高分池 + D3 资金确认为正`：样本 `10`，`20` 日走到 `+20%` 的比例 `70.0%`，`5` 日平均收益 `+22.25%`。
- `趋势高分池 + 20日位置中间带`：样本 `10`，`20` 日走到 `+20%` 的比例 `60.0%`，`5` 日内打到 `-5%` 的概率 `10.0%`，`10` 日平均收益 `+22.53%`。

这说明：

- 趋势线的下一步不是再堆更多特征，而是保留原趋势打分，外面再做一层 `确认过滤器`。

## 4. 现在建议采用的版本

- `首板线`：采用 `limitup_strengthened_v2`。
- `趋势线`：保留 `trend_base` 做主模型。
- `趋势聚焦池`：在 `trend_base` 高分池上，再看 `D3` 资金确认或位置中间带，做更激进或更稳健的二次筛选。

## 5. 对应产物

- [probe_signal_strengthening_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_model_compare.csv)
- [probe_signal_strengthening_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_bucket_compare.csv)
- [probe_signal_strengthening_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_overlay_compare.csv)