# EXP-20260426-combined-risk-stack-robustness：组合风险跨样本验证

## 问题

上一轮只在 `S01-M04B / v1.4-balanced` 成熟交易 41 笔上验证了组合风险。本实验扩大到 v1.3 阈值样本、v1.4 多模式、full/mature 两种口径，检查 `risk_count_R1_R5>=2` 是否稳定。

## 样本

- `modes:*`：来自 `20260426-v1-4-modes/all_mode_trades.csv`。
- `threshold:*`：来自 `20260426-v1-3-robustness-scan/all_threshold_trades.csv`。
- 日期范围仍受 L2 挂单限制：2026-03-02 ~ 2026-04-24。

## 推荐规则

`risk_count_R1_R5>=2`：R1~R5 中至少两个风险同时出现。

- R1：启动期撤买/新增买接近防线，`>=1.2`。
- R2：启动期 OIB/CVD 背离。
- R3：确认日出货分偏高。
- R4：确认日超大单和主力均为负。
- R5：弱启动 + 回调承接差。

## 成熟样本横向结果

| sample_name                |   base_trade_count |   base_win_rate_pct |   base_avg_return_pct |   base_median_return_pct |   base_min_return_pct |   filtered_count |   filtered_avg_return_pct |   filtered_median_return_pct |   filtered_big_winner_gt_15_count |   kept_trade_count |   kept_win_rate_pct |   kept_avg_return_pct |   kept_median_return_pct |   kept_min_return_pct |   delta_avg_return_pct |   delta_median_return_pct |   delta_win_rate_pct |
|:---------------------------|-------------------:|--------------------:|----------------------:|-------------------------:|----------------------:|-----------------:|--------------------------:|-----------------------------:|----------------------------------:|-------------------:|--------------------:|----------------------:|-------------------------:|----------------------:|-----------------------:|--------------------------:|---------------------:|
| modes:v1.3:mature          |                 48 |               72.92 |                  7.21 |                     5.33 |                -12.13 |               13 |                     -2.34 |                        -4.7  |                                 1 |                 35 |               88.57 |                 10.76 |                     8.21 |                -12.13 |                   3.55 |                      2.88 |                15.65 |
| modes:v1.4-balanced:mature |                 41 |               78.05 |                  8.44 |                     5.72 |                -12.13 |                6 |                     -5.04 |                        -4.7  |                                 0 |                 35 |               88.57 |                 10.76 |                     8.21 |                -12.13 |                   2.32 |                      2.49 |                10.52 |
| modes:v1.4-quality:mature  |                 22 |               77.27 |                 11.18 |                    10.1  |                 -5.61 |                3 |                     -3.32 |                        -4.7  |                                 0 |                 19 |               89.47 |                 13.47 |                    12.07 |                 -5.61 |                   2.29 |                      1.97 |                12.2  |
| threshold:1.5:mature       |                 48 |               72.92 |                  7.21 |                     5.33 |                -12.13 |               13 |                     -2.34 |                        -4.7  |                                 1 |                 35 |               88.57 |                 10.76 |                     8.21 |                -12.13 |                   3.55 |                      2.88 |                15.65 |
| threshold:2.0:mature       |                 50 |               72    |                  6.81 |                     5.31 |                -12.13 |               14 |                     -1.96 |                        -3.67 |                                 1 |                 36 |               86.11 |                 10.23 |                     7.83 |                -12.13 |                   3.42 |                      2.52 |                14.11 |
| threshold:2.5:mature       |                 54 |               68.52 |                  5.61 |                     3.23 |                -14.24 |               17 |                     -3.22 |                        -4.7  |                                 1 |                 37 |               83.78 |                  9.67 |                     7.44 |                -12.13 |                   4.06 |                      4.21 |                15.26 |
| threshold:3.0:mature       |                 54 |               68.52 |                  5.61 |                     3.23 |                -14.24 |               17 |                     -3.22 |                        -4.7  |                                 1 |                 37 |               83.78 |                  9.67 |                     7.44 |                -12.13 |                   4.06 |                      4.21 |                15.26 |
| threshold:none:mature      |                 74 |               58.11 |                  3.23 |                     2.61 |                -18.38 |               24 |                     -3.86 |                        -4.5  |                                 1 |                 50 |               68    |                  6.63 |                     4.26 |                -18.38 |                   3.4  |                      1.65 |                 9.89 |

## 输出文件

- `combined_risk_robustness_features.csv`
- `combined_risk_robustness_scan.csv`
- `recommended_rule_cross_sample.csv`
- `recommended_rule_failure_cases.csv`
- `summary.json`

## 结论

`risk_count_R1_R5>=2` 在核心成熟样本上方向仍然有效，但在更宽样本中存在误杀和样本依赖。建议继续作为 S04 观察型风险模块，不直接升级成 S01 默认硬过滤。
