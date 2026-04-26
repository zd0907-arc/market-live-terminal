# v1.3 挂单过滤回测

本版在 v1.2 基础上，只增加一条启动期挂单诱多过滤。

## 过滤规则

```text
launch_cancel_buy_to_add_buy_vs_hist > 2
```

含义：启动期 `撤买单 / 新增买单` 相对该股历史均值放大超过 2 倍，认为有“撤梯子诱多”风险。

## 策略对比

| strategy   |   trade_count |   win_rate |   avg_return_pct |   median_return_pct |   max_return_pct |   min_return_pct |   avg_holding_days |   avg_gross_return_pct |   total_return_pct_signal_sum |
|:-----------|--------------:|-----------:|-----------------:|--------------------:|-----------------:|-----------------:|-------------------:|-----------------------:|------------------------------:|
| v1         |            82 |      52.44 |             2.11 |                0.97 |            59.71 |           -18.38 |               7.68 |                 nan    |                         nan   |
| v1.2       |            82 |      59.76 |             3.21 |                2.75 |            62.3  |           -18.38 |               8.39 |                 nan    |                         nan   |
| v1.3       |            58 |      72.41 |             6.3  |                5.31 |            62.3  |           -13.07 |               9.69 |                   6.83 |                         365.4 |

## 候选过滤

- 原始候选：220
- 过滤候选：28
- 保留候选：192

## 文件

- raw_candidates.csv
- filtered_candidates.csv
- passed_candidates.csv
- v1_3_trades.csv
- strategy_comparison.csv
- summary.json
