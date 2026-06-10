# 市场环境门控页面接入方案

状态：开发前方案
日期：2026-06-11
目标端：Mac 本地研究站

## 先给结论

这次应该做两件事，但两者承担不同职责：

| 位置 | 目的 | 业务问题 |
|---|---|---|
| 独立研究页 | 证明这套门控为什么可信、有什么代价 | 市场好坏是否影响四个来源？拦截后少踩了多少坑？错过了什么？ |
| 选股工作台 | 给当天候选一个可执行的环境判断 | 今天能不能新开仓？这只票是环境允许、仅观察，还是暂停新开仓？ |

核心表达原则：

- 市场环境门控不是第五个选股来源，不改写四个来源的原始推荐。
- 它是覆盖层：先判断今天适不适合新开仓，再决定是否执行来源自己的买点。
- 被拦截不等于这只票差，而是“这只票今天不适合参与”。
- 买入点仍来自原来源规则；退出点仍来自原持仓/双轨卖点体系。市场环境只决定新开仓许可，不替代卖点。

## 现有页面结论

### Canonical Source

当前研究页体系的 canonical source 是：

- 入口：`src/components/selection/SelectionResearchPage.tsx` 顶部 `研究入口`
- 专题研究页壳：`src/components/selection/SparkPatternResearchPage.tsx`
- 研究卡片壳：`src/components/common/ResearchCard.tsx`

市场环境门控研究页应复用这个结构，不另起一套入口。

### Affected Surfaces

| 页面/组件 | 影响 |
|---|---|
| `SelectionResearchPage.tsx` | 顶部市场水位卡、研究入口菜单、左侧候选环境标签 |
| `SelectionDecisionPanel.tsx` | 右侧单票入场结论、信号链路、买点/退出点解释 |
| `selectionService.ts` / `types.ts` | 新增市场环境和门控字段 |
| 新研究页 | 展示研究结论、门控效果、被拦截候选复盘 |

### Parity Risk

- 不要把市场环境页做成另一个“回测收益榜”，否则会和 PPO/交易复盘页语义混淆。
- 不要把市场门控字段覆盖 `entry_allowed` 的原始含义，否则后续无法区分“来源规则拦截”和“环境拦截”。
- 不要在选股首页放太多研究表格，日常入口只需要判断今天怎么做。

## 一、独立研究页方案

### 页面名称与入口

建议新增：

```text
市场环境门控研究页
```

入口位置：

```text
/selection-research -> 顶部“研究入口”下拉菜单
```

菜单说明：

```text
展示市场水位如何影响四个候选来源，以及被拦截候选后续 5/10 日表现。
```

### 页面结构

研究页不做成长篇 Markdown，而做成可交互专题页：

1. 结论卡
2. 市场水位时间轴
3. 周期选择证据
4. 来源 x 市场状态矩阵
5. 被拦截候选复盘
6. 单票固定窗口图

### 1. 结论卡

第一屏只回答四句话：

```text
整体候选池：市场好时短线更好，市场差时更容易痛苦持仓。
星火机会模型：相关性最清楚，弱市不建议给高分例外。
资金流回调稳健策略：方向支持，但样本还不够硬。
试盘识别、趋势延续策略：样本不足或快照断更，不能下最终结论。
```

同时给出三类指标：

| 指标 | 示例 |
|---|---|
| 主门控周期 | 5 日 |
| 预警周期 | 3 日 |
| 确认周期 | 10 日 |

### 2. 市场水位时间轴

字段来源：`market_state_daily.csv`

展示：

- `water_score` 折线。
- 背景色区分攻击、谨慎、防守。
- tooltip 显示 `market_detail_label`、`default_action`、`reason_top3`。

业务目的：

```text
让用户看到水位是在修复，还是继续下沉。
```

### 3. 周期选择证据

字段来源：

- `market_metric_source_day_leaderboard.csv`
- `market_metric_source_day_scorecard.csv`

展示方式：

- 排名表只展示前 12 条。
- 旁边放一个结论条：

```text
5 日做主门控，3 日做情绪预警，10 日做弱势确认；20 日最好业务分只有 3.97，不适合决定明天是否新开仓。
```

### 4. 来源 x 市场状态矩阵

字段来源：

- `gate_summary_by_source_regime.csv`
- `gate_summary_by_source_detail.csv`
- `market_metric_source_day_scorecard.csv`

展示顺序：

1. 星火机会模型
2. 资金流回调稳健策略
3. 趋势延续策略
4. 试盘识别

每个来源展示：

- 样本数
- 高/低水位推荐日
- 5 日痛苦持仓率
- 10 日痛苦持仓率
- 高水位相对低水位的 MFE 提升
- 置信度：可用 / 方向支持 / 样本不足

页面文案要避免说“谁绝对更强”，只说：

```text
这个来源在什么市场水位下更适合参与。
```

### 5. 被拦截候选复盘

这是研究页最重要的新增区，专门回答：

```text
有些票拦截了，如果不拦截会怎样？
```

左侧清单字段：

| 字段 | 含义 |
|---|---|
| 股票 | 名称、代码 |
| 信号日 | 原来源给票日期 |
| 来源 | 星火 / 资金流回调 / 趋势延续 / 试盘 |
| 原始动作 | 来源原本是否明日可买 |
| 环境动作 | 环境允许 / 仅观察 / 暂停新开仓 |
| 拦截原因 | 例如防守-持续下跌、小盘 5 日上涨占比低 |
| 后续结果 | 5 日/10 日痛苦持仓、最大冲高、收盘收益 |
| 复盘结论 | 正确拦截 / 代价可接受 / 误杀待复核 |

右侧详情展示：

- 信号日
- 假设买入日：次日开盘
- 假设买入价：次日开盘价
- 5 日观察点
- 10 日观察点
- 22 日观察点，仅用于机会模型复盘
- 痛苦持仓触发原因：收盘亏 5% / 最大浮亏 8%

注意：这里的“买入日”是为了回答“不拦截会怎样”的假设买点，不能标成真实操作。

### 6. 单票固定窗口图

借鉴 `OpportunityTradeReviewPage` 的表达：

- 左侧：被拦截候选清单。
- 右侧：固定窗口 K 线。
- 图上标线：
  - 信号日
  - 环境判定日
  - 假设买入日
  - 5 日观察点
  - 10 日观察点
  - 22 日硬观察点

图下指标：

- 最大冲高
- 最大浮亏
- 5 日收盘收益
- 10 日收盘收益
- 痛苦持仓原因

## 二、选股工作台接入方案

### 总体原则

选股工作台不是研究报告页。它只回答当天决策：

```text
今天能不能新开仓？
这只票是环境允许、仅观察，还是暂停新开仓？
如果环境允许，买点仍按来源规则执行。
如果已经持仓，退出仍按原有持仓/双轨卖点体系执行。
```

### 1. 顶部市场水位卡

位置：`SelectionResearchPage` 顶部工具栏下方、候选列表上方。

展示字段：

| 字段 | 示例 |
|---|---|
| 今日水位 | 防守 |
| 细分状态 | 防守-持续下跌 |
| 默认动作 | 暂停新开仓 |
| 5 日主判断 | 全市场上涨占比、小盘上涨占比、中位涨跌幅 |
| 3 日预警 | 情绪是否急变 |
| 10 日确认 | 弱势是否持续 |
| 三条原因 | 来自 `reason_top3` |

文案：

```text
当前为防守-持续下跌。默认暂停新开仓，候选仅观察；等待 5 日水位修复或例外被数据证明。
```

### 2. 左侧候选列表

现有分组保留：

- 明日可操作
- 观察中
- 已拦截 / 风险提示
- 持仓跟踪
- 次日卖出

新增每条候选的环境标签：

| 标签 | 含义 |
|---|---|
| 环境允许 | 市场水位不阻止执行来源买点 |
| 仅观察 | 市场水位谨慎，或来源样本不足 |
| 暂停新开仓 | 防守环境下默认不执行新开仓 |
| 例外未通过 | 高分/高置信暂未证明能穿越弱市 |

单条候选上要同时显示两层动作：

```text
来源动作：明日可买
环境动作：暂停新开仓
最终处理：仅观察
```

这样用户能知道：

- 原来源确实给了票。
- 页面不是把票删掉。
- 是市场环境覆盖层把它压成观察。

### 3. 右侧单票决策详情

新增“入场结论”卡，结构如下：

| 层级 | 展示 |
|---|---|
| 环境层 | 防守-持续下跌，默认暂停新开仓 |
| 来源层 | 星火机会模型给出明日可买，目标是 22 日冲高 |
| 最终动作 | 仅观察，不执行新开仓 |
| 解释 | 该来源未被证明能穿越当前弱市 |

### 4. 买入点表达

买入点必须拆成两层：

```text
环境允许后，才执行来源买点。
```

示例：

```text
来源买点：次日开盘，高开不超过 6.8% 且不接近涨停。
环境判断：当前防守-持续下跌，暂停新开仓。
最终处理：不执行该买点，仅观察。
```

如果环境允许：

```text
环境允许：可按来源买点观察次日开盘。
仍需满足：高开幅度、涨停距离、个股风险过滤。
```

### 5. 退出点表达

退出点不要由市场环境直接生成。

保留原体系：

- 星火持仓/双轨退出
- 策略原本的 `trade_plan.exit_signal_date`
- 已有 `dual_exit_tracks`

市场环境只加背景提示：

```text
当前环境偏弱，持仓建议从严解读；具体卖点仍看双轨退出或来源退出规则。
```

### 6. 信号链路表达

当前链路建议升级为：

```text
推荐日 -> 市场环境判定 -> 来源买点 -> 最终入场动作 -> 持仓/退出跟踪
```

在环境拦截场景中：

```text
推荐日 -> 市场防守 -> 来源买点不执行 -> 后续只复盘 5/10 日表现
```

## 三、数据与接口方案

### V1 最小可落地

先基于本次研究产物生成静态 payload，服务研究页：

```text
public/research/market_environment_gate_research_payload.json
```

来源：

- `market_state_daily.csv`
- `market_metric_source_day_leaderboard.csv`
- `market_metric_source_day_scorecard.csv`
- `gate_policy_comparison_5d.csv`
- `gate_policy_comparison_10d.csv`
- `gate_summary_by_source_regime.csv`
- `candidate_outcomes.csv`

优点：

- 开发快。
- 不影响每日候选主链。
- 先把研究页表达跑通。

### V2 工作台接口

新增：

```text
GET /api/selection/market-environment?date=YYYY-MM-DD
```

返回：

```json
{
  "trade_date": "2026-06-10",
  "water_score": 18.2,
  "market_regime": "defense",
  "market_detail": "defense_active_decline",
  "market_detail_label": "防守-持续下跌",
  "default_action": "暂停新开仓",
  "reason_top3": ["5日上涨占比低", "小盘中位跌幅深", "10日弱势延续"],
  "metrics": {
    "all_up_ratio_3d": 22.1,
    "all_up_ratio_5d": 18.7,
    "all_up_ratio_10d": 20.4,
    "all_med_ret_5d": -4.8,
    "small_up_ratio_5d": 12.3,
    "small_med_ret_5d": -6.1
  }
}
```

### V3 候选级门控字段

建议并入 `GET /api/selection/daily-candidates`，但不覆盖原字段：

```json
{
  "market_environment": {},
  "items": [
    {
      "symbol": "sz002655",
      "source_action_label": "明日可买",
      "entry_allowed": true,
      "market_gate_status": "blocked",
      "market_gate_reasons": ["防守-持续下跌", "星火高分例外未通过"],
      "market_default_action": "暂停新开仓",
      "final_entry_allowed": false,
      "final_action_label": "仅观察",
      "entry_decision_source": "market_gate",
      "gate_policy_id": "market_gate_v0_20260610",
      "gate_policy_version": "research_v0"
    }
  ]
}
```

字段解释：

| 字段 | 作用 |
|---|---|
| `entry_allowed` | 原来源/个股规则动作，保留兼容 |
| `market_gate_status` | 环境覆盖层动作 |
| `final_entry_allowed` | 页面最终处理 |
| `entry_decision_source` | rule / market_gate / both |
| `market_gate_reasons` | 为什么环境拦截或降级 |

### V4 单票详情字段

建议补进 `SelectionProfileData`：

```json
{
  "market_environment_snapshot": {},
  "entry_decision_summary": "环境防守，暂停新开仓；该票仅观察。",
  "entry_decision_breakdown": {
    "market_gate": {
      "status": "blocked",
      "label": "暂停新开仓",
      "reasons": []
    },
    "stock_rule": {
      "status": "allowed",
      "label": "来源明日可买",
      "buy_rule": "次日开盘高开不超过6.8%且不接近涨停才买"
    },
    "final_action": {
      "status": "watch_only",
      "label": "仅观察"
    }
  },
  "market_gate_evidence": {
    "primary_window": "5d",
    "warning_window": "3d",
    "confirm_window": "10d"
  }
}
```

## 四、开发顺序建议

### 阶段 1：研究页

先做研究页，因为它不影响日常选股主链。

交付：

1. `market_environment_gate_research_payload.json`
2. `MarketEnvironmentGateResearchPage.tsx`
3. `marketEnvironmentGateResearchRegistry.ts`
4. 研究入口菜单增加 `市场环境门控研究页`
5. 路由增加 `/selection-market-environment-gate`

验收：

- 能看到结论卡。
- 能看到水位时间轴。
- 能看到 3/5/10/20 日周期比较。
- 能看到来源 x 市场状态矩阵。
- 能点开被拦截候选，看到“不拦截会怎样”。

### 阶段 2：选股页只读接入

交付：

1. 当日市场水位接口。
2. 工作台顶部市场水位卡。
3. 候选列表环境标签。
4. 单票详情入场结论。

验收：

- 防守日期能明确显示“暂停新开仓”。
- 候选不会被静默删除。
- 用户能看见“来源动作”和“环境动作”的差别。
- 页面不暗示自动买入。

### 阶段 3：候选级门控落库

交付：

1. 每日候选生成后写入门控结果。
2. `daily-candidates` 返回 `market_gate_status` 和 `final_action_label`。
3. 右侧详情可解释每只票的最终处理。

验收：

- 同一天所有候选共享同一个市场环境快照。
- 同一只票能看出是来源规则拦截、市场环境拦截，还是两者都拦。
- 后续前向复盘可以统计门控后表现。

## 五、不做什么

本轮不做：

- 不自动交易。
- 不记录用户真实买卖。
- 不做动态仓位。
- 不把市场环境当卖点模型。
- 不重新训练四个来源。
- 不把市场环境结论写进原始来源分数。

## 六、实现检查清单

- 研究入口菜单里使用完整业务名称，不使用内部脚本名。
- 研究页复用 `SectionCard` / `Metric`，不要新造一套卡片壳。
- 图表中价格仍是主线，市场水位和门控标签放在副图或 tooltip。
- 被拦截候选必须展示“减少痛苦持仓”和“可能错过冲高”两面。
- 买入点用“假设买入”或“来源买点”，不要写成真实买入。
- 退出点区分“研究观察周期”和“策略退出点”，不要混用。
- 工作台首页只展示决策必要信息，详细证据放研究页。
