# 小主题热点研究总览

## 当前结论

热点数据有用，但不能直接当买点。

当前最有价值的用法有两类：

1. 用小颗粒主题判断市场资金正在交易什么，给个股研究提供背景。
2. 从热点样本里反推“哪些形态未来 20 日有冲高”，再用 L2 和卖点规则做交易验证。

## 已落地数据

- 小主题日度热度：`/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db`
- 个股 L1/L2 底座：`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
- 热点大涨样本：`/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/market_heat/backtests/hot_theme_big_mover_l2_precondition_events.csv`

## 关键研究结论

### 1. 纯热点不能买

细颗粒热点能提高未来强股覆盖率，但热点池内部后排票太多，直接买 Alpha 不稳定。

### 2. L2 单因子不能定买点

近 3/5/10/20 日主力或超大单净流入，与未来收益没有稳定线性关系。当前较有解释价值的是：

```text
近5日超大单净流入 / 近5日成交额
```

它更像“未来几天有没有冲高”的辅助变量，不是独立买入信号。

### 3. 强者恒强能筛出后20日冲高样本

当前最有效的冲高筛选规则：

```text
热点日涨幅 >= 7%
热点前20日已涨 > 20%
热点前5日超大单占成交额 > 2%
主题成交放大 >= 1.5
```

历史表现：

```text
全样本后20日最高 >=20%：18.7%
强者恒强规则后20日最高 >=20%：55.9%
```

这个规则适合找“未来有冲高概率”的票，但买点已经偏右侧，必须配合卖点。

### 4. 卖点比继续持有更重要

2025 年单账户 100 万实盘约束回测：

| 策略 | 最终资金 | 总收益 | 交易数 | 胜率 | 最大单笔亏损 |
|---|---:|---:|---:|---:|---:|
| +10% 半仓止盈，剩余按回撤/L2/时间退出 | 124.20万 | +24.2% | 9 | 77.8% | -14.7% |
| 去掉半仓，原规则全仓卖出 | 101.89万 | +1.9% | 9 | 55.6% | -14.7% |
| 固定持有20日 | 85.85万 | -14.2% | 5 | 40.0% | -29.7% |

当前判断：

```text
+10% 半仓止盈是策略收益核心，不是可有可无的风控动作。
固定持有 20 日最差，因为强者恒强样本的真实高点来得很快，后面容易回吐。
```

## 核心文件

- 冲高筛选规则：`docs/selection/market_heat/backtests/hot_theme_fwd20_screen_rules.md`
- 强者恒强样本页：`docs/selection/market_heat/backtests/hot_theme_strong_momentum_l2_cases.html`
- 卖点复盘：`docs/selection/market_heat/backtests/hot_theme_strong_momentum_sell_points.md`
- 100万单账户回测：`docs/selection/market_heat/backtests/strong_momentum_portfolio_2025.md`
- 去掉分批止盈对比：`docs/selection/market_heat/backtests/strong_momentum_exit_compare_2025.md`
- L2 资金相关性：`docs/selection/market_heat/backtests/l2_flow_forward_return_correlation.md`

## 当前使用边界

- 不能把热点排名直接等同于买入信号。
- 强者恒强规则可以作为“追强候选池”，但不是稳定自动交易系统。
- 买入后必须按交易规则执行，尤其是第一止盈和回撤退出。
- 后续需要继续测多仓位版本、不同市场阶段、不同板块生命周期。
