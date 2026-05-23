# 当前策略研究运营摘要

> 说明：这是 `strategy-rework` 顶层的当前阶段运营摘要，用来替代旧的阶段状态卡和目录盘点卡，不是整个项目总入口。
> 进入项目先看：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 本专题当前三件套：`LONG_MEMORY.md`、`current-strategy-conclusion.md`、`current-research-operating-summary.md`

## 当前结论

- 当前策略研究已经从“单策略实验页”推进到“每日复盘决策页”。
- 已接入系统的主线能力只有三项：
  - 资金流回调稳健
  - 趋势中继高质量回踩
  - 每日复盘决策
- 当前定位仍然是研究/观察/复盘决策工作台，不应表述为稳定自动买入系统。

## 当前已接入与定位

| 能力 | 状态 | 当前定位 |
|---|---|---|
| 资金流回调稳健 | 已接入 | 当前高质量主策略 |
| 趋势中继高质量回踩 | 已接入 | 样本少但方向好，作为观察/小规模验证策略 |
| 每日复盘决策 | 已接入 | 按日期聚合多策略结果，作为日常入口 |
| 消息事件重估 | 未开发 | 下一轮独立研究主题 |

## 当前继续推进什么

1. 趋势中继继续滚动验证，重点看最近买入确认信号的后续表现。
2. 每日复盘页继续补“今日摘要 / 明日操作清单 / 观察池跨日跟踪”。
3. 持仓后的卖出监控与风险跟踪，后续单独做工作台能力。
4. 消息事件重估策略，后续按 `S03-news-event-revaluation` 专题推进。

## 当前明确不作为主线什么

- 不再回到旧确认/吸筹/出货三分打榜。
- 不把趋势中继“入池后直接买”当默认方案。
- 不把简单放宽成交额门槛、Top20 扩容、单因子 OIB/CVD/压单过滤当主策略升级方向。
- 不靠日期型阶段卡和目录盘点卡继续占顶层入口。

## 当前默认阅读路径

1. `LONG_MEMORY.md`
   - 长期不变的总判断、边界和用户目标。
2. `current-strategy-conclusion.md`
   - 当前主策略和当前结论单页。
3. 本文档
   - 当前阶段状态、继续推进项、明确否决项。
4. 需要追溯实验采纳与否时，再看 `docs/archive/ARC-LEG-20260519-strategy-research-experiment-decision-log.md`。
5. 需要下钻具体策略时，再进 `strategies/S01~S03/`。

## 已迁入 Archive

- `docs/archive/ARC-LEG-20260519-strategy-research-current-inventory.md`
  - 旧的目录盘点卡，保留追溯价值，但不再作为顶层入口。
- `docs/archive/ARC-LEG-20260519-strategy-research-project-status-20260427.md`
  - 旧的阶段状态卡，保留追溯价值，但不再作为顶层入口。
- `docs/archive/ARC-LEG-20260519-strategy-research-experiment-decision-log.md`
  - 旧的实验登记表，保留追溯价值，但不再作为顶层入口。
