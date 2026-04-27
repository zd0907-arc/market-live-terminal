# 当前策略研究目录盘点

## 结论

当前资料按三层管理：

```text
长记忆/总入口
-> 策略族
-> 实验目录
```

当前不要再新增散乱文档；新实验必须落到对应策略族下面。

## 总入口文档

| 文档 | 作用 |
|---|---|
| `README.md` | 策略研究文件夹入口 |
| `LONG_MEMORY.md` | 长记忆，记录当前大方向和已确认结论 |
| `project-status-20260427.md` | 当前系统和研究状态 |
| `current-strategy-conclusion.md` | 当前策略结论 |
| `experiment-decision-log.md` | 实验采纳/不采纳登记 |
| `strategy-taxonomy.md` | 策略族和命名规则 |

## 当前可用策略资料

### 资金流回调稳健策略

位置：

```text
docs/strategy-rework/strategies/S01-capital-trend-reversal/
```

核心实验：

| 实验 | 结论 |
|---|---|
| `EXP-20260426-S01-M05-conservative-combined-risk` | 当前稳健策略，已接入系统 |
| `EXP-20260427-liquidity-gate-variants` | 简单放宽成交额门槛不适合直接替换 |
| `EXP-20260427-liquidity-gate-variants-top20` | Top20 扩容提高覆盖但降低质量 |

产品接入：

```text
docs/changes/REQ-20260427-01-selection-stable-callback-strategy-ui.md
docs/strategy-rework/product-integration-stable-callback-strategy.md
```

### 趋势中继策略

位置：

```text
docs/strategy-rework/strategies/S02-capital-breakout-continuation/
```

核心实验：

| 实验 | 结论 |
|---|---|
| `EXP-20260427-strong-runup-opportunity-audit` | 强势股反推，说明需要趋势中继策略 |
| `EXP-20260427-trend-continuation-prototype` | 观察池覆盖有效，但直接买入失败 |
| `EXP-20260427-trend-continuation-prototype-score70` | 单纯提高分数阈值无效 |
| `EXP-20260427-trend-continuation-prototype-score75-top5` | 进一步收紧仍无效 |

下一步方案：

```text
docs/strategy-rework/strategies/S02-capital-breakout-continuation/next-buy-point-plan.md
```

## 当前未解决问题

1. 趋势中继策略需要二次买点确认，不能入池后直接买。
2. 多策略合并后，要继续验证对 Top30/Top50/涨幅>=30%/涨幅>=50% 的覆盖率。
3. 消息事件重估策略还没启动。
4. ST、市值、冷却期等业务防线要以后拆开单独验证。
