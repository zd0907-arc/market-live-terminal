# 共用样本定义

## 研究窗口

当前首轮研究窗口：`2026-03-02 ~ 2026-04-24`。

原因：该窗口内 `atomic_trade_daily` 与 `atomic_order_daily` 都较完整，可同时研究 L2 成交资金和挂单行为。

## 正样本

定义：

```text
任意锚点后 5~40 个交易日内最高涨幅 >= 50%
且锚点日成交额 >= 3亿
```

用途：研究真正走出趋势的票在启动前、启动中、回调中、出货前的共同特征。

当前脚本：

`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/backend/scripts/research_trend_sample_factors.py`

输出：

`/Users/dong/Desktop/AIGC/market-live-terminal-selection-strategy-rework/docs/strategy-rework/experiments/20260426-trend-factor-research/trend_factor_samples.csv`

## 负样本

定义：

```text
目标日存在异动：涨幅 >=4% 或成交额异常 >=1.6 或突破前20日高点 >=1%
但后续 5~40 日最高涨幅只有 10%~35%
且 10日收益 <=3%
```

用途：对比“假启动/一日游/拉高回落”与“真趋势”的差异。

## 当前样本数

- 正样本：134
- 负样本：653
