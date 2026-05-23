# MOD-20260521-01-code-governance-review-findings

## 1. 基本信息
- 标题：代码治理 review 发现
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260521-01-code-governance-review-findings`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`

## 2. 验证状态
- 已完成一次本地依赖安装。
- `npm run build` 已可执行并通过。
- 本文档里的问题判断基于“已修 3 个确定性问题 + 已通过一次构建验证”的状态。

## 3. 发现问题

### 3.1 情绪模块 symbol 口径不一致
- 位置：`src/App.tsx`
- 问题：页面上游多数逻辑按完整 `symbol` 读数据，但下游新版情绪面板传的是 `activeStock.code`。
- 风险：新版 `sentimentService` 走的是 `/api/sentiment/*/{symbol}` 口径，传六码会打错路径或读到空数据。
- 结论：这是优先修的问题，修复前不要继续扩情绪链路。

### 3.2 行情解析的长度校验偏松
- 位置：`src/services/stockService.ts`
- 问题：只校验了 `parts.length < 30`，但后面实际读取到了 `parts[33] / parts[34] / parts[37]`。
- 风险：上游行情格式一旦变短，会生成 `undefined` / `NaN`，导致页面显示异常但不容易立刻报错。

### 3.3 旧情绪趋势页仍有分叉链路
- 位置：`src/components/dashboard/SentimentTrend.tsx`
- 问题：实时点写进了 `liveData`，但主图只吃 `historyData`，实时更新不会直接体现在图上。
- 风险：旧链路继续和新版 `sentimentService` 分叉，后面容易重复出一套口径。

## 4. 后续修复顺序
1. 先统一情绪模块的 symbol 入参口径。
2. 再收紧行情解析校验。
3. 最后决定旧 `dashboard/*` 情绪链路是保留兼容还是降级标记。

## 5. 已修复
- `src/App.tsx`：新版情绪面板改回传完整 `symbol`。
- `src/services/stockService.ts`：行情长度校验收紧到覆盖后续字段访问。
- `src/components/dashboard/SentimentTrend.tsx`：旧趋势页实时点已合入图表数据。

## 6. 仍保留
- `src/components/dashboard/SentimentDashboard.tsx` 仍是旧入口，后续再决定是保留兼容还是迁到历史说明。

## 7. 代码治理四步当前结论

### 7.1 研究页共享壳统一
- 已落地第一批共享壳：`src/components/common/ResearchCard.tsx`
- 已接入页面：
  - `src/components/selection/SelectionResearchPage.tsx`
  - `src/components/trend/TrendResearchPage.tsx`
  - `src/components/selection/PPOBacktestReportPage.tsx`
- 这一层只统一了 `SectionCard / Metric` 展示壳，没有改业务逻辑、数据结构、图表行为。
- 这一步的收益是降低样式壳漂移，不是做页面级抽象。

### 7.2 情绪模块 canonical / legacy 定性
- 当前 canonical 是：
  - `src/components/sentiment/SentimentDashboard.tsx`
  - `src/components/sentiment/SentimentTrendChart.tsx`
- 当前 legacy / orphan 是：
  - `src/components/dashboard/SentimentDashboard.tsx`
  - `src/components/dashboard/SentimentTrend.tsx`
- 保留风险：
  - `dashboard/*` 仍保留旧接口语义和旧集成方式
  - `src/services/stockService.ts` 里的旧情绪接口还承担兼容读取职责
- 当前最稳妥的治理结论不是“马上删”，而是先在治理文档里把 canonical 和 legacy 边界钉死，避免后续继续双轨扩散。

### 7.3 带股票上下文页面骨架统一评估
- 已评估页面：
  - `src/components/selection/SelectionResearchPage.tsx`
  - `src/components/trend/TrendResearchPage.tsx`
  - `src/components/selection/OpportunityTradeReviewPage.tsx`
  - `src/components/market/MarketHeatPage.tsx`
  - `src/components/model/ModelTrainingPage.tsx`
- 结论：
  - 这些页面共享了顶部返回/标题区、信息概览卡、分区展示壳、部分指标块样式。
  - 但它们的主任务形态并不相同：选股是候选池与决策，趋势研究是长报告，热点是主题池，交易复盘是单票/账户复盘，模型页是训练任务入口。
  - 现在适合共用的最小层只有展示壳，不适合直接抽统一“页面骨架”。

### 7.4 首页 / 复盘页进一步共用评估
- 已评估文件：
  - `src/App.tsx`
  - `src/components/dashboard/RealtimeView.tsx`
  - `src/components/dashboard/HistoryMultiframeFusionView.tsx`
- 结论：
  - `HistoryMultiframeFusionView` 已经是共享的深层能力组件。
  - `App.tsx` 更像路由和主页面编排层，`RealtimeView` 是实时盯盘面板，二者有数据上下文共享，但页面语义不同。
  - 这一层若继续共用，应该先盯“局部能力”和“公共卡片”，不该直接去抽首页 / 复盘页总骨架。
