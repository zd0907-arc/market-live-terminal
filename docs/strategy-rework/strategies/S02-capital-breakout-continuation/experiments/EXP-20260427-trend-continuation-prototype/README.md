# 趋势中继策略原型实验

## 问题

当前“资金流回调稳健策略”高胜率但覆盖窄。大量强势股属于：

```text
已经涨过一段
资金没有明显撤退
没有标准回调买点
后面继续二波/主升
```

本实验验证“趋势中继原型”能否补充覆盖这类股票。

## 原型逻辑

信号日要求：

```text
前20日已有明显涨幅，但不极端过热
价格仍在20日高点附近
近期有回撤/震荡但未破坏趋势
前20/10日 L2 主力或超大单仍有留场迹象
信号日不能大跌，承接/主动买入不能太差
```

买入：信号日次日开盘。

卖出：暂复用资金流回调稳健策略的累计超大单退出/硬止损。

## 回测结果

- 全部交易：{'trade_count': 352, 'win_rate': 43.47, 'avg_return_pct': 1.25, 'avg_gross_return_pct': 1.76, 'median_return_pct': -2.57, 'max_return_pct': 128.39, 'min_return_pct': -20.16, 'avg_holding_days': 5.87, 'total_return_pct_signal_sum': 441.33}
- 成熟交易：{'trade_count': 263, 'win_rate': 39.92, 'avg_return_pct': 0.38, 'avg_gross_return_pct': 0.88, 'median_return_pct': -6.56, 'max_return_pct': 128.39, 'min_return_pct': -20.16, 'avg_holding_days': 6.5, 'total_return_pct_signal_sum': 99.76}

## 强势样本覆盖

| threshold   |   strong_count |   candidate_hit_count |   trade_hit_count |   stable_trade_hit_count |   combined_trade_hit_count |   new_trade_hit_vs_stable |
|:------------|---------------:|----------------------:|------------------:|-------------------------:|---------------------------:|--------------------------:|
| 30          |            674 |                   172 |               165 |                       15 |                        179 |                       164 |
| 50          |            222 |                    82 |                80 |                        6 |                         85 |                        79 |
| top50       |             50 |                    20 |                20 |                        2 |                         22 |                        20 |

## 初步结论

这是第一版原型，只用于判断方向是否值得继续。重点看它是否能补充当前稳健策略没有抓到的强势股，而不是马上投产。

## 输出文件

- `trend_continuation_candidates.csv`
- `trend_continuation_trades.csv`
- `trend_continuation_mature_trades.csv`
- `strong_coverage.csv`
- `all_runup_opportunities.csv`
- `summary.json`
