# 成交额发现层替代规则实验

## 问题

当前强势样本覆盖面窄，大量股票被 `2.5亿成交额硬门槛` 卡掉。本实验只替换发现层成交额规则，买点、组合风险过滤、出场逻辑保持不变。

## 测试规则

- `current_abs_250m`：当前硬门槛，成交额 >=2.5亿。
- `abs_100m`：简单放宽到 >=1亿。
- `hybrid_100m_rel`：>=1亿，且相对20日均额或60日分位有放大。
- `hybrid_80m_rel_or_abs`：>=8000万，且相对放量/高分位/或绝对达到2.5亿。
- `hybrid_60m_strong_rel`：>=6000万，但要求强相对放量。

## 核心结果

| liquidity_mode        |   candidate_rows |   mature_trade_count |   mature_win_rate |   mature_avg_return_pct |   mature_median_return_pct |   mature_min_return_pct |   top50_candidate_symbol_hit_count |   top50_trade_symbol_hit_count |   ge50_candidate_symbol_hit_count |   ge50_trade_symbol_hit_count |   ge30_candidate_symbol_hit_count |   ge30_trade_symbol_hit_count |
|:----------------------|-----------------:|---------------------:|------------------:|------------------------:|---------------------------:|------------------------:|-----------------------------------:|-------------------------------:|----------------------------------:|------------------------------:|----------------------------------:|------------------------------:|
| current_abs_250m      |              740 |                   65 |             73.85 |                    7.22 |                       5.3  |                  -12.13 |                                 10 |                              2 |                                47 |                             7 |                               129 |                            24 |
| abs_100m              |              740 |                   78 |             71.79 |                    7.19 |                       4.69 |                  -12.13 |                                 10 |                              2 |                                43 |                             7 |                               123 |                            23 |
| hybrid_100m_rel       |              740 |                   75 |             72    |                    6.97 |                       5.29 |                  -12.13 |                                 10 |                              2 |                                46 |                             7 |                               127 |                            24 |
| hybrid_80m_rel_or_abs |              740 |                   75 |             72    |                    6.97 |                       5.29 |                  -12.13 |                                 10 |                              2 |                                46 |                             7 |                               128 |                            25 |
| hybrid_60m_strong_rel |              667 |                   50 |             54    |                    1.24 |                       1.94 |                  -13.85 |                                  7 |                              0 |                                29 |                             3 |                               114 |                            20 |

## 输出文件

- `liquidity_variant_summary.csv`
- `base_candidate_pool.csv`
- `all_variant_candidates.csv`
- `all_variant_filtered.csv`
- `all_variant_trades.csv`
- `all_runup_opportunities.csv`
- `summary.json`
