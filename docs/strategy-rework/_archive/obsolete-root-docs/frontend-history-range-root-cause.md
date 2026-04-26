# 选股页右侧复盘时间窗 / 旧数据问题：根因与修复

## 1. 现象

右侧复盘图表在选择 `90天 / 120天` 时，实际只能看到 `2026-03 ~ 2026-04` 左右的数据。

## 2. 根因

### 根因 A：前端时间窗锚点不对

旧逻辑直接用：

```ts
effectiveEndDate = 今天
effectiveStartDate = 今天 - coverageDays
```

这会导致历史复盘时，右侧图表并不是围绕当前选中的信号日/画像日展开。

### 根因 B：后端默认数据目录过度依赖 repo/data

旧配置默认优先读：

```text
<repo>/data/market_data.db
<repo>/data/atomic_facts/...
```

但本机真实完整数据在：

```text
/Users/dong/Desktop/AIGC/market-data
```

如果后端没有显式带环境变量启动，就容易退化成只读到最近一段正式 L2 history，导致旧数据缺失。

### 根因 C：日线 multiframe 没有把 `local_history` 当成兜底

即使更早日期没有完整挂单数据，只要有：

- `atomic_trade_daily`
- 或 `local_history`

日线图也应该能继续展示价格与主力资金走势。

旧逻辑这块不够完整。

---

## 3. 已做修复

### 修复 1：默认数据目录改为优先正式数据目录

文件：

- `/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/app/core/config.py`

现在默认优先：

```text
/Users/dong/Desktop/AIGC/market-data
```

找不到时才回退到：

```text
<repo>/data
```

### 修复 2：右侧复盘时间窗锚点改成围绕当前候选/画像日

文件：

- `/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/src/components/selection/SelectionDecisionPanel.tsx`

现在 `effectiveEndDate` 优先取：

1. `trade_plan.exit_signal_date`
2. `profile.requested_trade_date`
3. `profile.trade_date`
4. `candidate.trade_date`
5. 最后才回退到今天

这样：

- 你看历史候选时，图表会围绕那一天展开
- 你切 `90天 / 120天` 时，窗口语义是成立的

### 修复 3：日线 multiframe 增加 `local_history` 兜底

文件：

- `/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/app/routers/analysis.py`

现在日线链路会：

1. 先读 `history_daily_l2 + atomic_trade_daily`
2. 再把 `local_history` 合并进来做日线兜底
3. 若正式数据缺失，不让 placeholder 覆盖已有旧数据

---

## 4. 修复后的预期

### 日线

- 90天能看到完整 90 天左右的数据
- 120天能看到完整 120 天左右的数据
- 更早没挂单的数据，至少还能看到价格和旧主力资金口径

### 5m / 30m / 1h

- 近期优先展示正式 L2/atomic 结果
- 更老的数据如果没有细粒度历史，仍可能不完整
- 这是数据层限制，不是前端时间窗问题

---

## 5. 和当前三层重构的关系

这次修的是“旧前端右侧复盘”的基础能力，不是 v2 三层接入。

也就是说：

- 当前页面还是旧选股页
- 但右侧历史复盘至少先恢复到“窗口正确 + 旧数据能看”的状态
