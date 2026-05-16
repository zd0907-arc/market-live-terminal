# 热点主线 / 板块共振 aggressive 10cm 实验

- 数据源：`/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db`、`/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
- 初始资金：100万，主板 10cm，信号日收盘后打分，下一交易日开盘买入。
- 统一约束：不使用任何信号日之后的字段；买入一律 T+1；持仓退出只使用持仓当日及以前数据。

## 变体

- `leader_attack`：只做日内最强热点里的 leader/volume_core，强调主线热度、强度和个股承接。
- `theme_resonance`：只做同日落在多个热点主题里的重叠成员，强调主题共振、扩散与容量承接。

## 结果

| period | variant | net_return_pct | max_drawdown_pct | trade_count | win_rate_pct | avg_return_pct |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2026-04-01~2026-04-30 -> 2026-05-11 | leader_attack | 6.17 | -2.75 | 6 | 50.00 | 3.43 |
| 2026-04-01~2026-04-30 -> 2026-05-11 | theme_resonance | 8.26 | -3.49 | 7 | 57.14 | 3.93 |
| 2026-03-02~2026-05-11 | leader_attack | 16.00 | -30.92 | 219 | 28.31 | 0.24 |
| 2026-03-02~2026-05-11 | theme_resonance | 1.77 | -24.48 | 180 | 30.00 | 0.06 |

## 最优变体

- 以全区间 `net_return_pct` 优先、`max_drawdown_pct` 次优筛选，当前最优：`leader_attack`。
- 全区间表现：收益 16.00% ，最大回撤 -30.92% ，交易 219 笔，胜率 28.31%。

## 无未来函数说明

- 信号端只读取当日 `fine_theme_heat_daily` / `fine_theme_member_daily` 和当日 `atomic_*_daily`。
- 买入执行固定为下一交易日开盘，且过滤过高缺口和开盘近涨停情形。
- 止损 / 趋势衰减 / 超时退出只依据持仓期间当日 OHLC 与当日热点状态，若是收盘后触发则下一交易日开盘卖出。
