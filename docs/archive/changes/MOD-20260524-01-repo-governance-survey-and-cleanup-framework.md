# MOD-20260524-01 仓库治理总调研与分模块清理框架

## 1. 基本信息
- 标题：仓库治理总调研与分模块清理框架
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-01-repo-governance-survey-and-cleanup-framework`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`
- 关联 STG：`N/A`

## 2. 目标

这份文档不直接删文件，也不直接做代码重构，只回答 4 个问题：

1. 当前系统到底有哪些正式模块、研究模块、实验模块。
2. 当前仓库的文件体系哪里合理，哪里已经开始污染主阅读路径。
3. 哪些数据库、脚本、文档、运行产物应视为正式真相，哪些只是兼容层或历史包袱。
4. 后续应该按什么顺序，一块一块清，而不是按感觉删。

## 3. 总结论

### 3.1 当前系统骨架是合理的

当前项目已经形成比较清晰的三层结构：

1. 正式主链
   - 盯盘首页 `/`
   - 正式复盘 `/review`
   - 选股研究工作台 `/selection-research`

2. 研究主线
   - 市场热点 `/market-heat`

3. 专题 / 实验层
   - 趋势研究 `/trend-research`
   - 模型训练 `/model-training`
   - PPO 回测复盘 `/selection-ppo-report`、`/model-training/ppo-backtest`
   - 机会发现交易复盘 `/selection-opportunity-review`
   - 热点低位样本 `/market-heat/low-position-samples`

所以问题不是“没有结构”，而是“结构已经有了，但仓库里还保留了太多旧过程、旧兼容和运行残留”。

### 3.2 当前最主要的问题不是 archive，而是仓库被运行态和历史兼容层污染

当前体量最重、最可能持续误导 AI/人工的区域不是 `docs/archive/`，而是：

1. `data/`：本地数据库、研究产物、导出样本混在一起
2. `.run/`：大量运行时日志、worker db、中间报表
3. repo 根目录：残留 `market_data.db`、`market_data_history.db` 等历史库
4. `docs/selection/`：主入口、研究总册、专题案例、训练材料、回测说明混在同层
5. `docs/strategy-rework/`：当前入口、实验目录、旧交接、历史归档并存
6. `ops/`：正式白名单脚本和历史 `full_reverse / bench / backfill` 脚本并存

### 3.3 后续不能按文件夹硬删

后续清理必须遵守下面的分类：

1. 正式真相源：保留，只补边界说明
2. 兼容过渡层：先断引用，再退役
3. 运行产物：先从仓库主视野移开，再决定保留周期
4. 历史档案：不是先删，而是先压缩和改入口

## 4. 当前系统模块地图

### 4.1 前端路由真相源

当前前端路由以 [src/App.tsx](/Users/dong/Desktop/AIGC/market-live-terminal/src/App.tsx) 为准。

| 模块 | 路由 | 当前定位 | 前端入口 |
|---|---|---|---|
| 盯盘首页 | `/` | 正式主链 | `src/components/dashboard/RealtimeView.tsx` |
| 正式复盘 | `/review` | 正式主链 | `src/components/sandbox/SandboxReviewPage.tsx` |
| 选股研究工作台 | `/selection-research` | 正式主链 | `src/components/selection/SelectionResearchPage.tsx` |
| 市场热点 | `/market-heat` | 研究主线 | `src/components/market/MarketHeatPage.tsx` |
| 热点低位样本 | `/market-heat/low-position-samples` | 专题页 | `src/components/market/HotThemeLowPositionSamplesPage.tsx` |
| 趋势研究 | `/trend-research` | 专题页 | `src/components/trend/TrendResearchPage.tsx` |
| 模型训练 | `/model-training` | 专题页 | `src/components/model/ModelTrainingPage.tsx` |
| PPO 回测复盘 | `/selection-ppo-report` | 专题页 | `src/components/selection/PPOBacktestReportPage.tsx` |
| 模型训练内 PPO 详情 | `/model-training/ppo-backtest` | 专题页 | `src/components/selection/PPOBacktestReportPage.tsx` |
| 机会发现交易复盘 | `/selection-opportunity-review` | 专题页 | `src/components/selection/OpportunityTradeReviewPage.tsx` |
| 兼容旧复盘路由 | `/sandbox-review` | 兼容跳转 | 在 `src/App.tsx` 内重定向到 `/review` |

### 4.2 后端 API 真相源

当前后端 API 以 [backend/app/main.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/app/main.py) 注册结果为准。

| API 组 | 路由前缀 | 当前定位 | 代码入口 |
|---|---|---|---|
| Watchlist | `/api` | 正式主链 | `backend/app/routers/watchlist.py` |
| 市场/实时 | `/api` | 正式主链 | `backend/app/routers/market.py` |
| 分析/详情 | `/api` | 正式主链 | `backend/app/routers/analysis.py` |
| 配置 | `/api` | 正式主链 | `backend/app/routers/config.py` |
| 盯盘活跃态 | `/api/monitor` | 正式主链 | `backend/app/routers/monitor.py` |
| 散户情绪 | `/api/sentiment` | 已落地主链但仍部分态 | `backend/app/routers/sentiment.py` |
| 官方事件层 | `/api/stock_events` | 已落地主链但仍部分态 | `backend/app/routers/stock_events.py` |
| ingest | `/api/internal/ingest` | 正式生产链路 | `backend/app/routers/ingest.py` |
| 正式复盘 | `/api/review` | 正式主链 | `backend/app/routers/review.py` |
| 选股研究 | `/api/selection/*` | 本地研究主线 | `backend/app/routers/selection.py` |
| 市场热点 | `/api/market_heat/*` | 研究主线 | `backend/app/routers/market_heat.py` |
| 趋势研究 | `/api/trend_research/*` | 专题层 | `backend/app/routers/trend_research.py` |
| 沙盒复盘 | `/api/sandbox/*` | 维护态 / 隔离域 | `backend/app/routers/sandbox_review.py` |

补充判断：

1. 研究类 API 还存在显式开关 `ENABLE_RESEARCH_API_ROUTES`。
2. 这说明“盯盘/复盘”和“研究页”在部署边界上已经开始分层，这是合理的。

### 4.3 当前模块与文档入口对照

| 模块 | 核心文档入口 | 当前判断 |
|---|---|---|
| 盯盘 | `docs/domain/realtime-monitor.md` | 正式主链 |
| 正式复盘 | `docs/domain/review-and-history.md` | 正式主链 |
| 选股研究 | `docs/domain/selection-research.md` | 主链已落地，但研究结论仍保守 |
| 市场热点 | `docs/selection/market_heat/README.md` | 探索态，不是正式买点系统 |
| 数据主站 / 跑数 | `docs/domain/data-pipeline.md` | 正式主链 |
| 散户情绪 | `docs/domain/retail-sentiment.md` | 已落地但未完全收口 |
| 官方事件层 | `docs/domain/stock-events.md` | 已落地但未完全收口 |

## 5. 当前文件体系判断

### 5.1 合理的部分

下面这些分层总体上是对的：

1. `src/` 前端
2. `backend/` 后端
3. `docs/00~08` 核心规则入口
4. `docs/domain/` 业务长记忆
5. `docs/contracts/` 契约长记忆
6. `docs/ops/` 运维长记忆
7. `docs/changes/` 动态过程卡
8. `docs/archive/` 历史归档

也就是说，项目在“理论上的文档/代码/运维分层”已经基本成型。

### 5.2 不合理的部分

问题主要集中在“理论结构之外的现实残留”：

#### A. 根目录被运行态和历史数据污染

当前 repo 根目录存在：

- `market_data.db`
- `market_data_history.db`
- `market_data.db-shm`
- `market_data.db-wal`
- `market_data_history.db-shm`
- `market_data_history.db-wal`
- `.run/`
- `logs/`
- `dist/`
- `node_modules/`
- `.venv/`

这里面有些是正常本地产物，但它们不应继续在“仓库主视野”里承担长期语义。

#### B. data 目录同时承接了正式库、修复库、沙盒库、研究产物

当前 [data](/Users/dong/Desktop/AIGC/market-live-terminal/data) 里同时有：

1. 主业务消费库
2. 历史修复库
3. 沙盒库
4. 市场热点规则 JSON
5. 研究导出 CSV
6. 选股专题研究产物目录

这说明 `data/` 现在是“正式数据 + 临时研究 + 修复副本 + 导出结果”的混合层，后续必须再拆语义。

#### C. selection 与 strategy-rework 目录承担了过多主题

`docs/selection/` 当前同时承接：

1. 正式入口
2. 研究总册
3. 模型训练 SOP
4. 工作台集成计划
5. 热点子专题
6. 长期趋势专题
7. 案例库与回测说明

`docs/strategy-rework/` 当前同时承接：

1. 当前策略入口
2. 历史交接
3. 实验目录
4. 案例目录
5. 长记忆
6. 旧归档

所以这两个目录的问题不是“无结构”，而是“主题太多，同层竞争太强”。

#### D. ops 目录仍然存在正式入口和历史脚本族并排暴露

虽然 [docs/04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md) 已经定义了正式白名单，但 `ops/` 目录肉眼上仍会暴露：

1. `run_postclose_l2.sh`
2. `start_local_research_station.sh`
3. `start_local_research_frontend.sh`
4. `bootstrap_mac_full_processed_sync.sh`

以及一批历史高噪音对象：

1. `start_atomic_backfill_full_reverse.sh`
2. `start_atomic_backfill_mainboard_full_reverse.sh`
3. `check_atomic_backfill_full_reverse.sh`
4. `bench_*`
5. `measure_full_extract.ps1`
6. `start_local_backend_with_atomic.sh`

所以这里的风险是“旧名词持续占据一线视野”。

## 6. 当前数据与数据库分层判断

### 6.1 正式读取路径

当前正式本地研究站启动脚本 [ops/start_local_research_station.sh](/Users/dong/Desktop/AIGC/market-live-terminal/ops/start_local_research_station.sh) 已经明确：

1. 优先读取外置目录 `/Users/dong/Desktop/AIGC/market-data`
2. 若外置目录不存在，再回退到 repo 内 `data/`
3. `DB_PATH`、`SELECTION_DB_PATH`、`ATOMIC_*` 都在启动时统一注入

这说明：

1. repo 内 `data/` 已经不是唯一真相源
2. 外置 `market-data` 才是当前正式研究站的优先数据根

### 6.2 当前数据库对象分类

#### 正式真相源

1. 外置 `market-data/market_data.db`
2. 外置 `market-data/selection/selection_research.db`
3. 外置 `market-data/atomic_facts/*`
4. repo 内 `data/user_data.db`

#### 兼容 / 过渡层

1. repo 内 `data/market_data.db`
2. repo 内 `data/selection/selection_research.db`
3. repo 内旧 atomic 路径相关逻辑
4. 根目录 `market_data.db`
5. 根目录 `market_data_history.db`

这些对象不一定都没用，但它们的角色已经从“正式运行真相”退化为：

- 本地兼容副本
- 历史脚本输入
- 临时验证样本

#### 一次性修复或临时对象

1. `data/market_data_history_202602_fix.db`
2. `backend/app/market_data.db`
3. `backend/app/db/market_data.db`
4. `backend/market.db`

其中：

- `backend/market.db` 是已被跟踪的空文件，属于治理对象；
- `backend/app/db/market_data.db` 是空文件；
- `backend/app/market_data.db` 是小型样本库，只见到文件存在，没有看到它被定义为正式路径。

### 6.3 当前最关键的判断

后续不能先问“哪几个 db 体积大”，而应先问：

1. 它是不是正式路径
2. 它是不是还有脚本引用
3. 它是当前运行依赖，还是旧工具依赖

如果直接按体积删，很容易把仍被旧脚本引用的兼容库删掉。

## 7. 当前文档层判断

### 7.1 archive 不是主问题

当前 archive 目录本身不是主要治理对象：

1. `docs/archive/` 体积小
2. `docs/strategy-rework/_archive/` 虽然文件多，但已经有历史标识
3. archive 的问题主要是“后续还可以继续压缩摘要”，不是“马上删”

所以 archive 不是第一批清理重点。

### 7.2 当前真正会误导 AI 的，是这些“像现状、其实只是过程”的材料

1. `docs/changes/` 里的旧 current-state / rollout / roadmap / project-status 卡
2. `docs/selection/` 里同时像总入口又像阶段方案的文件
3. `docs/strategy-rework/handoff-for-next-ai.md`
4. `docs/selection/selection_research_master.md`
5. 一些旧 worktree、旧分支、旧默认入口仍写在文档里的对象

这些对象的治理重点不是立即删除，而是：

1. 改默认入口
2. 降级阅读优先级
3. 吸收到少量阶段摘要后再迁 archive

## 8. 当前脚本层判断

### 8.1 正式白名单

当前正式脚本白名单仍应以 [docs/04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md) 为准：

1. `ops/bootstrap_mac_full_processed_sync.sh`
2. `ops/start_local_research_station.sh`
3. `ops/start_local_research_frontend.sh`
4. `ops/run_postclose_l2.sh`
5. `ops/check_postclose_l2_status.sh`
6. `sync_to_windows.sh`
7. `deploy_to_cloud.sh`
8. `scripts/check_baseline.sh`

### 8.2 二线工具 / 历史脚本族

下面这些不应再被理解为默认入口：

1. `full_reverse`
2. `atomic_backfill`
3. `bench`
4. `measure_*`
5. `start_local_backend_with_atomic.sh`
6. 一些旧的 windows 分片与月跑脚本

这里后续真正要做的不是先删脚本，而是：

1. 给正式白名单更高可见性
2. 给二线脚本更低可见性
3. 把“仍有正式职责”的二线脚本单独列出来

## 9. 治理方法：以后怎么一块一块清

### 9.1 推荐总方法

采用两层并行治理：

1. 按系统模块梳理
2. 按存储对象落地清理

这是最适合当前项目的方法，因为：

1. 你能从功能理解全局
2. 我能从代码/文档/数据库引用落地判断风险

### 9.2 每个模块都按同一模板处理

后续处理任一模块，只回答 6 个问题：

1. 这个模块当前是不是正式主链
2. 它的页面入口和 API 入口是什么
3. 它当前正式读哪些库 / 文件
4. 它有没有旧兼容路径
5. 它对应哪些核心文档
6. 它目录下哪些是当前真相，哪些是研究沉淀，哪些是历史材料

### 9.3 每个文件/数据库对象都按同一模板处理

后续处理任一对象，只回答 5 个问题：

1. 它属于哪个模块
2. 当前角色是：正式 / 兼容 / 临时 / 归档
3. 是否仍被代码或脚本引用
4. 现在删会不会影响主链
5. 后续动作是：保留 / 迁出 / 归档 / 待退役

## 10. 推荐执行顺序

### Phase 1：数据库与运行产物

优先级最高。

原因：

1. 最占空间
2. 最容易误导 AI
3. 最容易让“仓库看起来像有很多真相源”

这一阶段先不删，只做分类：

1. 正式库
2. 兼容库
3. 修复库
4. 运行产物库

### Phase 2：选股 / 热点 / 策略研究三块专题目录

目标：

1. 把真正的入口文档钉死
2. 把研究沉淀与阶段方案分层
3. 把还能误导后续 AI 的过程文档继续降级

### Phase 3：ops 与历史脚本族

目标：

1. 固定正式入口
2. 标记二线工具
3. 明确哪些脚本已经只剩历史价值

### Phase 4：代码治理

这一步最后做。

因为如果前面的“模块边界 / 文档入口 / 存储角色”不先固定，代码治理会反复踩空。

## 11. 当前不建议做的事

1. 不建议现在就删所有 archive
2. 不建议现在就按目录批量删 db
3. 不建议现在就大规模重构 `selection` / `strategy-rework`
4. 不建议现在就统一所有研究页代码壳之后再回头想数据

## 12. 当前完成度与重新评估

到 2026-05-24 当前轮次为止，已经完成的不是“全仓清理”，而是高混淆入口的第一轮收口：

1. 正式运维白名单与核心口径收口
2. `active atomic` 活跃入口默认切到 compact
3. `market_heat` 模块边界收口
4. `selection watchlist / doubler` 边界收口
5. `snapshot / sync / local compatibility` 边界收口
6. 策略研究默认入口第一轮收紧
7. `README / AI_QUICK_START / 04_OPS_AND_DEV / 03 / storage` 的版本与正式数据根目录口径对齐

这意味着：

- 继续做大面积历史文档瘦身，收益已经明显下降
- 现在真正还值得优先做的，是少数会持续把人带偏的“默认入口 / 默认命名 / 默认主库认知”

重新评估后，当前最高收益的剩余治理点是：

1. 外置 `market-data` 与 repo 内 `data/` 的正式 / 回退角色继续命名收口
2. `backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 这类 shadow / 样本库的降级说明
3. `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这类“名字像实验、实际承担主链”的对象命名收口
4. `data/market_heat/market_heat.db` 这类历史残留库的高风险误导说明

代码共享壳治理仍有价值，但不应该先于这批命名和主库角色收口。

当前已经进入代码治理前的正式包阶段：文档层的正式角色、兼容副本、shadow/sample 以及高风险命名冲突已经基本收齐，下一步应先把代码对象清单和 `canonical / legacy / local-only` 边界表固化，再决定是否真正动共享壳和双轨实现。

## 13. 本文档之后的直接用途

后续可以直接按下面的顺序往下做：

1. 先做“数据库与运行产物命名收口清单”
2. 再做“shadow / 样本库降级说明”
3. 再决定是否进入代码治理
4. 若代码治理落地，再回头做最后一轮 archive 压缩

每一块都按本文的分类框架往下拆，不再重新发明方法。
