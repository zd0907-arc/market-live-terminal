# 策略族与命名体系

## 结论

后续不要再用 `V2实验验证`、`VR discovery`、`v1.4-balanced` 这类只体现迭代顺序、不体现业务含义的名字作为主入口。

采用三级结构：

```text
策略族 Strategy Family  ->  方法版本 Method Version  ->  实验 Experiment
```

## 策略族命名

策略族表示“这套策略要抓哪一类行情”，不是表示代码版本。

| 策略族 | 中文名 | 目标行情 | 当前状态 |
|---|---|---|---|
| `S01-capital-trend-reversal` | 资金流趋势反转 | 先有资金潜伏/背离，后启动，回调承接后买入 | 当前主线 |
| `S02-capital-breakout-continuation` | 资金流突破中继 | 已经涨过一段，但资金没走，继续走二波/趋势中继 | 待研究 |
| `S03-news-event-revaluation` | 消息事件重估 | 公司业务、业绩、题材、政策、供需变化驱动重估 | 待研究 |
| `S04-capital-exit-risk` | 资金撤退/风险规避 | 专门识别出货、抢跑、诱多、资金撤退 | 待研究，可被其他策略复用 |
| `S05-market-regime-filter` | 市场环境过滤 | 识别全市场顺风/逆风，控制是否开仓 | 待研究 |

## 方法版本命名

方法版本表示“同一个策略族内，核心逻辑如何变化”。

格式：

```text
S01-M01-baseline
S01-M02-cum-super-exit
S01-M03-orderbook-ladder-filter
S01-M04-balanced-weak-launch-filter
```

规则：

- `S01`：策略族编号。
- `M01`：方法版本编号，只在同一策略族内递增。
- 后缀必须写业务含义，不能只写 `v2`、`new`、`final`。
- 参数扫描不升级方法版本；只有核心业务逻辑变化才升级方法版本。

## 实验命名

实验表示“为了验证某个问题跑的一次研究”。

格式：

```text
EXP-YYYYMMDD-short-topic
```

例子：

```text
EXP-20260426-market-extreme-review
EXP-20260426-orderbook-ladder-attribution
EXP-20260426-cap-threshold-ablation
```

实验目录必须能回答五件事：

```text
为什么跑
用什么数据
改了什么/验证什么
结果如何
结论是否采纳
```

## 旧版本映射表

| 旧叫法 | 新归属 | 状态 | 说明 |
|---|---|---|---|
| `v0-lifecycle-baseline` | `LEGACY-L01-lifecycle-score` | 基线 | 旧生命周期打分，保留作对照 |
| `v1` | `S01-M01-baseline` | 历史版本 | 趋势反转确认基础版 |
| `v1.2` | `S01-M02-cum-super-exit` | 有效版本 | 只改出场，引入累计超大单峰值回撤 |
| `v1.3` | `S01-M03-orderbook-ladder-filter` | 有效版本 | 加启动期撤买单/新增买单异常过滤 |
| `v1.4-quality` | `S01-M04Q-quality-weak-launch-filter` | 候选模式 | 少交易、高质量模式 |
| `v1.4-balanced` | `S01-M04B-balanced-weak-launch-filter` | 当前主候选 | 均衡模式，暂作为 S01 主候选 |
| `v1.5` | `S01-E05-business-guards-prototype` | 实验未采纳 | ST/市值/冷却/早期资金失败验证，不能整体替代 M04B |

## 当前主策略入口

当前页面或离线回测如果需要一个默认策略，建议显示：

```text
S01 资金流趋势反转 / M04B 均衡弱启动过滤
```

不要显示：

```text
V2实验验证
VR discovery
v1.4-balanced
```
