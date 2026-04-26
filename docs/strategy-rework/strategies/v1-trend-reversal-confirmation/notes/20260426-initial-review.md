# 2026-04-26 v1 初版交易复盘

## 复盘对象

文件：

`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-initial/v1_trades.csv`

复盘增强输出：

`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/docs/strategy-rework/strategies/v1-trend-reversal-confirmation/experiments/20260426-initial-review`

## 基础结果

- 交易数：82
- 胜率：52.44%
- 平均收益：2.11%
- 中位收益：0.97%

## 重要结论

### 1. v1 的主要收益差异来自持有期资金是否持续，而不是入场前分数高低

入场前因子与最终收益相关性不强：

- `setup_score` 相关性约 `0.11`
- `pre20_super_price_divergence` 相关性约 `0.10`
- `pre5_super_price_divergence` 相关性约 `0.08`

这说明：

> v1 的发现逻辑能把胜率抬起来，但最终能赚多少，主要取决于买入后资金是否继续支持。

### 2. 持有期 L2 正向持续性很关键

盈利票 vs 亏损票：

| 因子 | 盈利均值 | 亏损均值 | 解释 |
|---|---:|---:|---|
| `hold_positive_l2_bar_ratio_avg` | 0.485 | 0.375 | 盈利票持有期 L2 正流入切片更多 |
| `hold_super_positive_day_ratio` | 0.483 | 0.282 | 盈利票超大单为正的天数更多 |
| `hold_main_positive_day_ratio` | 0.520 | 0.262 | 盈利票主力资金为正的天数更多 |
| `hold_active_buy_strength_avg` | -0.23 | -5.88 | 亏损票主动卖压明显更强 |
| `hold_support_spread_avg` | +0.012 | -0.027 | 盈利票持有期挂单承接更好 |

可转成下一版出场/持有因子。

### 3. 持有期累计资金比单日分数更适合做卖点

单因子过滤显示：

- `hold_super_net_ratio >= -0.0092` 后，胜率约 78%，中位收益约 6%。
- `hold_main_net_ratio >= -0.0197` 后，胜率约 78%，中位收益约 6%。
- `hold_positive_l2_bar_ratio_avg >= 0.4436` 后，胜率约 75.6%，中位收益约 6%。

这些不是入场前可用指标，但非常适合做持有过程中的动态出场条件。

### 4. 启动太猛未必更好

在 v1 交易池里：

- `launch3_main_net_ratio` 与最终收益相关性约 `-0.37`
- `launch3_super_net_ratio` 与最终收益相关性约 `-0.22`
- `launch3_return_pct` 与最终收益相关性约 `-0.16`

解释：

> v1 已经要求启动质量，如果启动 3 日过猛，反而可能后续空间变小或更容易洗下来。

下一版不应继续提高启动强度阈值，而应限制“启动过热”。

### 5. 从发现到买入阶段，如果主动买太强，反而可能不好

`discover_to_entry_active_buy_strength_avg` 与最终收益相关性约 `-0.25`。

解释：

> 如果发现后到买入前已经被主动买推得太明显，可能已经偏追高。

下一版可以增加：发现到买入期间涨幅/主动买过热降权。

### 6. 重复命中不是当前最大问题，但要记录

去掉同票重叠后：

- 交易数：57
- 胜率：50.88%
- 平均收益：2.87%
- 中位收益：0.97%

说明同票重复会影响交易数，但不是 v1 胜率改善的核心来源。

## 下一版可尝试的优化指标

### 持有增强/退出指标

1. `hold_super_positive_day_ratio`
2. `hold_main_positive_day_ratio`
3. `hold_positive_l2_bar_ratio_avg`
4. `hold_active_buy_strength_avg`
5. `hold_support_spread_avg`
6. `anchor_cum_super_net_ratio`
7. `anchor_cum_main_net_ratio`

### 入场前过热降权指标

1. `launch3_return_pct` 不宜过高。
2. `launch3_super_net_ratio` / `launch3_main_net_ratio` 过强要谨慎。
3. `discover_to_entry_return_pct` 过高要降权。
4. `discover_to_entry_active_buy_strength_avg` 过高要降权。

## 下一步建议

v1.1 不改发现逻辑主体，重点优化卖点和持有：

```text
买入后如果累计超大单/主力未明显转负，且正流入切片仍可接受，就继续持有；
如果累计资金转负 + 主动卖增强 + 挂单承接转弱，再卖。
```

同时加一个过热过滤：

```text
发现日至买入日前，如果涨幅过大或主动买过强，降低入场优先级。
```
