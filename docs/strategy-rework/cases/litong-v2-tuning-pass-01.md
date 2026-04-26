# 利通电子 v2 调参首轮记录

## 1. 本轮目标

不是做全市场最优参数，而是先拿 `sh603629` 利通电子，把：

- 启动买点
- 洗盘后再进场
- 出货/恐慌派发卖点

先调到一个相对顺手的状态。

## 2. 本轮采用参数

基于 `SelectionV2Params`，本轮重点只调这几个参数：

```text
attack_score_min = 65.0
repair_score_min = 60.0
distribution_score_warn = 70.0
panic_distribution_score_exit = 80.0
entry_attack_cvd_floor = -0.08
entry_return_20d_cap = 80.0
```

其余保持默认。

## 3. 这几个参数为什么这么调

### `attack_score_min = 65.0`

作用：

- 提高攻击型买点门槛
- 低质量脉冲少一些

逻辑：

- 如果主力真在主动推升，`attack_score` 不应该只刚刚及格

### `repair_score_min = 60.0`

作用：

- 洗盘修复要更明显，才重新纳入可买

逻辑：

- 只要跌后稍微弹一下就重进，会很容易吃到假修复

### `distribution_score_warn = 70.0`

作用：

- 出货预警放慢一点
- 减少强趋势中途被普通分歧洗出去

### `panic_distribution_score_exit = 80.0`

作用：

- 只有很强的“主力跑了”信号才直接触发卖点

### `entry_attack_cvd_floor = -0.08`

作用：

- 对攻击型入场增加一个成交验证

逻辑：

- 如果表面上爆拉，但 `cvd_ratio` 很差，容易是拉高分歧甚至诱多

这次它主要挡掉了：

- `2026-03-19`

### `entry_return_20d_cap = 80.0`

作用：

- 20日涨幅已经极端过热时，不继续追击

这次它主要挡掉了：

- `2026-04-23`

## 4. 利通电子回放结果

### 4.1 核心区间

本轮主要看：

```text
2026-01-01 ~ 2026-04-24
```

### 4.2 回放结果

回测摘要：

```text
trade_count = 2
win_rate = 100%
avg_return_pct = 86.31%
compounded_return_pct = 245.06%
max_drawdown_pct = 0.0%   （按当前已成交交易序列统计）
```

### 4.3 识别出的买卖点

#### 交易 1

```text
signal_date = 2026-01-14
entry_date  = 2026-01-15
exit_signal_date = 2026-03-17
exit_date   = 2026-03-18
net_return_pct = 100.65%
exit_reason = panic_distribution_exit
```

解释：

- `2026-01-14` 被识别为 `launch_attack`
- 攻击分数高、突破成立
- `2026-03-17` 被识别为 `panic_distribution`
- 说明系统判断这一天更像“主力在跑”，不是普通洗盘

#### 交易 2

```text
signal_date = 2026-03-25
entry_date  = 2026-03-26
exit_date   = 2026-04-24
net_return_pct = 71.97%
exit_reason = window_end
```

解释：

- 这段不是最早攻击启动，而是“洗盘修复 + 再次走强”
- 对应的是第二段主升

## 5. 本轮被挡掉的典型信号

### `2026-03-19`

原始信号：

```text
intent_label = launch_attack
attack_score = 78.88
```

但被挡掉，原因：

```text
攻击型信号但 CVD 偏弱，疑似拉高分歧
```

这是本轮调参里最关键的一步。

### `2026-04-23`

原始信号：

```text
intent_label = launch_attack
attack_score = 70.43
return_20d_pct = 101.69
```

但被挡掉，原因：

```text
20日涨幅过热，禁止继续追击
```

## 6. 页面验证口径

当前 `V2 实验验证` 页面有两种分数需要区分：

```text
Layer1 当日横截面分数：只看信号日当日的资金、活跃度、结构
Layer3 回放验证排序：看当日候选后，按次日入场、后续出场、最终收益排序
```

利通在 Layer1 横截面里不是 Top10：

```text
2026-01-14: #48
2026-03-25: #62
```

但用本轮真正定义的 Layer3 生命周期策略回放后，利通是：

```text
2026-01-14: #1, net_return_pct = 100.65%
2026-03-25: #1, net_return_pct = 71.97%
```

所以页面里的 `V2 实验验证` 已改为按 Layer3 回放验证排序。

注意：这个排序使用了信号日之后的结果，只能用于历史验证和调参，不能直接用于实盘。

## 7. 这一轮调参的局限

如果把区间放宽到最近 6 个月全看，`2025-11` 和 `2025-12` 仍有早期噪声信号。

也就是说：

```text
这套参数已经把 2026-01 ~ 2026-04 这一轮主行情打得比较顺
但还没有把更早期的小波动完全过滤干净
```

所以这只是：

```text
pass 01
```

下一轮更合理的方向，不是继续乱加字段，而是专门调：

- 主升前的假突破
- `washout` 和 `panic_distribution` 的边界
- `launch_attack` 和 “拉高分歧” 的边界
