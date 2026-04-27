# REQ-20260427-02-selection-trend-continuation-strategy-ui

- 标题：选股页接入“趋势中继高质量回踩”策略
- 状态：DONE

## 结论

把当前趋势中继候选版接入选股页下拉框。

页面显示名：

```text
趋势中继高质量回踩
```

内部 ID：

```text
trend_continuation_callback
```

## 策略范围

当前只适用于完整 L2 挂单数据区间。

目前验证区间：

```text
2026-03-02 ~ 2026-04-24
```

## 策略逻辑

```text
强趋势观察池
+ 严格高质量回踩
+ 确认日主动买入强度 > 0
+ 确认日主力净流入比例 >= 0
+ 单日大额超大单派发退出
```

## 页面要求

候选列表同时展示：

```text
观察中：进入趋势中继观察池，但还不能买。
可买入：已经触发严格高质量回踩确认。
```

日常使用方式：

```text
先看观察池，知道哪些票在趋势中继雷达里；
只有状态变成“可买入”时，才是策略买点。
```

## 验收结果

当前研究口径：

| 交易数 | 胜率 | 平均收益 | 中位收益 | 最低收益 |
|---:|---:|---:|---:|---:|
| 7 | 100.00% | 20.19% | 19.36% | 3.93% |

## 代码结果

已完成：

```text
backend/app/services/selection_trend_continuation.py
/selection/candidates?strategy=trend_continuation_callback
/selection/trade-dates?strategy=trend_continuation_callback
/selection/profile/{symbol}?strategy=trend_continuation_callback
/selection/trend-continuation/evaluate
前端下拉框新增：趋势中继高质量回踩
```
