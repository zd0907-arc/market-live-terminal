# 策略目录索引

## 新规则

策略目录按“策略族”管理，不按随手版本名管理。

```text
strategies/
  S01-capital-trend-reversal/          # 资金流趋势反转
  S02-capital-breakout-continuation/   # 资金流突破中继/二波
  S03-news-event-revaluation/          # 消息事件重估
  S04-capital-exit-risk/               # 出货/风险识别
  S05-market-regime-filter/            # 市场环境过滤
```

## 当前实际路径

历史文件暂时仍在：

```text
strategies/v1-trend-reversal-confirmation/
```

它等价于新体系里的：

```text
S01-capital-trend-reversal
```

后续新实验优先放到新策略族路径；旧路径只作为历史归档和映射。

## 当前主候选

```text
策略族：S01-capital-trend-reversal
方法：S01-M04B-balanced-weak-launch-filter
中文名：资金流趋势反转 / 均衡弱启动过滤
```

## 版本映射

详见：

```text
docs/strategy-rework/strategy-taxonomy.md
```
