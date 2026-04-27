# v1.3 后复盘：误杀与剩余亏损

基于全市场稳健性验证结果，重点看两件事：

1. 阈值 1.5 过滤掉的票里，有没有误杀大牛。
2. 阈值 1.5 保留下来的成熟交易里，剩余大亏票还有什么共同特征。

## 1. 阈值 1.5 的误杀情况

- 被阈值 1.5 过滤且原本会触发交易：30 笔
- 其中净收益 >= 10%：3 笔
- 其中净收益 <= -8%：14 笔
- 被过滤交易原始平均收益：-3.39%
- 被过滤交易原始中位收益：-7.72%

被误杀的大赚票数量不多，但包含一笔大牛。当前更合理的判断是：先接受这类误杀，因为这批被过滤交易整体收益为负。

## 2. 剩余大亏票 vs 保留大赚票

| feature                              |   group_a_median |   group_b_median |   a_minus_b_median |   group_a_mean |   group_b_mean |
|:-------------------------------------|-----------------:|-----------------:|-------------------:|---------------:|---------------:|
| confirm_distribution_score           |        50.4      |        35.66     |          14.74     |      42.4667   |      36.0494   |
| launch3_ob_active_buy_strength_avg   |         7.22311  |         2.90767  |           4.31545  |       5.96828  |       3.56798  |
| setup_score                          |        88.075    |        92.01     |          -3.935    |      86.5717   |      90.6939   |
| launch3_return_pct                   |         4.79     |         7.03     |          -2.24     |       4.92333  |       7.48     |
| pullback_day_ob_oib_cvd_gap          |        -0.11194  |         0.0553   |          -0.16724  |       0.015578 |       0.225302 |
| launch_cancel_buy_to_add_buy_vs_hist |         1.12     |         1.0011   |           0.1189   |       0.979517 |       0.924633 |
| pullback_day_ob_support_spread_avg   |        -0.058585 |         0.024525 |          -0.08311  |       0.052923 |       0.194637 |
| launch3_ob_oib_cvd_gap               |        -0.08681  |        -0.00959  |          -0.07722  |       0.050133 |      -0.023862 |
| pullback_day_ob_cvd_ratio            |         0.05716  |        -0.01557  |           0.07273  |       0.03735  |      -0.030662 |
| pullback_support_spread_avg          |        -0.04877  |         0.022955 |          -0.071725 |       0.058402 |       0.072278 |
| pullback_main_net_ratio              |         0.095175 |         0.03364  |           0.061535 |       0.083995 |       0.034312 |
| launch3_main_net_ratio               |         0.0714   |         0.02498  |           0.04642  |       0.064853 |       0.035877 |

剩余大亏票的明显特征：启动 3 日涨幅偏弱、确认日出货分偏高，部分伴随回调承接为负。

## 3. 下一条规则 What-if

| rule                                                              |   filtered_count |   filtered_loss_le_-8 |   filtered_win_ge_10 |   filtered_avg_return |   kept_count |   kept_win_rate |   kept_avg_return |   kept_median_return |   kept_min_return |   kept_sum_return |
|:------------------------------------------------------------------|-----------------:|----------------------:|---------------------:|----------------------:|-------------:|----------------:|------------------:|---------------------:|------------------:|------------------:|
| launch_ret_lt_6                                                   |               26 |                     6 |                    4 |                  3.85 |           22 |           77.27 |             11.18 |                10.1  |             -5.61 |            246    |
| confirm_dist_gte_50                                               |               13 |                     4 |                    2 |                  4.34 |           35 |           82.86 |              8.27 |                 5.75 |            -12.13 |            289.57 |
| launch_ret_lt_6_and_confirm_dist_gte_50                           |               11 |                     4 |                    2 |                  4.51 |           37 |           81.08 |              8.01 |                 5.75 |            -12.13 |            296.46 |
| launch_ret_lt_6_and_pullback_support_lt_0                         |               16 |                     4 |                    2 |                  1.81 |           32 |           75    |              9.91 |                 9.16 |            -12.13 |            317.09 |
| pullback_support_lt_0_and_confirm_dist_gte_45                     |                8 |                     3 |                    2 |                  2.08 |           40 |           77.5  |              8.23 |                 5.72 |            -12.13 |            329.38 |
| launch_ret_lt_6_and_pullback_support_lt_0_and_confirm_dist_gte_45 |                7 |                     3 |                    1 |                 -0.02 |           41 |           78.05 |              8.44 |                 5.72 |            -12.13 |            346.19 |

## 初步建议

不要马上修正 v1.3 的阈值 1.5；它虽然误杀少数赢家，但整体过滤收益为正。

下一步可以尝试 v1.4：在 v1.3 后增加“弱启动过滤”，优先测试：

```text
launch3_return_pct < 6
```

这条规则会显著减少剩余大亏，但也会明显减少交易数，属于更激进的高质量模式。

## 文件

- threshold_1_5_would_filter_trades.csv
- threshold_1_5_false_killed_winners.csv
- threshold_1_5_correctly_filtered_losses.csv
- threshold_1_5_mature_kept_trades_enriched.csv
- threshold_1_5_remaining_losses.csv
- false_killed_winners_vs_filtered_losses_diff.csv
- remaining_losses_vs_kept_winners_diff.csv
- next_rule_what_if_scan.csv
- summary.json
