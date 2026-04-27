# 选股策略重构研究

## 当前结论

## 当前项目状态

最新状态见：

```text
project-status-20260427.md
```

核心结论：

```text
资金流回调稳健策略已接入系统。
趋势中继高质量回踩已接入系统。
页面默认入口已升级为“每日复盘决策”。
```


这里是“策略研究项目”的总入口。后续按：

```text
策略族 -> 方法版本 -> 实验
```

管理，不再用 `V2实验验证`、`VR discovery` 这类看不出业务含义的名字。


## 当前人话入口

如果只是想知道现在到底什么有用，先看：

```text
LONG_MEMORY.md                    # 策略研究长记忆
current-strategy-conclusion.md      # 当前策略结论
experiment-decision-log.md          # 实验采纳/不采纳登记
archive-index.md                    # 旧资料归档索引
```

对话和产品展示优先使用中文名：

```text
资金流回调稳健策略
组合风险模块
趋势中继策略
消息事件重估策略
```

编号如 `S01-M05` 只作为文件追溯用，不作为日常沟通名称。

## 核心文档

| 文档 | 用途 |
|---|---|
| `LONG_MEMORY.md` | 策略研究长记忆和当前总入口 |
| `strategy-taxonomy.md` | 策略族、版本、旧版本映射 |
| `research-governance.md` | 实验、版本升级、采纳规则 |
| `agent-workflow.md` | 主 Agent + 子 Agent 并行研究流程 |
| `experiment-template.md` | 新实验 README 模板 |
| `_shared/data-sources.md` | 共用数据源说明 |
| `_shared/sample-definition.md` | 共用样本定义 |
| `data-map-current.md` | 当前字段和业务含义 |
| `handoff-for-next-ai.md` | 给其他 AI 的交接背景 |
| `project-status-20260427.md` | 当前完成情况评估 |
| `review-page-user-story.md` | 复盘页面用户 Story 与优化空间 |

## 目录结构

```text
docs/strategy-rework/
  _shared/                 # 跨策略共用数据源/样本口径
  strategies/              # 策略族与版本实验
  _archive/                # 旧实验/过时文档归档
  cases/                   # 个股案例，如利通电子
  notes/                   # 对话记忆/临时沉淀
```

## 策略族规划

| 策略族 | 目标 |
|---|---|
| `S01-capital-trend-reversal` | 抓资金流背离、启动、回调承接后的趋势反转 |
| `S02-capital-breakout-continuation` | 抓已经涨过一段但资金没走的趋势中继/二波 |
| `S03-news-event-revaluation` | 抓消息、业绩、公司转型带来的重估 |
| `S04-capital-exit-risk` | 做出货、诱多、抢跑、风险退出识别 |
| `S05-market-regime-filter` | 判断市场环境是否适合开仓 |

## 当前主线

当前页面入口是：

```text
每日复盘决策
```

当前已接入两条策略：

```text
资金流回调稳健策略
趋势中继高质量回踩策略
```

旧 `v0-*`、`v1-*` 目录已归档到 `_archive/obsolete-strategy-dirs/`。

## 工作流

后续默认流程：

```text
主 Agent 和用户定方向
-> 拆成可验证假设
-> 子 Agent 并行跑实验
-> 每个实验独立留痕
-> 主 Agent 汇总决定是否纳入策略版本
```
