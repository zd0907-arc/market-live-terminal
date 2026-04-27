# 当前策略研究目录盘点

## 结论

当前有效资料只看三类：

```text
LONG_MEMORY.md / project-status-20260427.md
strategies/S01-capital-trend-reversal/
strategies/S02-capital-breakout-continuation/
```

旧 `v0-*`、`v1-*` 策略目录已归档，不再作为当前入口。

## 总入口文档

| 文档 | 作用 |
|---|---|
| `README.md` | 策略研究文件夹入口 |
| `LONG_MEMORY.md` | 长记忆，记录当前大方向和已确认结论 |
| `project-status-20260427.md` | 当前系统和研究状态 |
| `review-page-user-story.md` | 复盘页面用户 Story 和优化空间 |
| `current-strategy-conclusion.md` | 当前策略结论 |
| `experiment-decision-log.md` | 实验采纳/不采纳登记 |
| `strategy-taxonomy.md` | 策略族和命名规则 |

## 当前已接入系统

| 功能 | 状态 |
|---|---|
| 资金流回调稳健 | 已接入 |
| 趋势中继高质量回踩 | 已接入 |
| 每日复盘决策 | 已接入，默认入口 |
| 策略节点打点 | 已接入 |
| 策略解释浮窗 | 已接入第一版 |

## 当前有效策略资料

### 资金流回调稳健

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

### 趋势中继高质量回踩

位置：

```text
docs/strategy-rework/strategies/S02-capital-breakout-continuation/
```

核心实验：

| 实验 | 结论 |
|---|---|
| `EXP-20260427-strong-runup-opportunity-audit` | 强势股反推，说明需要趋势中继策略 |
| `EXP-20260427-trend-continuation-prototype` | 观察池覆盖有效，但直接买入失败 |
| `EXP-20260427-trend-continuation-quality-callback-expand` | 高质量回踩方向有效 |
| `EXP-20260427-trend-continuation-current-candidate` | 当前页面接入版本 |

产品接入：

```text
docs/changes/REQ-20260427-01-selection-stable-callback-strategy-ui.md
docs/changes/REQ-20260427-02-selection-trend-continuation-strategy-ui.md
```

## 已归档

| 路径 | 原因 |
|---|---|
| `_archive/obsolete-strategy-dirs/v0-lifecycle-baseline` | 旧生命周期方案，已被当前多策略框架替代 |
| `_archive/obsolete-strategy-dirs/v1-trend-reversal-confirmation` | 旧命名目录，当前用 S01 策略族承接 |
| `_archive/obsolete-root-docs/` | 旧阶段散文档 |
| `_archive/early-experiments/` | 早期探索实验 |

## 当前未解决问题

1. 趋势中继需要继续滚动验证，尤其是最近买入确认但未成熟的信号。
2. 资金流回调稳健还没有完整观察池展示。
3. 每日复盘页还缺今日摘要、明日操作清单、观察池跨日跟踪。
4. 持仓后的卖出监控还没做成独立工作台。
5. 消息事件重估策略需求已重新收口到 `strategies/S03-news-event-revaluation/README.md`，尚未开发；核心包含“候选票事件解释卡”和“消息触发快速研判卡”。
