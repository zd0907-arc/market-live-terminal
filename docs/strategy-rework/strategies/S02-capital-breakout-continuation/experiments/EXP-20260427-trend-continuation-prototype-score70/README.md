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

- 全部交易：{'trade_count': 147, 'win_rate': 44.22, 'avg_return_pct': 0.39, 'avg_gross_return_pct': 0.9, 'median_return_pct': -2.35, 'max_return_pct': 45.49, 'min_return_pct': -16.51, 'avg_holding_days': 6.14, 'total_return_pct_signal_sum': 57.91}
- 成熟交易：{'trade_count': 119, 'win_rate': 41.18, 'avg_return_pct': -1.15, 'avg_gross_return_pct': -0.65, 'median_return_pct': -6.54, 'max_return_pct': 36.14, 'min_return_pct': -16.51, 'avg_holding_days': 6.71, 'total_return_pct_signal_sum': -136.73}

## 强势样本覆盖

| threshold   |   strong_count |   candidate_hit_count |   trade_hit_count |   stable_trade_hit_count |   combined_trade_hit_count |   new_trade_hit_vs_stable |
|:------------|---------------:|----------------------:|------------------:|-------------------------:|---------------------------:|--------------------------:|
| 30          |            674 |                    89 |                84 |                       15 |                         99 |                        84 |
| 50          |            222 |                    49 |                48 |                        6 |                         54 |                        48 |
| top50       |             50 |                    12 |                12 |                        2 |                         14 |                        12 |

## 初步结论

这是第一版原型，只用于判断方向是否值得继续。重点看它是否能补充当前稳健策略没有抓到的强势股，而不是马上投产。

## 输出文件

- `trend_continuation_candidates.csv`
- `trend_continuation_trades.csv`
- `trend_continuation_mature_trades.csv`
- `strong_coverage.csv`
- `all_runup_opportunities.csv`
- `summary.json`
