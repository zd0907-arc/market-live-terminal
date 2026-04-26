# EXP-20260426-S01-M05-conservative-combined-risk

## 问题

把 S04 组合风险规则作为一个明确的 S01 实验方法版本，验证：

```text
S01-M05 = S01-M04B + 组合风险 >=2 时不进场
```

## 策略定义

基础策略：`S01-M04B-balanced-weak-launch-filter`。

新增过滤：

```text
risk_count_R1_R5 >= 2
```

也就是以下 5 个风险信号中同时出现至少 2 个：

- R1：启动期撤买/新增买接近异常防线。
- R2：启动期 OIB/CVD 背离。
- R3：确认日出货分偏高。
- R4：确认日超大单和主力同时为负。
- R5：弱启动 + 回调承接差。

## 结果

| strategy_method   |   full_trade_count |   full_win_rate_pct |   full_avg_net_return_pct |   full_median_net_return_pct |   full_max_net_return_pct |   full_min_net_return_pct |   full_sum_net_return_pct |   full_big_winner_gt_15_count |   full_big_loss_le_-8_count |   mature_trade_count |   mature_win_rate_pct |   mature_avg_net_return_pct |   mature_median_net_return_pct |   mature_max_net_return_pct |   mature_min_net_return_pct |   mature_sum_net_return_pct |   mature_big_winner_gt_15_count |   mature_big_loss_le_-8_count |
|:------------------|-------------------:|--------------------:|--------------------------:|-----------------------------:|--------------------------:|--------------------------:|--------------------------:|------------------------------:|----------------------------:|---------------------:|----------------------:|----------------------------:|-------------------------------:|----------------------------:|----------------------------:|----------------------------:|--------------------------------:|------------------------------:|
| S01-M04B          |                 65 |               60    |                      5.08 |                         3.2  |                      62.3 |                    -13.07 |                    330.23 |                            11 |                           8 |                   41 |                 78.05 |                        8.44 |                           5.72 |                        62.3 |                      -12.13 |                      346.19 |                              11 |                             3 |
| S01-M05           |                 57 |               66.67 |                      6.75 |                         5.29 |                      62.3 |                    -12.13 |                    384.84 |                            11 |                           4 |                   35 |                 88.57 |                       10.76 |                           8.21 |                        62.3 |                      -12.13 |                      376.45 |                              11 |                             1 |
| S04-filtered-out  |                  8 |               12.5  |                     -6.83 |                        -7.87 |                       1.8 |                    -13.07 |                    -54.61 |                             0 |                           4 |                    6 |                 16.67 |                       -5.04 |                          -4.7  |                         1.8 |                      -11.08 |                      -30.26 |                               0 |                             2 |

## 解释

- `avg_net_return_pct`：平均净收益率，不是金额。
- `median_net_return_pct`：中位净收益率，更能避免被单只大牛扭曲。
- `S04-filtered-out`：被 M05 排除的交易。如果这组整体为负，说明过滤有价值。

## 阶段结论

按当前 2026-03~04 的 L2 挂单样本，M05 明显优于 M04B：胜率、平均净收益率、中位净收益率均提升，且没有过滤掉成熟样本里的 >15% 大赢家。

但 full 口径仍有未来数据不足的交易，且挂单数据只有两个月，所以建议先作为实验策略/稳健模式，不直接覆盖主策略。

## 输出文件

- `s01_m05_comparison.csv`
- `s01_m05_trades.csv`
- `s04_combined_risk_filtered_trades.csv`
- `s01_m04b_base_trades_with_risk.csv`
- `summary.json`
