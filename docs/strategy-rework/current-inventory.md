# 当前策略研究目录盘点

## 结论

当前资料已经比较多，但分成了两类：

```text
1. 已沉淀为策略主线的资料：主要在 strategies/v1-trend-reversal-confirmation
2. 早期探索/临时实验：主要在 docs/strategy-rework/experiments
```

后续不清理旧文件，只建立索引和新规范。

## 当前关键目录

| 路径 | 当前含义 | 后续处理 |
|---|---|---|
| `_shared/` | 数据源、样本定义等跨策略资料 | 继续共用 |
| `cases/` | 利通电子等个股案例 | 继续保留 |
| `experiments/` | 早期未归入策略族的实验 | 只读归档，后续少新增 |
| `strategies/v0-lifecycle-baseline/` | 旧生命周期策略 | 作为对照基线 |
| `strategies/v1-trend-reversal-confirmation/` | 当前资金流趋势反转主线 | 映射为 `S01-capital-trend-reversal` |
| `strategies/S01-*` ~ `S05-*` | 新策略族结构 | 后续新实验放这里 |

## 当前 S01 已有有效资产

旧路径：

```text
strategies/v1-trend-reversal-confirmation/
```

有价值文件：

| 文件 | 价值 |
|---|---|
| `README.md` | 当前策略链路说明 |
| `factor-design.md` | 因子设计 |
| `research-hypotheses.md` | 研究假设 |
| `version-history.md` | v1 到 v1.5 的迭代记录 |
| `experiments/20260426-v1-3-robustness-scan/` | v1.3 全市场稳健性扫描 |
| `experiments/20260426-v1-4-modes/` | v1.4 quality/balanced 对比 |
| `experiments/20260426-v1-5-business-guards/` | ST/市值/冷却等业务防线试验 |
| `experiments/20260426-market-extreme-review/` | 市场最强/最弱 30 反推 |

## 当前最重要的未解决问题

1. S01 发现层偏保守，成交额 `2.5亿` 绝对门槛可能错过早期牛股。
2. S01 更适合抓“资金流趋势反转”，不能包圆所有强势票。
3. 已经涨过一段后继续走二波的票，应拆到 `S02`。
4. 消息/公司重估类行情，应拆到 `S03`，不能强塞进纯资金流策略。
5. 出货/诱多/风险退出能力应沉淀成 `S04`，供 S01/S02 复用。
