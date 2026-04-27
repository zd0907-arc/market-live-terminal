# 归档索引

## 说明

当前不直接删除旧实验文件，原因是：

```text
旧 CSV/summary 仍可用于复盘和追溯；
删除会让历史脚本、文档链接失效。
```

处理方式：

```text
不再作为当前决策入口；
统一从 current-strategy-conclusion.md 和 experiment-decision-log.md 看结论。
```

## 归档类资料

### 早期未归入策略族的实验

路径：

```text
docs/strategy-rework/_archive/early-experiments/
```

状态：归档，只读参考。

### 旧生命周期策略

路径：

```text
docs/strategy-rework/strategies/v0-lifecycle-baseline/
```

状态：归档，只做对照。

### 旧版本名策略目录

路径：

```text
docs/strategy-rework/strategies/v1-trend-reversal-confirmation/
```

状态：保留，因为大量实验和脚本仍引用这里。

对话里不再叫 `v1`，统一叫：

```text
资金流回调策略历史实验
```

### 未采纳实验

这些实验保留，但不作为当前策略依据：

| 实验 | 状态 |
|---|---|
| `strategies/S04-capital-exit-risk/experiments/EXP-20260426-sell-pressure-attribution` | 压单单因子暂不采用 |
| `strategies/S04-capital-exit-risk/experiments/EXP-20260426-oib-cvd-divergence` | 单因子不采用，已并入组合风险 |
| `strategies/S05-market-regime-filter/experiments/EXP-20260426-market-l2-regime-filter` | 大盘环境过滤暂不采用 |
| `20260426-v1-5-business-guards` | ST/市值/冷却混合规则暂不整体采用 |

## 当前入口

后续先看：

```text
docs/strategy-rework/current-strategy-conclusion.md
docs/strategy-rework/experiment-decision-log.md
```


## 已物理归档

```text
_archive/early-experiments/
_archive/obsolete-root-docs/
```

## 2026-04-27 新增归档

| 路径 | 原因 |
|---|---|
| `_archive/obsolete-strategy-dirs/v0-lifecycle-baseline/` | 旧生命周期 baseline，已被多策略每日复盘框架替代 |
| `_archive/obsolete-strategy-dirs/v1-trend-reversal-confirmation/` | 旧策略命名目录，当前由 `S01-capital-trend-reversal` 承接有效内容 |
