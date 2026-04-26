# Layer 3：交易状态与回测层

## 1. 定位

交易状态层回答：

```text
能不能进？进了以后能不能拿？什么时候出？历史上这么做收益如何？
```

它是最终交易模拟和回测的执行层。

当前实现方向已经收敛为：

```text
不是先做复杂仓位管理，而是先把“什么时候主力在进、什么时候主力在跑”识别清楚
```

因此 Layer 3 当前重点是：

- 进场时机识别
- 出场时机识别
- 爆拉/暴跌日意图识别
- 用 L1/L2 + 挂撤单组合来判断这一天更像吸筹、攻击、洗盘、还是出货

## 2. 状态机

建议状态：

```text
watch
accumulating
event_spike
shakeout
shakeout_repair
launching
entered
holding
distribution_warning
exit
failed
```

当前 v0.1 的状态跃迁已经受 `intent_profile` 驱动：

- `accumulation`
- `launch_attack`
- `follow_through_attack`
- `washout`
- `shakeout_repair`
- `distribution`
- `panic_distribution`
- `pull_up_distribution`

## 3. 状态定义

### 3.1 `watch`

含义：有资金/事件异动，但不足以进场。

进入条件候选：

- Layer 1 有候选，但量化强度不足。
- Layer 2 事件逻辑较强，但资金尚未确认。

动作：观察，不买。

### 3.2 `accumulating`

含义：资金持续承接/吸筹。

进入条件候选：

- 多日 L2 主力/超大净额为正。
- 承接强于卖压。
- 价格未过热或处于可接受中继区。

动作：加入重点观察，不一定立刻买。

### 3.3 `event_spike`

含义：突发事件驱动启动，未必有前置吸筹。

进入条件候选：

- 涨停/大涨。
- 成交额异常放大。
- 新闻/公告/行业事件强。

动作：不盲追，等待资金确认或分歧后的二次机会。

### 3.4 `shakeout`

含义：分歧/急跌/洗盘候选。

进入条件候选：

- 单日回撤达到阈值。
- 但未确认出货。
- 需要观察后续 1-3 日回补。

动作：持仓不一定卖；未持仓等待修复。

### 3.5 `shakeout_repair`

含义：洗盘后资金回补和价格修复。

进入条件候选：

- 急跌后 1-3 日 L2 主力/超大资金回补。
- 回补覆盖前期流出一定比例。
- 价格收复关键位。
- 承接指标修复。

动作：重要进场/加仓候选。

### 3.6 `launching`

含义：启动确认。

进入条件候选：

- 价格突破平台或强修复。
- 成交额放大。
- L2 主动买强。
- OIB/CVD 转强。
- 公司/事件逻辑不弱。

动作：可生成次日模拟入场。

### 3.7 `entered`

含义：已模拟入场。

默认入场口径：

- 信号日后下一交易日买入。
- 后续可支持开盘价、收盘价、VWAP 等不同口径。

当前 v0.1 实现：

- 默认按下一交易日开盘执行。
- 若下一交易日近似涨停，则记为 `entry_blocked_limit_up`，该次机会放弃。
- 当前主板实验默认用 `9.5%` 近似涨跌停约束，后续再细分 ST/不同板块。

### 3.8 `holding`

含义：趋势和资金仍支持继续持有。

持续条件候选：

- 未跌破关键趋势位。
- L2 主力/超大资金未连续恶化。
- 承接仍在。
- 公司/事件逻辑未证伪。

### 3.9 `distribution_warning`

含义：出货/承接失效风险抬升。

条件候选：

- 高位放量滞涨。
- L2 主力/超大净额连续转负。
- `add_sell_ratio` 上升。
- `cancel_buy_ratio` 上升。
- `sell_pressure_ratio` 上升。
- `buy_support_ratio` 下降。
- CVD/OIB 转弱。

动作：减仓预警；回测中可选择部分退出或等待确认。

### 3.10 `exit`

含义：触发退出。

退出原因候选：

- 出货确认。
- 趋势破位。
- 洗盘修复失败。
- 止损。
- 止盈/浮盈保护。
- 最大持有天数到期。
- 公司逻辑证伪。

当前 v0.1 实现：

- 退出信号先在盘后生成，默认下一交易日开盘执行。
- 若下一交易日近似跌停，则记为 `exit_blocked_limit_down`，继续持有并等待后续可卖日。
- 若回放窗口结束但已有退出信号未执行，则按窗口末日收盘强制结算，同时保留原始 `exit_reason`。

### 3.11 `failed`

含义：启动失败或事件一日游。

用于复盘错误案例。

## 4. 参数化配置

所有阈值必须参数化。

建议配置分组：

```yaml
universe:
  min_market_cap: 5000000000
  max_market_cap: 50000000000

candidate:
  min_amount: 300000000
  amount_anomaly_launch: 1.5
  breakout_threshold_pct: 1.0

funding:
  l2_main_net_ratio_strong: 0.03
  l2_super_net_ratio_strong: 0.015
  active_buy_strength_strong: 5.0

shakeout:
  drop_pct: -5.0
  repair_days: 3
  repair_coverage_ratio: 1.2

exit:
  limit_up_pct: 9.5
  limit_down_pct: -9.5
  buy_slippage_bp: 15
  sell_slippage_bp: 15
  round_trip_fee_bp: 20
  max_open_positions: 3
  max_new_positions_per_day: 1
  max_holding_days: 40
  stop_loss_pct: -8.0
  trailing_take_profit_drawdown_pct: -12.0
  distribution_confirm_days: 2
```

具体数值只是占位，必须通过回测调参。

## 5. 单日历史回放

输入：

```text
trade_date = 2026-03-02
```

输出链路：

```text
候选 TopN
→ 公司研究/事件解释
→ 可进场列表
→ 次日模拟入场
→ 每日状态序列
→ 出场日与收益
```

单票输出示例：

```json
{
  "symbol": "sh603629",
  "signal_date": "2026-03-02",
  "entry_date": "2026-03-03",
  "exit_date": "2026-03-25",
  "return_pct": 18.4,
  "max_runup_pct": 32.1,
  "max_drawdown_pct": -6.2,
  "holding_days": 16,
  "exit_reason": "distribution_warning_confirmed",
  "state_path": [
    {"date": "2026-03-02", "state": "launching"},
    {"date": "2026-03-05", "state": "holding"},
    {"date": "2026-03-12", "state": "shakeout"},
    {"date": "2026-03-17", "state": "shakeout_repair"},
    {"date": "2026-03-25", "state": "exit"}
  ]
}
```

## 6. 月度/区间批量回测

输入：

```text
start_date = 2026-03-01
end_date = 2026-03-31
```

流程：

```text
对区间内每个交易日执行单日历史回放
→ 合并所有模拟交易
→ 处理重复信号和持仓冲突
→ 输出整体绩效
```

## 7. 回测统计指标

必须输出：

- 交易数
- 胜率
- 平均收益
- 收益中位数
- 最大单笔收益
- 最大单笔亏损
- 平均持有天数
- 最大持有天数
- 最大回撤
- 复利累计收益
- 平均毛收益
- 平均最大浮盈
- 平均浮盈回吐
- 累计收益
- 资金曲线
- 成功案例 TopN
- 失败案例 TopN
- 过早卖出案例
- 一日游误判案例

## 8. 风控和真实交易约束

后续回测要逐步加入：

- 涨停买不进。
- 跌停卖不出。
- 停牌。
- 滑点。
- 手续费。
- 单票最大仓位。
- 同日最大开仓数。
- 连续信号去重。
- 已持仓票不重复开仓。

当前 v0.1 已落地：

- 近似涨停买不进。
- 近似跌停卖不出。
- 买卖滑点参数。
- 往返手续费参数。
- 最大同时持仓数。
- 单日最大新增仓位数。
- 同票信号冲突去重。

但下一阶段重点不再放这里，而是继续优化：

- `distribution_score`
- `panic_distribution`
- `washout` vs `真实出货`
- `launch_attack` vs `虚拉派发`

## 9. 与产品页面关系

最终页面应支持两种模式：

### 9.1 历史回放模式

用户选择某日，系统展示：

- 当日候选。
- 公司研究卡片。
- 模拟入场/出场结果。
- 每日状态路径。

### 9.2 批量回测模式

用户选择区间，系统展示：

- 策略绩效概览。
- 每日候选和交易明细。
- 成功/失败案例。
- 参数版本对比。
