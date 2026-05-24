# MOD-20260524-13 治理阶段摘要与活跃 WIP 地图

## 1. 基本信息
- 标题：治理阶段摘要与活跃 WIP 地图
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-13-governance-phase-summaries-and-active-wip-map`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 这份摘要干什么

这份文件是给后续 AI 的“短入口”。

它不替代历史过程卡，只把当前已经完成的一批治理压成可快速理解的阶段摘要，避免后续先读 100 多份过程卡。

## 3. 已完成的四个阶段

### 3.1 数据与运行产物治理执行清单（业务审批版）

结论：
- `selection_research_windows.db`、`selection_research.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 都不再按“实验文件”看。
- `backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 只按 shadow / sample / 排障对象看。
- 当前重点不是删库，而是先统一正式别名、主读主写和回写边界。

当前可执行方向：
1. 先收命名口径；
2. 再做目录迁移规划；
3. 最后才考虑物理迁移。

### 3.2 活跃 atomic 入口分类与旧 full_reverse 降级

结论：
- 真正影响当前页面和工作台的活跃入口，优先是 `spark_opportunity_selector.py` 和 `selection_strategy_v2.py`。
- 其他大批研究脚本、专题脚本、案例脚本仍可保留，但不应再被当成默认正式入口。
- 这批治理的价值在于“先修活跃入口，再给历史材料降级”，避免全面替换把研究语境抹平。

当前可执行方向：
1. 继续按模块治理研究脚本族；
2. 研究文档先降级，不要把过程文档当真相源；
3. 不做字符串级全仓扫除。

### 3.3 `market_heat` 模块边界治理

结论：
- 当前正式页面链路是 `tradable_theme_map.db + fine_heat_snapshots_* + /api/market_heat/fine_dashboard`。
- `build_stock_sector_map.py / build_tradable_theme_map.py / build_fine_theme_heat_daily*.py` 是研究/训练底座，不是页面默认入口。
- 专题 HTML、回测、案例、阶段卡都是历史材料或专题材料。

当前可执行方向：
1. 钉死页面正式链路；
2. 维护脚本和专题材料分层；
3. 后续按脚本族继续治理。

### 3.4 `selection watchlist / doubler` 边界治理

结论：
- `watchlist` 是研究后持续盯盘链路，不是每日选股主链。
- `doubler` 是案例库 / 样本研究链路，不是每日候选源。
- 两者都应继续保留，但只按产物材料理解。

当前可执行方向：
1. 保留正式入口说明；
2. 维护脚本跟随正式 atomic 解析链；
3. 不把产物正文当成系统入口。

## 4. 这批治理已经产生的共同效果

1. 统一了主链、研究链、专题链、历史材料的边界。
2. 降低了 AI 把过程文档误读成当前真相的概率。
3. 让后续清理从“按感觉删”变成“按模块、按入口、按收益删”。

## 5. 下一步建议

1. 继续压缩 `docs/changes` 顶层过程卡。
2. 继续压缩 `docs/selection` 顶层历史研究文档。
3. 再逐批处理 `snapshot / sync / local compatibility` 和剩余研究脚本族。
