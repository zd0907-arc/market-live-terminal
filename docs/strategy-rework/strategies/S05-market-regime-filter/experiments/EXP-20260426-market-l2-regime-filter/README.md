# EXP-20260426-market-l2-regime-filter

## 1. 问题
验证全市场 L2 资金环境过滤是否能提升 S01-M04B。

## 2. 假设
如果全市场 L2 主力资金连续净流出，次日/信号日暂停开仓，可能减少逆风交易。

## 3. 数据范围
- 全市场日频原子数据：2026-03-02 ~ 2026-04-24。
- 交易样本：S01-M04B（旧 v1.4-balanced）全市场 Top10 回测交易。

## 4. 样本口径
- 主判断使用成熟交易：买入后至少还有 10 个交易日数据。
- 环境只使用交易日前已知日频市场 L2 聚合状态。

## 5. 规则/参数
扫描：主力/超大单连续 2/3 日净流出、20% 分位弱环境、主力+超大单组合；锚点包括发现日、买入信号日、买入信号日前一交易日。

## 6. 输出文件
- daily_market_regime.csv
- regime_filter_scan.csv
- filtered_trade_impact.csv
- summary.json

## 7. 核心结果
- 基线成熟交易：41 笔，胜率 78.05%，平均 8.44%，中位 5.72%，最大亏损 -12.13%。
- 最优扫描：`main_outflow_2d` @ `discovery_date`；保留 10 笔，跳过 31 笔，胜率 60.0%，平均 13.62%，中位 5.72%，最大亏损 -4.7%。

| rule                      | anchor                 |   kept_mature_trade_count |   skipped_mature_trade_count |   kept_win_rate_pct |   kept_avg_net_return_pct |   kept_median_net_return_pct |   kept_min_net_return_pct |   avg_return_delta_pct |   median_return_delta_pct |   win_rate_delta_pct |
|:--------------------------|:-----------------------|--------------------------:|-----------------------------:|--------------------:|--------------------------:|-----------------------------:|--------------------------:|-----------------------:|--------------------------:|---------------------:|
| main_outflow_2d           | discovery_date         |                        10 |                           31 |               60    |                     13.62 |                         5.72 |                     -4.7  |                   5.18 |                      0    |               -18.05 |
| main_outflow_3d           | discovery_date         |                        10 |                           31 |               60    |                     13.62 |                         5.72 |                     -4.7  |                   5.18 |                      0    |               -18.05 |
| super_outflow_2d          | discovery_date         |                        23 |                           18 |               78.26 |                     10.11 |                         7.44 |                    -12.13 |                   1.67 |                      1.72 |                 0.21 |
| main_and_super_outflow_2d | discovery_date         |                        23 |                           18 |               78.26 |                     10.11 |                         7.44 |                    -12.13 |                   1.67 |                      1.72 |                 0.21 |
| main_below_q20            | prev_entry_signal_date |                        24 |                           17 |               75    |                      9.99 |                         5.72 |                    -12.13 |                   1.55 |                      0    |                -3.05 |
| super_below_q20           | prev_entry_signal_date |                        24 |                           17 |               75    |                      9.99 |                         5.72 |                    -12.13 |                   1.55 |                      0    |                -3.05 |
| super_outflow_2d          | prev_entry_signal_date |                        35 |                            6 |               80    |                      9.97 |                         8.21 |                    -11.08 |                   1.53 |                      2.49 |                 1.95 |
| main_and_super_outflow_2d | prev_entry_signal_date |                        35 |                            6 |               80    |                      9.97 |                         8.21 |                    -11.08 |                   1.53 |                      2.49 |                 1.95 |

## 8. 结论：继续观察
不建议直接纳入 S05 作为 S01 默认开关。主力净流出在本区间过于常见，发现日主力连续流出会跳过 31/41 笔成熟交易且胜率下降；买入信号日前一日的主力连续流出也降低平均收益。可继续跟踪超大单连续流出或信号日主力连续流出的风控价值，但需跨月份验证。
