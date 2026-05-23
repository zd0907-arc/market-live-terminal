# MOD-20260520-04-code-governance-plan

## 1. 基本信息
- 标题：代码治理规划
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260520-04-code-governance-plan`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 关联 STG：`N/A`

## 2. 目标

在文档入口、脚本边界、阶段摘要已经收口之后，再给代码层一个明确的治理顺序，避免“看起来都该重构”导致一次性动太多页面。

## 2.1 重新评估结果

- 继续压文档的边际收益已经明显下降：当前入口已经基本收口，剩下的文档噪音主要是历史追溯，不再是最主要的风险源。
- 当前最值得做的是代码层治理：共享壳和双轨实现已经在多个页面同时重复，继续放任只会扩大维护成本。
- 所以本轮治理重心应从“继续删文档”切到“先收代码重复面，再回头看文档是否还需要补最后一轮归档”。

## 3. 当前优先级

### 3.1 研究页共享壳统一

优先级最高。

目标：
- 统一研究页 `SectionCard / Metric` 壳。
- 减少选股、热点、趋势研究页里各自重复搭壳。

理由：
- 这类重复最容易持续扩大。
- 统一壳不会先碰业务规则，风险低。

当前状态：
- 第一批已落地，并已抽出共享 `SectionCard / Metric` 到 `src/components/common/ResearchCard.tsx`。
- 已接入 `SelectionResearchPage`、`TrendResearchPage`、`PPOBacktestReportPage`。
- `OpportunityTradeReviewPage`、`ModelTrainingPage` 可继续纳入同一展示壳收口；`HotThemeLowPositionSamplesPage` 先保留局部实现。

### 3.2 情绪模块双轨清理

第二优先级。

目标：
- 梳理 `sentiment/` 和 `dashboard/` 两条近似实现。
- 明确哪个是当前真相，哪个只做兼容或历史保留。

理由：
- 这是典型的双轨实现问题。
- 不先收口，后续页面和契约会继续分叉。

当前状态：
- 已定性：
  - canonical：`src/components/sentiment/*`
  - legacy：`src/components/dashboard/SentimentDashboard.tsx`、`src/components/dashboard/SentimentTrend.tsx`
- 本轮不做强删，只先把 canonical / legacy 边界钉死，并避免继续往 legacy 链路加功能。

### 3.3 带股票上下文页面骨架统一

第三优先级。

目标：
- 统一带股票上下文的页面骨架。
- 让复盘、选股、热点解释页共享同一套页面框架语义。

理由：
- 这是页面层结构治理，不是算法治理。
- 适合在壳统一之后推进。

当前状态：
- 已完成评估，结论是不直接抽统一骨架。
- 原因不是做不到，而是页面任务形态差异太大，强抽会把选股、热点、趋势、复盘几类页面混在一个抽象里。
- 当前只建议继续统一展示壳、顶部信息块和局部共用能力，不建议抽总页面容器。

### 3.4 首页 / 复盘页进一步共用评估

第四优先级。

目标：
- 评估首页与复盘页主内容是否还能继续共用更多逻辑。
- 只做评估，不先动大面积代码。

理由：
- 这两个页面最容易因为共用逻辑过多而互相污染。
- 必须放在前面三项之后。

当前状态：
- 已完成评估，结论是“继续收局部能力，不收总骨架”。
- `HistoryMultiframeFusionView` 已经是当前最有价值的共享深层组件。
- 下一步若继续治理，应盯住头部 quote 元信息、局部指标卡、公共表格/列表行为，而不是合并首页与复盘页结构。

### 3.5 本轮落地边界

第一批只动“明显重复、且不会碰业务规则”的代码面：

| 代码面 | 目标文件 | 处理方式 | 本轮状态 |
|---|---|---|---|
| 研究页共享壳 | `src/components/selection/SelectionResearchPage.tsx`、`src/components/trend/TrendResearchPage.tsx`、`src/components/selection/PPOBacktestReportPage.tsx`、`src/components/selection/OpportunityTradeReviewPage.tsx`、`src/components/model/ModelTrainingPage.tsx` | 抽出共用 `SectionCard / Metric` 壳 | 第一批进行中 |
| 情绪双轨 | `src/components/sentiment/SentimentDashboard.tsx`、`src/components/dashboard/SentimentDashboard.tsx` | 先确认 canonical，再处理 legacy shim | 已定性，暂不删 |
| 带股票上下文页面骨架 | `src/components/selection/SelectionResearchPage.tsx`、`src/components/trend/TrendResearchPage.tsx`、`src/components/market/MarketHeatPage.tsx` | 先做骨架评估，不碰策略内容 | 已评估，暂不抽总壳 |
| 首页 / 复盘页共用 | `src/App.tsx`、`src/components/dashboard/RealtimeView.tsx`、`src/components/dashboard/HistoryMultiframeFusionView.tsx` | 只做评估，不先改 | 已评估，保留后续局部治理 |

不纳入第一批的现有重复：

- `SelectionDecisionPanel` 的 `MetricCard`：先保留局部实现，避免把右侧摘要壳和全页壳混成一个抽象。
- `HistoryMultiframeFusionView`：已经是共享组件，不作为本轮重构对象。
- `SelectionDecisionPanel` / `OpportunityTradeReviewPage` 中的局部 `Metric`：先观察是否真的值得抽成统一小组件。
- `HotThemeLowPositionSamplesPage` 的 `SummaryStrip / DetailPanel / SampleCard`：虽然也有 `Metric` 壳，但它们已经嵌在复合卡和样本详情语义里，本轮不动。

## 4. 不先做什么

1. 不先改业务策略判断。
2. 不先改模型逻辑。
3. 不先做大范围页面重构。
4. 不先合并所有研究页为一个页面。
5. 不再把继续压文档当作当前主优先级，除非它能直接消除错误入口或重复承接。

## 5. 验收标准

1. 第一批只产生共享壳，不引入策略行为变化。
2. `SentimentDashboard` 只保留一个明确的 canonical 入口，legacy 入口有清晰标记。
3. 每次改动只影响一个治理主题，不跨主题拼单。
4. 改完必须回写文档，说明哪些重复已消除、哪些仍保留为局部实现。

## 6. 预期执行方式

1. 先出每一项的最小治理范围。
2. 每次只解决一类壳或一类重复实现。
3. 每次改动前先确认不会碰到正在跑的数据/模型工作线。
4. 每次改完都回填治理文档，不让代码变化再漂回过程卡里。

## 7. 当前 review 结果

- 见 `docs/changes/MOD-20260521-01-code-governance-review-findings.md`。
- 已修复：
  - 新版情绪面板统一回传完整 `symbol`
  - 行情解析长度校验已收紧
  - 旧情绪趋势页已合入实时点到图表数据
- 仍保留：
  - 旧 `dashboard/SentimentDashboard` / `dashboard/SentimentTrend` 已被定性为 legacy，后续只考虑兼容边界，不再扩功能
