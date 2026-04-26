# 实验结论登记表

## 结论

这里记录哪些实验有效、哪些暂不采用。后续不要反复翻旧 CSV 才知道某个方向有没有做过。

## 采纳 / 继续推进

| 方向 | 结论 | 处理 |
|---|---|---|
| 累计超大单出场 | 有效 | 保留为持有/退出核心逻辑 |
| 启动期撤买单异常过滤 | 有效 | 保留 |
| 弱启动均衡过滤 | 有效 | 保留在当前基础策略里 |
| 组合风险过滤 | 有效 | 作为稳健模式继续推进 |
| 最强/最弱30反推 | 有价值 | 作为后续优化发现层和风险层的分析方法 |

## 暂不采用 / 只保留观察

| 方向 | 结论 | 原因 |
|---|---|---|
| 压单出货单因子 | 暂不采用 | 单独区分度弱，误杀风险高 |
| OIB/CVD 背离单因子 | 不单独采用 | 有风险提示价值，但单独硬过滤误杀大 |
| 大盘环境过滤 | 暂不采用 | 主力净流出太常见，过滤过重 |
| 买入后 1~3 日早退 | 暂不采用 | 会伤害收益，容易卖飞 |
| 市值/ST/冷却混合实验 | 暂不整体采用 | 混合验证不可解释，需拆开重做 |
| 只调 5%、6%、0/0.01 这类小阈值 | 不作为主方向 | 泛化意义弱，容易过拟合 |

## 当前有效实验路径

| 内容 | 路径 |
|---|---|
| 当前结论总文档 | `docs/strategy-rework/current-strategy-conclusion.md` |
| 组合风险实验 | `docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-combined-risk-stack/` |
| 组合风险扩展验证 | `docs/strategy-rework/strategies/S04-capital-exit-risk/experiments/EXP-20260426-combined-risk-stack-robustness/` |
| 稳健策略实验 | `docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-S01-M05-conservative-combined-risk/` |
| 最强/最弱30反推 | `docs/strategy-rework/strategies/S01-capital-trend-reversal/experiments/EXP-20260426-market-extreme-reverse-audit/` |

## 旧编号对照

这些编号只用于查文件，不建议对话里使用：

| 对话里建议叫法 | 文件/旧编号 |
|---|---|
| 旧生命周期基线 | `v0-lifecycle-baseline` |
| 资金流回调基础版 | `v1` |
| 累计超大单出场版 | `v1.2` |
| 撤买单过滤版 | `v1.3` |
| 均衡弱启动版 | `v1.4-balanced` |
| 资金流回调稳健策略 | `S01-M05-conservative-combined-risk` |
| 组合风险模块 | `S04-M01-observe-combined-risk-stack` |
