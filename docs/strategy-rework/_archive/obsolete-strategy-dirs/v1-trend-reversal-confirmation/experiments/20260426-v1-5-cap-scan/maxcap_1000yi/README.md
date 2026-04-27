# v1.5 业务防线与资金连续性验证

## 规则

- 基础沿用 v1.4-balanced。
- 剔除当前名称包含 ST/*ST 的股票。
- 流通市值过滤：发现日收盘价 × 当前流通股本，范围 50亿~500亿。
- 同股信号冷却/持仓互斥：一次买入信号后，到卖出信号后再冷却 5 个交易日。
- 买入后早期资金失败：前 3 个持仓日内，累计超大单和主力都转负且股价亏损，提前退出。

## 汇总

| scope   |   trade_count |   win_rate |   avg_return_pct |   avg_gross_return_pct |   median_return_pct |   max_return_pct |   min_return_pct |   avg_holding_days |   total_return_pct_signal_sum |
|:--------|--------------:|-----------:|-----------------:|-----------------------:|--------------------:|-----------------:|-----------------:|-------------------:|------------------------------:|
| full    |            34 |      41.18 |             3.8  |                   4.32 |               -1.45 |             62.3 |            -9.34 |               6.03 |                        129.2  |
| mature  |            19 |      63.16 |             8.24 |                   8.78 |                2.22 |             62.3 |            -8.97 |               8.68 |                        156.53 |

## 过滤原因

|                                                |   count |
|:-----------------------------------------------|--------:|
| v1_3_ladder_pull_filter                        |      30 |
| float_mcap_too_large                           |      17 |
| cooldown_or_open_position                      |      17 |
| weak_launch_with_bad_pullback_and_distribution |       8 |
| st_stock                                       |       3 |
| entry_blocked_limit_up                         |       1 |
| no_trade                                       |       1 |

## 文件

- enriched_candidates.csv
- filtered_candidates.csv
- accepted_candidates.csv
- v1_5_trades.csv
- tencent_snapshot_cache.json
- summary.json
