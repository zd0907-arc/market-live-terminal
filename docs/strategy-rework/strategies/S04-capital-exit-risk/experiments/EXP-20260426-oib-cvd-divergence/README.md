# EXP-20260426-oib-cvd-divergence：OIB 与 CVD 背离验证

## 1. 问题
验证“盘口看起来买方强（OIB 为正），但主动成交 CVD 弱或负”是否能识别假托真砸/诱多，是否值得加入 S04 或反向过滤 S01。

## 2. 假设
如果启动期或回调确认日出现 `sum(oib_delta_amount) > 0 且 sum(cvd_delta_amount) <= 0`，说明挂单买盘强但主动成交不跟，亏损票中应更常见，且简单过滤应能少误杀大赢家。

## 3. 数据范围
- 原子日线窗口：2026-01-01 ~ 2026-04-24
- 候选发现日：2026-03-02 ~ 2026-04-24
- 成熟交易：买入后至少还有 10 个交易日数据。

## 4. 样本口径
- `v1.3-threshold-1.5`：v1.3 稳健性扫描中阈值 1.5 的成熟交易。
- `v1.4-balanced`：v1.4 双模式中 balanced 的成熟交易。
- 分别对亏损票/亏损前10、盈利票/盈利前10做对比。

## 5. 规则/参数
- 启动窗口：`launch_start_date ~ launch_end_date`，通常为启动 3 日。
- 回调确认日：`pullback_confirm_date` 单日。
- 背离：窗口内 `sum(oib_delta_amount) > 0` 且 `sum(cvd_delta_amount) <= 0`。
- 比值：`oib_sum / abs(cvd_sum)`，`cvd_sum` 近零时置空，避免除零。
- 规则扫描只验证简单过滤，不改线上策略。

## 6. 输出文件
- `summary.json`
- `oib_cvd_loss_win_diff.csv`
- `divergence_rule_scan.csv`
- `oib_cvd_trade_enriched.csv`（辅助明细）

## 7. 核心结果

| sample_version     | group         |   count |   win_rate_pct |   avg_net_return_pct |   median_net_return_pct |   avg_next_day_return_pct |   launch_divergence_rate_pct |   confirm_divergence_rate_pct |   any_divergence_rate_pct |   median_launch_oib_cvd_diff |   median_confirm_oib_cvd_diff |
|:-------------------|:--------------|--------:|---------------:|---------------------:|------------------------:|--------------------------:|-----------------------------:|------------------------------:|--------------------------:|-----------------------------:|------------------------------:|
| v1.3-threshold-1.5 | loss_all      |      13 |              0 |                -6.6  |                   -5.61 |                     -3.58 |                        30.77 |                         38.46 |                     53.85 |                 -1.43821e+08 |                   5.68425e+07 |
| v1.3-threshold-1.5 | loss_bottom10 |      10 |              0 |                -7.93 |                   -8.88 |                     -4.2  |                        40    |                         40    |                     60    |                 -1.81035e+08 |                  -3.25379e+07 |
| v1.3-threshold-1.5 | win_all       |      35 |            100 |                12.34 |                   10.1  |                      1.07 |                        14.29 |                         40    |                     45.71 |                 -2.8876e+07  |                   5.71137e+07 |
| v1.3-threshold-1.5 | win_top10     |      10 |            100 |                26.6  |                   22.82 |                      3.47 |                        10    |                         40    |                     40    |                 -1.47996e+08 |                   4.62779e+07 |
| v1.4-balanced      | loss_all      |       9 |              0 |                -6.27 |                   -4.7  |                     -3.41 |                        44.44 |                         55.56 |                     77.78 |                 -5.84782e+07 |                   8.29398e+07 |
| v1.4-balanced      | loss_bottom10 |       9 |              0 |                -6.27 |                   -4.7  |                     -3.41 |                        44.44 |                         55.56 |                     77.78 |                 -5.84782e+07 |                   8.29398e+07 |
| v1.4-balanced      | win_all       |      32 |            100 |                12.58 |                   10.1  |                      0.98 |                        15.62 |                         43.75 |                     50    |                 -2.8876e+07  |                   5.71137e+07 |
| v1.4-balanced      | win_top10     |      10 |            100 |                26.29 |                   22.58 |                      3.1  |                        10    |                         50    |                     50    |                 -1.0261e+08  |                   4.62779e+07 |

### v1.4-balanced 规则扫描前 8 行

| sample_version   | rule_name                                       |   total_trades |   filtered_count |   filtered_loss_count |   filtered_win_count |   filtered_bottom10_loss_count |   filtered_top10_winner_count |   loss_capture_rate_pct |   win_kill_rate_pct |   top10_kill_rate_pct |   kept_count |   kept_win_rate_pct |   kept_avg_net_return_pct |   kept_median_net_return_pct |   kept_max_loss_pct |
|:-----------------|:------------------------------------------------|---------------:|-----------------:|----------------------:|---------------------:|-------------------------------:|------------------------------:|------------------------:|--------------------:|----------------------:|-------------:|--------------------:|--------------------------:|-----------------------------:|--------------------:|
| v1.4-balanced    | any_launch_or_confirm_divergence                |             41 |               23 |                     7 |                   16 |                              7 |                             5 |                   77.78 |               50    |                    50 |           18 |               88.89 |                      8.46 |                         3.23 |               -5.61 |
| v1.4-balanced    | confirm_diff_gt_q50_78270564                    |             41 |               15 |                     6 |                    9 |                              7 |                             4 |                   66.67 |               28.12 |                    40 |           26 |               88.46 |                      9.44 |                         7.91 |              -11.08 |
| v1.4-balanced    | confirm_divergence                              |             41 |               19 |                     5 |                   14 |                              5 |                             5 |                   55.56 |               43.75 |                    50 |           22 |               81.82 |                      6.96 |                         3.23 |              -12.13 |
| v1.4-balanced    | launch_divergence                               |             41 |                9 |                     4 |                    5 |                              4 |                             1 |                   44.44 |               15.62 |                    10 |           32 |               84.38 |                      9.8  |                         5.72 |              -11.03 |
| v1.4-balanced    | confirm_divergence_and_diff_gt_div_q50_73601340 |             41 |                9 |                     4 |                    5 |                              4 |                             2 |                   44.44 |               15.62 |                    20 |           32 |               84.38 |                      9.15 |                         5.72 |              -12.13 |
| v1.4-balanced    | launch_diff_gt_q50_319333120                    |             41 |                8 |                     3 |                    5 |                              3 |                             2 |                   33.33 |               15.62 |                    20 |           33 |               81.82 |                      9.03 |                         5.72 |              -11.03 |
| v1.4-balanced    | both_launch_and_confirm_divergence              |             41 |                5 |                     2 |                    3 |                              2 |                             1 |                   22.22 |                9.38 |                    10 |           36 |               80.56 |                      8.74 |                         5.72 |              -12.13 |
| v1.4-balanced    | confirm_diff_gt_q75_158729482                   |             41 |                7 |                     2 |                    5 |                              2 |                             3 |                   22.22 |               15.62 |                    30 |           34 |               79.41 |                      7.63 |                         5.5  |              -11.08 |

## 8. 结论：继续观察，不直接采纳为 S01 硬过滤

OIB/CVD 背离在亏损票中有一定解释力，尤其可作为 S04 的风险标签；但在 v1.4-balanced 样本里，简单规则会同时过滤部分盈利票，且对 Top10 大赢家仍有误杀风险。建议先纳入 S04 观察型风险因子/案例解释，不纳入 S01 硬过滤；若后续扩大样本，可测试与弱启动、出货分、撤梯子共同触发。
