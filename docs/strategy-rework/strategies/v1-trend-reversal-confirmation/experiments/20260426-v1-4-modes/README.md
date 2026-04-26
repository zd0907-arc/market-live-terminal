# v1.4 双模式回测

基于 v1.3 阈值 1.5，再测试弱启动过滤的两个模式。

## 模式定义

```text
v1.3:
  过滤 launch_cancel_buy_to_add_buy_vs_hist > 1.5

v1.4-quality:
  先执行 v1.3 过滤
  再过滤 launch3_return_pct < 6

v1.4-balanced:
  先执行 v1.3 过滤
  再过滤 launch3_return_pct < 6
       且 pullback_support_spread < 0
       且 confirm_distribution_score >= 45
```

## 结果对比

| mode          |   passed_candidate_count |   filtered_candidate_count |   full_trade_count |   full_win_rate |   full_avg_return_pct |   full_avg_gross_return_pct |   full_median_return_pct |   full_max_return_pct |   full_min_return_pct |   full_avg_holding_days |   full_total_return_pct_signal_sum |   mature_trade_count |   mature_win_rate |   mature_avg_return_pct |   mature_avg_gross_return_pct |   mature_median_return_pct |   mature_max_return_pct |   mature_min_return_pct |   mature_avg_holding_days |   mature_total_return_pct_signal_sum |
|:--------------|-------------------------:|---------------------------:|-------------------:|----------------:|----------------------:|----------------------------:|-------------------------:|----------------------:|----------------------:|------------------------:|-----------------------------------:|---------------------:|------------------:|------------------------:|------------------------------:|---------------------------:|------------------------:|------------------------:|--------------------------:|-------------------------------------:|
| v1.3          |                      324 |                         46 |                 75 |           58.67 |                  4.6  |                        5.12 |                     3.2  |                 62.3  |                -13.07 |                    8.09 |                             344.82 |                   48 |             72.92 |                    7.21 |                          7.75 |                       5.33 |                   62.3  |                  -12.13 |                     10.33 |                               346.03 |
| v1.4-quality  |                       65 |                        305 |                 39 |           58.97 |                  6.76 |                        7.29 |                     8.21 |                 31.05 |                -13.07 |                    8.92 |                             263.59 |                   22 |             77.27 |                   11.18 |                         11.74 |                      10.1  |                   31.05 |                   -5.61 |                     12.36 |                               246    |
| v1.4-balanced |                      314 |                         56 |                 65 |           60    |                  5.08 |                        5.61 |                     3.2  |                 62.3  |                -13.07 |                    8.34 |                             330.23 |                   41 |             78.05 |                    8.44 |                          8.99 |                       5.72 |                   62.3  |                  -12.13 |                     10.88 |                               346.19 |

## 口径说明

- 发现日：2026-03-02 ~ 2026-04-24
- 回放到：2026-04-24
- 成熟交易：买入后至少还有 10 个交易日数据
- full：包含 4 月下旬未来数据不足的交易。
- mature：只统计成熟交易，更适合判断策略质量。

## 文件

- mode_comparison.csv
- all_mode_trades.csv
- all_mode_filtered_candidates.csv
- enriched_candidates.csv
- summary.json
