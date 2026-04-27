# v1.3 挂单归因分析：大亏票 vs 大赚票

基于 v1.2 最优参数的交易结果，暂不改策略，只对 `净收益 <= -8%` 与 `净收益 >= 10%` 做 L2 挂单对比。

## 样本数

- 大亏样本：22
- 大赚样本：23

## 关键差异

| feature                                       |   loss_mean |   loss_median |   win_mean |   win_median |   loss_minus_win_median |
|:----------------------------------------------|------------:|--------------:|-----------:|-------------:|------------------------:|
| launch3_ob_cancel_buy_to_add_buy_vs_hist      |   11.989    |      2.2369   |   2.49937  |      1.08    |                1.1569   |
| pullback_day_ob_buy_support_avg               |    1.43415  |      1.46832  |   1.01186  |      0.54652 |                0.921795 |
| launch3_ob_buy_support_avg                    |    1.31609  |      1.37903  |   0.863657 |      0.51722 |                0.86181  |
| pullback_day_ob_cancel_buy_to_add_buy         |    0.111389 |      0.0032   |   0.319815 |      0.44787 |               -0.44467  |
| launch3_ob_cancel_buy_to_add_buy              |    0.132231 |      0.008645 |   0.276059 |      0.38571 |               -0.377065 |
| pullback_day_ob_cancel_buy_to_add_buy_vs_hist |    2.37201  |      0.91935  |   1.62457  |      1.1528  |               -0.23345  |
| pullback_day_ob_oib_cvd_gap                   |    0.295605 |      0.14471  |   0.219276 |      0.04304 |                0.10167  |
| launch3_ob_oib_cvd_gap                        |    0.154214 |     -0.08681  |   0.005062 |     -0.00959 |               -0.07722  |
| pullback_day_ob_support_spread_avg            |    0.283373 |      0.081855 |   0.200104 |      0.01585 |                0.066005 |
| pullback_day_ob_oib_ratio                     |    0.283373 |      0.081855 |   0.200104 |      0.01585 |                0.066005 |
| pullback_day_ob_cvd_ratio                     |   -0.01223  |      0.03021  |  -0.01917  |     -0.01557 |                0.04578  |
| pullback_day_ob_add_sell_vs_hist              |    0.911614 |      1.0006   |   0.937513 |      0.9655  |                0.0351   |

## 简单规则扫描

| rule                                        |   hit_all |   hit_loss |   hit_loss_rate_in_losses |   hit_win |   hit_win_rate_in_winners |   hit_avg_return |
|:--------------------------------------------|----------:|-----------:|--------------------------:|----------:|--------------------------:|-----------------:|
| pullback_oib_cvd_gap>=0.03_and_cvd<=0.01    |        38 |         10 |                     45.45 |        12 |                     52.17 |           4.6495 |
| pullback_support_spread<0                   |        37 |          9 |                     40.91 |         9 |                     39.13 |           1.7524 |
| pullback_cancel_buy_to_add_buy>=0.85        |         0 |          0 |                      0    |         0 |                      0    |           0      |
| pullback_cancel_buy_to_add_buy>=1.0         |         0 |          0 |                      0    |         0 |                      0    |           0      |
| pullback_add_sell_vs_hist>=1.35             |         0 |          0 |                      0    |         0 |                      0    |           0      |
| launch_add_sell_vs_hist>=1.35_and_support<0 |         0 |          0 |                      0    |         0 |                      0    |           0      |
| launch_cancel_buy_to_add_buy>=0.85          |         0 |          0 |                      0    |         0 |                      0    |           0      |


## What-if：如果把疑似诱多票过滤掉

| filter | filtered_count | kept_count | win_rate | avg_return_pct | median_return_pct | min_return_pct | max_return_pct | sum_return_pct |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
| base_no_filter | 0 | 82 | 59.76 | 3.21 | 2.75 | -18.38 | 62.3 | 263.43 |
| F1_launch_cancel_vs_hist_gt_2 | 24 | 58 | 72.41 | 6.3 | 5.31 | -13.07 | 62.3 | 365.4 |
| F2_launch_cancel_vs_hist_gt_2_and_buy_support_gt_1 | 23 | 59 | 72.88 | 6.21 | 5.29 | -13.07 | 62.3 | 366.64 |
| F3_launch_buy_support_gt_1 | 48 | 34 | 67.65 | 6.48 | 5.54 | -11.28 | 62.3 | 220.16 |
| F4_launch_cancel_vs_hist_gt_2_or_buy_support_gt_1_5 | 29 | 53 | 73.58 | 6.49 | 5.29 | -12.13 | 62.3 | 343.8 |

初步最有价值的拦截条件是：`launch3_ob_cancel_buy_to_add_buy_vs_hist > 2`。它过滤 24 笔，保留样本胜率从 59.76% 提升到 72.41%，中位收益从 2.76% 提升到 5.31%。

业务解释：不是“撤买单绝对值高”危险，而是“启动期撤买单/新增买单 相对自身历史突然放大”危险，更像撤梯子诱多。

## 初步结论

1. 这一步只做归因，不直接固化规则。
2. 优先寻找“能覆盖较多大亏、但少误杀大赚”的过滤条件。
3. 如果单一挂单条件误杀严重，v1.3 应使用组合规则，而不是一票否决。

## 文件

- v1_2_trades_orderbook_enriched.csv
- big_loss_vs_big_win_orderbook_diff.csv
- simple_rule_scan.csv
- loss_trades_focus.csv
- summary.json
- what_if_filter_scan.csv
