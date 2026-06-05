# A股“拉升试盘 / 测抛压”研究（第一阶段）

## 结论
- 贝因美 `sz002570` 是当前口径下很典型的“首次试盘 -> 连续试盘 -> 试盘后启动”候选。`2026-06-01 10:30` 是首次试盘，`2026-06-02 13:00` 是连续试盘，`2026-06-03` 的业务发动点在 `09:35` 首次触板，不应再算试盘。
- 第一版严格口径下，共识别试盘候选 273 次，覆盖 246 只股票；其中有 80 次在 10 个交易日内等到启动，命中率约 29.3%。
- 更适合的接法不是“直接当买点”，而是先作为星火类模型增强特征；热点优先级可以作为第二接法，但还需要补主题热度映射校验；独立候选池只建议先做 `watch_only`。

## 1. 业务定义
- 市场并没有统一的官方术语口径。中文投资百科对“试盘”的共识描述是：主导资金在正式操盘前，先做一段拉抬或打压，用来测试筹码锁定、上方抛压和市场跟风反应。
- 本研究把“拉升试盘 / 测抛压”翻译成一个更可验证的业务动作：日内先出现一段非常用力的 5 分钟急拉，但当天并没有顺势把高点继续往上推，反而回吐一部分，用来观察上方抛压和回落后的承接。
- 这里的“抛压”不是单一字段，而是一个综合结果。它更接近“急拉之后市场愿不愿意马上砸下来、主导资金能不能轻松挂住价格”。
- 把 OIB、盘口失衡和回吐幅度当成量化代理，是本研究结合订单簿微观结构文献做的推断。订单簿研究也支持：短周期价格变化和订单流失衡的关系，通常比单看成交量更稳。

## 2. 第一版识别口径
- 研究区间：`2026-03-02` 到 `2026-06-03`。
- 数据底座：复用项目现有主板 5 分钟成交、委托、盘口状态、日线和涨跌停状态库，不另起炉灶。
- 起筛范围：先只看单日有 4% 以上日内高点振幅、且成交额不低于 8000 万的股票日。
- 试盘候选的结构要求是：5 分钟急拉足够猛，单根高点相对参考价约在 4.47% 以上；成交额至少是当日中位 5 分钟成交额的 12.80 倍；OIB/成交额比不低于 0.22；当天随后要有明显回吐，但后续又不能继续把高点显著往上扩。
- 正式启动日与试盘区分开的关键，不是“有没有拉”，而是“拉完以后当天是否被市场承认”。如果后续继续扩高、回吐很浅，或直接走成触板型强攻，更接近启动。
- 启动日样本里，技术锚点有时会落在下午回封或再拉的那根 5 分钟，因此样本表额外给了 `business_anchor_time`，专门记录业务上更像发动的时间点。

## 3. 贝因美复盘
- `2026-06-01 10:30`：5 分钟内急拉很强，量能爆发，但全天没有继续把高点往上抬，收盘回吐明显，更像第一次摸上方筹码。
- `2026-06-02 13:00`：又来一次类似动作，当天依然没走成，更像连续试盘，而不是随机异动。
- `2026-06-03`：日线已经转成正式发动。技术锚点落在 `14:30`，但从业务上看，真正的发动点是 `09:35` 首次触板，应该归为“试盘后启动”。

## 4. 全市场扫描结果
- `probe_candidate`：273 次。
- `launch_day`：4899 次，其中“试盘后启动” 130 次，“直接启动” 4769 次。
- 试盘角色拆分：首次试盘 246 次，连续试盘 2 次，重新试盘 25 次。
- 严格口径下，只有约 29.3% 的试盘事件在 10 个交易日内等到启动，这说明“可观测试盘”是一个有辨识度但不高频的前置信号，不是所有启动都会先给你一轮明显试盘。

## 5. 后续表现统计
- 首次试盘后 5 日收盘收益：231 个样本，均值 -0.86%，中位数 -1.45%。
- 首次试盘后 10 日内最好冲高：208 个样本，均值 9.92%，中位数 5.93%。
- 重新试盘后 5 日收盘收益：19 个样本，均值 -2.68%，中位数 -2.91%。
- 重新试盘后 10 日内最好冲高：17 个样本，均值 8.09%，中位数 5.55%。
- 连续试盘后 5 日收盘收益：1 个样本，均值 7.24%，中位数 7.24%。
- 连续试盘后 10 日内最好冲高：1 个样本，均值 14.51%，中位数 14.51%。
- 连续试盘当前只有 2 次识别、真正有 5 日前瞻的只有 1 次，方向上偏强，但样本远不够，不能当成稳定统计结论。

按股票聚类后：
- 两次试盘：25 只股票，10 日最好冲高均值 11.83%，20 日最好收盘均值 10.11%。
- 单次试盘：220 只股票，10 日最好冲高均值 9.86%，20 日最好收盘均值 -2.72%。
- 多次试盘：1 只股票，10 日最好冲高均值 13.42%，20 日最好收盘均值 5.96%。

## 6. 接到现有体系的建议
- 第一优先级：接到星火类模型，做状态增强特征，而不是直接当买点。最值得加的是“近 10 日是否出现试盘”“是首次还是重试”“距离最近一次试盘几天”“是否进入启动窗口”。
- 第二优先级：做独立 `watch_only` 观察池。输出语言要面向交易研究，而不是只报技术字段，例如“这只票 3 天前试过盘，今天进入启动观察窗口”。
- 第三优先级：接热点板块优先级，但要先补主题映射和热度日表校验。这个方向值得做，但当前这版证据还不够硬，先不把它写成已验证结论。
- 当前不建议把试盘事件直接升级成自动交易模型，也不建议直接替代现有成熟买点策略。

补充到当前长样本概率框架后，更明确的接法已经变成：

- `趋势高分池` 可以先接进盘后演练。验证集里，次日开盘买入后 `5` 日平均收益约 `+10.34%`，`5` 日胜率约 `83.9%`，`10` 日内摸到 `+5%` 的概率约 `90.3%`。
- `首板高分池` 也有价值，但更适合做优先级排序。验证集里，`20` 日内首板命中率约 `54.8%`，但 `5` 日内打到 `-5%` 的概率仍有 `38.7%`，说明回撤还偏粗。
- 下一阶段最值得强化的不是事件窗口，而是现有数据库里的 `D1/D3 资金确认`、`盘口承接/撤卖`、`热点前排强度`、`价格位置结构`。

进一步做完强化对比后，结论又往前走了一步：

- `首板线` 强化有效，验证 AUC 已从 `0.6033` 提升到 `0.7206`，高分池首板命中率从 `54.8%` 提升到 `61.3%`，高分池 `10` 日平均收益从 `+7.56%` 提升到 `+11.33%`。
- `趋势线` 暂时不适合直接换主模型。虽然强化版 AUC 从 `0.7042` 小幅升到 `0.7132`，但高分池真实交易体验反而变差，说明当前更合理的做法是保留原趋势主模型，再叠加 `D3` 资金确认或位置过滤做二次筛选。
- 新增 `2026-01-01 ~ 2026-03-31` 的样本外检验后，结论更细了一步：
  - `首板强化版` 在新样本里依然比基线更容易筛中首板，但短线买入体验不一定同步变强，更像“更准的首板筛子”。
  - `趋势强化版` 在新样本里 AUC 提升更明显，但收益和回撤改善还不稳定，暂时仍不建议直接替换原趋势主模型。
  - `趋势基线高分池 + D3 资金确认` 仍然是当前最稳的增强方式之一。

## 7. 输出文件
- [event_definition.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/event_definition.md)
- [sample_review.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/sample_review.csv)
- [event_scan.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/event_scan.csv)
- [followup_outcome.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/followup_outcome.csv)
- [cluster_summary.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/cluster_summary.csv)
- [integration_notes.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/integration_notes.md)
- [probe_signal_probability_framework_conclusion.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_probability_framework_conclusion.md)
- [probe_signal_strengthening_directions.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_directions.md)
- [probe_signal_strengthening_compare.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_compare.md)
- [probe_signal_q1_2026_out_of_sample.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_out_of_sample.md)
- [probe_signal_bucket_trade_metrics.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_bucket_trade_metrics.csv)
- [probe_signal_rule_exploration.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_rule_exploration.csv)
- [probe_signal_enriched_candidate_pool.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_enriched_candidate_pool.csv)
- [probe_signal_strengthening_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_model_compare.csv)
- [probe_signal_strengthening_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_bucket_compare.csv)
- [probe_signal_strengthening_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_strengthening_overlay_compare.csv)
- [probe_signal_q1_2026_model_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_model_compare.csv)
- [probe_signal_q1_2026_bucket_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_bucket_compare.csv)
- [probe_signal_q1_2026_overlay_compare.csv](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/probe_signal_q1_2026_overlay_compare.csv)
- [research_conclusion.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/research_conclusion.md)
- [summary.json](/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/experiments/20260603-probe-lift-research/summary.json)

## 8. 外部资料
- [MBA智库百科：试盘](https://wiki.mbalib.com/wiki/%E8%AF%95%E7%9B%98)
- [东方财富百科：试盘](https://baike.eastmoney.com/item/%E8%AF%95%E7%9B%98)
- [Cont, Kukanov, Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
