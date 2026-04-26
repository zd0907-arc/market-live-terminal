# EXP-20260426-sell-pressure-attribution：压单出货归因验证

## 1. 问题
验证 Gemini 提到的“新增卖挂单异常放大 + 支撑压力差严重为负”是否能解释 v1.3 阈值 1.5 后仍保留的亏损票，并区分 v1.3/v1.4 大赚票。

## 2. 假设
如果是泰山压顶/压单出货，亏损票在启动 3 日或回调确认日应出现：`add_sell_amount` 相对自身历史异常放大、`support_pressure_spread` 明显为负、`sell_pressure_ratio` 偏高。

## 3. 数据范围
- 发现日：2026-03-02 ~ 2026-04-24
- 回放到：2026-04-24
- 原子数据回看：2026-01-01 ~ 2026-04-24
- 交易结果：v1.3 阈值 1.5、v1.4-balanced、v1.4-quality 的成熟交易。

## 4. 样本口径
- v1.3 阈值 1.5 成熟交易：48 笔。
- v1.3 保留下来的亏损票：13 笔，重点看最亏前 10。
- v1.3/v1.4 大赚对照：净收益 >= 10%，共 49 行样本（不同模式同票会分别计入）。

## 5. 规则/参数
每个阶段计算：
- `add_sell_amount_vs_hist`：阶段新增卖挂单金额 / 该股前 20 个有挂单交易日的日均新增卖挂单金额（按阶段天数折算）。
- `add_sell_ratio_vs_hist`：阶段 `add_sell_amount / total_amount` 日均值相对历史日均倍数。
- `support_pressure_spread`：`buy_support_ratio - sell_pressure_ratio` 阶段均值。
- `sell_pressure_ratio`：阶段均值。

## 6. 输出文件
- `loss_vs_win_sell_pressure_diff.csv`：亏损票 vs 大赚票指标差异。
- `rule_scan.csv`：简单压单规则扫描。
- `summary.json`：程序可读摘要。

## 7. 核心结果

| feature                         |   loss_count |   win_count |   loss_mean |   loss_median |   win_mean |   win_median |   loss_minus_win_median |
|:--------------------------------|-------------:|------------:|------------:|--------------:|-----------:|-------------:|------------------------:|
| launch3_add_sell_amount_vs_hist |           13 |          49 |    1.09486  |      0.8184   |   1.10065  |     1.053    |               -0.2346   |
| confirm_add_sell_ratio          |           13 |          49 |    1.07176  |      1.06617  |   1.03912  |     0.875964 |                0.190204 |
| confirm_add_sell_amount_vs_hist |           13 |          49 |    1.13728  |      1.005    |   0.857518 |     0.8488   |                0.1562   |
| launch3_add_sell_ratio          |           13 |          49 |    1.02841  |      0.960774 |   1.05817  |     0.900053 |                0.060721 |
| launch3_sell_pressure_ratio     |           13 |          49 |    0.737302 |      0.56943  |   0.762925 |     0.520724 |                0.048706 |
| launch3_add_sell_ratio_vs_hist  |           13 |          49 |    0.808077 |      0.9245   |   0.974004 |     0.9687   |               -0.0442   |
| confirm_sell_pressure_ratio     |           13 |          49 |    0.73937  |      0.582844 |   0.731761 |     0.553989 |                0.028855 |
| confirm_support_pressure_spread |           13 |          49 |    0.042602 |      0.057882 |   0.215754 |     0.033202 |                0.02468  |
| confirm_add_sell_ratio_vs_hist  |           13 |          49 |    0.879592 |      0.9848   |   0.969743 |     0.9655   |                0.0193   |
| launch3_support_pressure_spread |           13 |          49 |    0.010237 |     -0.010127 |  -6.4e-05  |    -0.003502 |               -0.006625 |

规则扫描前 12：

| base                      | rule                                               |   filter_count |   filter_loss_count |   filter_loss_recall_pct |   filter_big_win_count |   filter_big_win_hit_pct |   filtered_avg_return |   kept_count |   kept_win_rate |   kept_avg_return |   kept_median_return |   kept_min_return |
|:--------------------------|:---------------------------------------------------|---------------:|--------------------:|-------------------------:|-----------------------:|-------------------------:|----------------------:|-------------:|----------------:|------------------:|---------------------:|------------------:|
| v1.3_threshold_1.5_mature | confirm_sell_pressure_ratio>=0.45                  |             47 |                  13 |                   100    |                     18 |                   100    |                  7.24 |            1 |          100    |              5.75 |                 5.75 |              5.75 |
| v1.3_threshold_1.5_mature | launch3_sell_pressure_ratio>=0.45                  |             48 |                  13 |                   100    |                     18 |                   100    |                  7.21 |            0 |            0    |              0    |                 0    |              0    |
| v1.3_threshold_1.5_mature | launch3_sell_pressure_ratio>=0.55                  |             33 |                   9 |                    69.23 |                      8 |                    44.44 |                  7.08 |           15 |           73.33 |              7.49 |                10.1  |            -11.08 |
| v1.3_threshold_1.5_mature | confirm_sell_pressure_ratio>=0.55                  |             34 |                   8 |                    61.54 |                     10 |                    55.56 |                  6.34 |           14 |           64.29 |              9.31 |                10.1  |            -11.08 |
| v1.3_threshold_1.5_mature | launch3_support_pressure_spread<=0.0               |             33 |                   8 |                    61.54 |                     12 |                    66.67 |                  6.76 |           15 |           66.67 |              8.19 |                 5.75 |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_support_pressure_spread<=0.0               |             21 |                   6 |                    46.15 |                      6 |                    33.33 |                  4.54 |           27 |           74.07 |              9.29 |                 7.44 |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_add_sell_amount_vs_hist>=1.2               |             11 |                   5 |                    38.46 |                      3 |                    16.67 |                  1.36 |           37 |           78.38 |              8.95 |                 5.72 |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_support_pressure_spread<=-0.05             |             14 |                   5 |                    38.46 |                      3 |                    16.67 |                  3.32 |           34 |           76.47 |              8.81 |                 6.6  |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_add_sell_amount_vs_hist>=1.5               |              7 |                   4 |                    30.77 |                      0 |                     0    |                 -3.05 |           41 |           78.05 |              8.96 |                 5.72 |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_add_sell_amount_vs_hist>=1.5_and_support<0 |              6 |                   4 |                    30.77 |                      0 |                     0    |                 -4.52 |           42 |           78.57 |              8.88 |                 5.73 |            -12.13 |
| v1.3_threshold_1.5_mature | launch3_support_pressure_spread<=-0.05             |             13 |                   4 |                    30.77 |                      3 |                    16.67 |                  7.61 |           35 |           74.29 |              7.06 |                 5.75 |            -12.13 |
| v1.3_threshold_1.5_mature | confirm_sell_pressure_ratio>=0.65                  |             21 |                   4 |                    30.77 |                      5 |                    27.78 |                  6.74 |           27 |           66.67 |              7.57 |                 7.44 |            -11.08 |

## 8. 结论：不采纳为硬过滤，继续观察
新增卖挂单异常和支撑压力差不能稳定地区分剩余亏损票与大赚票。单独看卖压会误杀较多赢家；组合 `add_sell_vs_hist + support<0` 后覆盖亏损又不足。当前不建议纳入 S01/S04 的硬规则，只保留为 S04 观察型风险标签。
