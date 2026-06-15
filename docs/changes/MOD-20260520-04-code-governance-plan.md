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

当前这份计划不再只是“方向说明”，而要变成代码治理前的执行前置包。后续进入代码治理前，必须先补齐：

1. 治理对象清单
2. canonical / legacy / local-only 边界表
3. 最小验证基线
4. 治理前准入检查
5. 每批治理后的退役回填规则

## 2.1 重新评估结果

- 继续压文档的边际收益已经明显下降：当前入口已经基本收口，剩下的文档噪音主要是历史追溯，不再是最主要的风险源。
- 当前最值得做的是代码层治理：共享壳和双轨实现已经在多个页面同时重复，继续放任只会扩大维护成本。
- 所以本轮治理重心应从“继续删文档”切到“先收代码重复面，再回头看文档是否还需要补最后一轮归档”。

## 3. 当前优先级

### 3.0 代码治理前置条件

在真正进入 3.1 ~ 3.4 前，先完成四件事：

| 前置项 | 要回答什么 | 最低产物 |
|---|---|---|
| 治理对象盘点 | 这次到底治理哪些页面、组件、服务、API | 模块/对象清单 |
| canonical / legacy 边界 | 哪个继续扩展，哪个只兼容，哪个只本地用 | 边界对照表 |
| 验证基线 | 每一批治理前后至少验证什么 | 最小验证清单 |
| 准入检查 | 当前是否会撞上跑数/模型/并行 worktree | 治理前检查清单 |

没补齐这四项，不进入代码治理实施。

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
- canonical：`src/components/sentiment/*`
- legacy 文件已退役删除：`src/components/dashboard/SentimentDashboard.tsx`、`src/components/dashboard/SentimentTrend.tsx`
- 目前只保留历史说明和兼容语义，不再继续往旧 dashboard 链路加功能。

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
| 情绪双轨 | `src/components/sentiment/SentimentDashboard.tsx`、`src/components/dashboard/SentimentDashboard.tsx` | 先确认 canonical，再处理 legacy shim | canonical 已固定，legacy 文件已删除 |
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

## 5. 代码治理前置产物

### 5.1 治理对象清单

至少按四层列清：

1. 页面 / 路由
2. 共享组件
3. 后端服务 / API
4. 兼容入口 / legacy shim

目标不是穷举全仓，而是把本轮会碰到的对象列全，避免治理过程中不断发现“还有一支分叉没记”。

#### 当前已确认的对象

**页面 / 路由**
- `/` 首页盯盘
- `/review` 正式复盘
- `/selection-research` 选股研究
- `/market-heat` 市场热点
- `/trend-research` 趋势研究
- `/model-training` 模型训练
- `/selection-ppo-report`、`/model-training/ppo-backtest` PPO 回测复盘
- `/selection-opportunity-review` 机会发现交易复盘
- `/market-heat/low-position-samples` 热点低位样本

**共享组件**
- `src/components/common/MarketTopHeader.tsx`
- `src/components/common/StockQuoteHeroCard.tsx`
- `src/components/common/QuoteMetaRow.tsx`
- `src/components/common/ResearchCard.tsx`
- `src/components/dashboard/HistoryMultiframeFusionView.tsx`
- `src/components/common/ConfigModal.tsx`
- `src/components/common/DataSourceControl.tsx`

**双轨 / 待定**
- `src/components/sentiment/SentimentDashboard.tsx`
- `src/components/dashboard/SentimentDashboard.tsx`
- `src/components/dashboard/SentimentTrend.tsx`
- `src/components/selection/SelectionDecisionPanel.tsx`
- `src/components/market/HotThemeLowPositionSamplesPage.tsx`

**后端服务 / API**
- `backend/app/main.py`
- `backend/app/routers/review.py`
- `backend/app/routers/sandbox_review.py`
- `backend/app/routers/selection.py`
- `backend/app/routers/market.py`
- `backend/app/routers/analysis.py`
- `backend/app/routers/sentiment.py`
- `backend/app/routers/stock_events.py`
- `backend/app/routers/market_heat.py`
- `backend/app/routers/trend_research.py`
- `backend/app/scheduler.py`

**兼容入口 / legacy shim**
- `ENABLE_RESEARCH_API_ROUTES`
- `/sandbox-review` -> `/review`
- `review.py` 的 `60m` / `1h` 别名
- `analysis.py` 的 `60m` / `1h` 别名
- `sandbox_review.py` 中的旧 fallback
- `selection_history_proxy`
- `live_crawler_win.py` 的旧返回结构兼容

### 5.2 canonical / legacy / local-only 边界表

每个双轨对象必须归到下面三类之一：

| 类别 | 含义 | 后续允许动作 |
|---|---|---|
| canonical | 当前正式真相源 | 允许继续扩展、抽共用、补验证 |
| legacy | 仅兼容 / 历史承接 | 不再扩功能，只允许降级、标记、迁移、退役 |
| local-only | 本地工具 / 调试 / 专题专用 | 不并入正式共享抽象 |

#### 当前初判

| 对象 | 边界 |
|---|---|
| 首页盯盘 / 正式复盘 / 选股研究 / 市场热点 / 趋势研究 / 模型训练 | canonical |
| `HistoryMultiframeFusionView`、`MarketTopHeader`、`StockQuoteHeroCard`、`QuoteMetaRow`、`ResearchCard` | canonical |
| `SentimentDashboard`（`src/components/sentiment/*`） | canonical |
| `src/components/dashboard/SentimentDashboard.tsx`、`src/components/dashboard/SentimentTrend.tsx` | legacy |
| `/sandbox-review`、`review.py` 兼容别名、`ENABLE_RESEARCH_API_ROUTES` | legacy |
| `SelectionDecisionPanel`、`HotThemeLowPositionSamplesPage`、`ModelTrainingPage` | local-only |
| `backend/scripts/*` 大部分编排与导出入口 | local-only |

### 5.3 最小验证基线

每一批代码治理至少固定以下证据：

1. `npm run build`
2. 相关 Python 静态校验或脚本语法校验（若涉及）
3. 目标页面路由冒烟
4. 行为边界说明：无行为变化 / 有限变化

### 5.3.1 第一批代码治理建议

优先级不变，但第一批只动最小面：

1. 研究页共享壳继续收口到 `ResearchCard`。
2. 情绪模块只保留一个 canonical 面，旧 dashboard 链路只做兼容标记。
3. 不先抽总页面骨架。
4. 不先动首页 / 复盘页主结构。
5. 每次只处理一个主题，不跨页面拼单。

### 5.4 治理前准入检查

每一批代码治理前，至少确认：

1. 当前没有要并行接入的跑数/模型分支改同一批文件
2. 当前 worktree/分支职责清楚
3. 本轮不依赖未落地的数据库物理迁移
4. 本轮验证环境可用

### 5.5 退役回填规则

每做完一批，都要回写：

1. 哪些对象已转正为 canonical
2. 哪些对象仍是 legacy
3. 哪些对象进入“待归档 / 待删除 / 待迁移”

不能只在代码里完成，不回写状态。

### 5.6 已完成项的代码收尾映射

前面计划里已经做完的治理项，必须在代码层完成对应收尾，不允许“文档说已完成，代码还在旧口径”：

| 已完成治理项 | 代码收尾动作 | 收尾判定 |
|---|---|---|
| 数据契约 / 存储边界已收口 | 代码默认值只认正式别名；旧名只允许显式 legacy fallback | 不再新增写死旧名的默认路径 |
| 运维白名单已收口 | 启动器、脚本、路由只从正式入口进入 | runbook 与代码实际入口一致 |
| 共享壳已起步（`ResearchCard`） | 继续消灭局部重复壳，只保留语义上必要的局部组件 | 不再新增等价 `MetricCard` / `SectionCard` |
| 情绪模块已单轨 | 旧 dashboard 文件退役，不再保留第二套正式入口 | `src/components/sentiment/*` 是唯一情绪 canonical |
| shadow / sample 已标定 | 代码默认与文档一样把它们当排障 / 样本对象，不进入正式链 | 不会被自动选为主库 |

### 5.7 每批收尾产物

每一批代码治理结束后，必须同时产出：

1. 代码 diff
2. build / 冒烟结果
3. code review findings
4. plan card 回写
5. `AI_HANDOFF_LOG` 更新
6. 如本批已无后续代码动作，则补 archive summary

没有这 6 项，不算真正收尾。

## 6. 验收标准

1. 第一批只产生共享壳，不引入策略行为变化。
2. `SentimentDashboard` 只保留一个明确的 canonical 入口，legacy 入口有清晰标记。
3. 每次改动只影响一个治理主题，不跨主题拼单。
4. 改完必须回写文档，说明哪些重复已消除、哪些仍保留为局部实现。

## 7. 预期执行方式

1. 先出每一项的最小治理范围。
2. 每次只解决一类壳或一类重复实现。
3. 每次改动前先确认不会碰到正在跑的数据/模型工作线。
4. 每次改完都回填治理文档，不让代码变化再漂回过程卡里。

## 8. 推荐执行顺序

1. 先补治理对象清单
2. 再补 canonical / legacy / local-only 边界表
3. 再补最小验证基线和准入检查
4. 再按 3.1 -> 3.2 -> 3.3 -> 3.4 分批推进
5. 每批结束后做 legacy 退役回填

## 9. 当前 review 结果

- 见 `docs/changes/MOD-20260521-01-code-governance-review-findings.md`。
- 已修复：
  - 新版情绪面板统一回传完整 `symbol`
  - 行情解析长度校验已收紧
  - 旧情绪趋势页已合入实时点到图表数据
- 本轮新增落点：
  - `SelectionDecisionPanel` 的局部 `MetricCard` 已收口到共享 `ResearchCard.Metric`，只保留单一壳样式
  - `src/components/dashboard/SentimentDashboard.tsx` 与 `src/components/dashboard/SentimentTrend.tsx` 已退役删除，情绪模块只保留 `src/components/sentiment/*` 作为 canonical
- 仍保留：
  - 情绪模块其余旧边界只保留在计划与回写里，不再扩功能

## 10. 本轮收尾状态

- 已完成：
  - `SelectionDecisionPanel` 的局部 `MetricCard` 统一到 `ResearchCard.Metric`
  - `src/components/dashboard/SentimentDashboard.tsx` 与 `src/components/dashboard/SentimentTrend.tsx` 删除
  - `backend/app/services/market.py` 旧趋势注释改为中性表述
- 已验证：
  - `npm run build`
- 待继续：
  - 按 3.1 -> 3.2 -> 3.3 -> 3.4 继续推进下一批代码治理
  - 每批都回写 `AI_HANDOFF_LOG`
