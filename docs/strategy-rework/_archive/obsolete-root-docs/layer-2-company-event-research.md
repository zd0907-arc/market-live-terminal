# Layer 2：公司研究 + 事件解释层

## 1. 定位

公司研究 + 事件解释层回答两个问题：

```text
这家公司为什么值得被资金炒？
这次量化信号背后有没有足够强的公司/事件/题材逻辑？
```

它不是纯新闻摘要，也不是直接替代买卖模型。它负责让用户在晚间复盘时快速理解候选票。

## 2. 输入

来自 Layer 1：

- 候选股票
- 信号日期
- 候选类型
- 量化理由
- 风险提示

需要补充的数据：

- 公司基本信息
- 主营业务
- 财报/业绩预告
- 公告
- 互动问答/董秘回复
- 投资者关系活动
- 新闻资讯
- 行业/题材标签
- 龙虎榜/交易公开信息
- 研报或公开解读，如后续接入

## 3. 时间点约束

历史回放必须遵守：

```text
只能使用 signal_date 当时已经可见的信息
```

示例：选择 `2026-03-02`，则事件层只允许使用：

```text
published_at <= 2026-03-02 收盘后可见时间
```

禁止使用未来新闻解释过去信号。

如果数据缺失，必须输出：

```text
event_context_missing = true
```

## 4. 数据源现状

当前已有能力但不完整：

- `stock_events`
- `stock_event_entities`
- `stock_event_daily_rollup`
- `sentiment_events`
- `sentiment_daily_scores`
- `stock_symbol_aliases`

当前 v0.1 实验实现已经接入：

- `stock_universe_meta`：名称、市值、时间截面。
- `stock_events`：正式事件时间线，按 `published_at <= signal_date` 截断。
- `sentiment_events`：股吧/情绪事件时间线，按 `pub_time <= signal_date` 截断。
- `sentiment_daily_scores`：最近一个不晚于 `signal_date` 的情绪摘要快照。

当前缺口：

- `stock_events` 目前正式库为空。
- `sentiment_daily_scores` 覆盖极少。
- 公司主营、财务、题材、龙虎榜需要继续补齐。

## 5. 输出卡片

### 5.1 公司一句话画像

输出：

```text
公司原主营是什么，现在市场关注它什么，新变化是什么。
```

示例形态：

```text
利通电子原以消费电子结构件/背板业务为主，盈利能力弱；近期市场核心关注点转向算力租赁业务扩张及利润弹性。
```

### 5.2 业务与利润来源

输出：

- 主营收入构成。
- 主要利润来源。
- 新业务/转型业务。
- 利润弹性来自哪里。
- 是否有数量、价格、产能、出租率、订单等可量化线索。

### 5.3 近期事件时间线

按时间列出：

- 公告
- 财报
- 业绩预告
- 互动问答
- 投资者关系活动
- 媒体资讯
- 龙虎榜

每条事件标记：

```text
事件时间、来源、事件类型、摘要、与当前上涨逻辑的关系
```

### 5.4 题材与板块映射

输出：

- 所属题材。
- 当前市场是否处于主线。
- 是否有板块共振。
- 是否有同题材标杆股。
- 是短线题材还是中期产业逻辑。

### 5.5 估值弹性粗算

目的：帮助用户理解“市场为什么可能重估”。

输出结构：

```text
关键假设：新增利润 / 订单 / 产能 / 价格
估算逻辑：利润 × 合理估值倍数
目标市值区间：低/中/高情景
当前市值位置：是否仍有空间
不确定性：假设来源、兑现风险
```

注意：

- 这是辅助研究，不是精确估值。
- 必须展示假设，不可给黑箱结论。

### 5.6 资金行为与公司逻辑一致性

输出：

| 一致性 | 含义 |
| --- | --- |
| `confirmed` | 事件/公司逻辑强，且 L2 资金同步验证 |
| `funds_only` | 资金强，但公司/事件逻辑弱，偏情绪或一日游 |
| `logic_only` | 公司逻辑强，但资金尚未确认，适合观察 |
| `conflict` | 新闻逻辑与资金行为矛盾，谨慎 |
| `unknown` | 事件数据不足 |

### 5.7 LLM 固定判定模板

大模型应按固定套路输出，而不是自由发挥。

建议问题：

1. 这家公司主营是什么？最近是否发生业务变化？
2. 当前候选信号能被哪些已知事件解释？
3. 事件属于短线刺激，还是可能形成中期逻辑？
4. 如果形成中期逻辑，利润或估值弹性来自哪里？
5. 当前资金行为是否验证该逻辑？
6. 最大风险是什么？
7. 对交易状态的建议是什么：可进场、等洗盘、只观察、不参与？

## 6. 结构化输出

建议输出：

```json
{
  "symbol": "sh603629",
  "trade_date": "2026-03-02",
  "company_profile": "...",
  "business_summary": "...",
  "core_thesis": "算力租赁转型带来利润重估",
  "event_strength": "strong",
  "event_duration": "medium_term",
  "theme_tags": ["算力", "AI", "业务转型"],
  "valuation_elasticity": {
    "has_estimate": true,
    "key_assumptions": ["算力出租率", "单匹租金", "净利率"],
    "rough_market_cap_range": "...",
    "uncertainty": "..."
  },
  "fundamental_funding_consistency": "confirmed",
  "llm_action_hint": "can_enter_or_wait_shakeout",
  "confidence": 0.72,
  "risk_points": ["估值已提前反映", "算力出租率不确定"],
  "tracking_points": ["后续财报扣非利润", "算力规模变化", "龙虎榜资金持续性"]
}
```

当前 v0.1 已落地字段：

```json
{
  "symbol": "sh603629",
  "trade_date": "2026-02-27",
  "name": "利通电子",
  "market_cap": null,
  "company_profile": "...",
  "business_summary": "...",
  "core_thesis": "...",
  "event_strength": "weak|medium|strong",
  "event_duration": "short_term|medium_term",
  "theme_tags": ["算力", "AI"],
  "fundamental_funding_consistency": "confirmed|funds_only|unknown",
  "action_hint": "observe_only|review_for_entry|review_with_caution",
  "llm_action_hint": "同 action_hint",
  "sentiment_snapshot": {
    "available": true,
    "trade_date": "2026-02-23",
    "sample_count": 14,
    "sentiment_score": 45.0,
    "direction_label": "偏多",
    "summary_text": "..."
  },
  "event_timeline": []
}
```

## 7. 与交易状态层关系

公司研究层影响交易状态层的置信度和持有策略：

| 公司/事件质量 | 对交易层影响 |
| --- | --- |
| 中期逻辑强 + 资金确认 | 可提高持有容忍度 |
| 短线事件 + 资金不持续 | 缩短持有周期，快进快出 |
| 突发事件强但资金未确认 | 等洗盘/二次确认 |
| 逻辑证伪 | 降低持有置信度 |
| 数据缺失 | 不加分，保持量化默认风控 |
