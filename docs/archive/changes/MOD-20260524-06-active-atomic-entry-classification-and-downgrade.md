# MOD-20260524-06 活跃 atomic 入口分类与旧 full_reverse 降级

## 1. 基本信息
- 标题：活跃 atomic 入口分类与旧 `full_reverse` 降级
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-06-active-atomic-entry-classification-and-downgrade`
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 这次到底做了什么

这次不是全仓替换旧库名，而是先回答一个更重要的问题：

> 哪些地方真的还会影响你现在的页面、工作台和正式研究站？

按这个口径，本轮把命中分成三类：

1. **活跃入口，优先修**
2. **研究/专题材料，保留但不当默认入口**
3. **历史/过程文档，只做降级说明**

## 3. 本轮确认的活跃入口

| 文件 | 当前角色 | 本轮动作 |
|---|---|---|
| `backend/app/services/spark_opportunity_selector.py` | 每日选股工作台活跃候选源 | 默认 atomic 兜底从 `full_reverse` 改为 `compact_current` |
| `backend/app/services/selection_strategy_v2.py` | 选股研究页 / 多处研究服务活跃依赖 | 默认 atomic 常量从 `full_reverse` 改为 `compact_current` |

补充：

- `backend/app/core/config.py`
- `ops/start_local_research_station.sh`

这两处已在上一轮完成正式入口治理，本轮不重复改。

## 4. 本轮明确不做全量替换的对象

以下对象虽然命中了旧库名，但当前不按“正式默认入口”处理：

- `ops/start_local_backend_with_atomic.sh`
- `backend/scripts/build_local_research_snapshot.py`
- `backend/scripts/build_research_watchlist_snapshot.py`
- `backend/scripts/build_fine_theme_heat_daily.py`
- `backend/scripts/build_fine_theme_heat_daily_v2.py`
- `backend/scripts/build_stock_sector_map.py`
- 各类 `research_* / analyze_* / backtest_* / build_*page.py / case page` 脚本

原因不是它们没价值，而是它们属于：

- 兼容排查入口
- 本地快照链
- 热点研究/训练链
- 专题分析与案例材料

如果现在一把全改，风险比收益大，也会把历史研究语境抹平。

## 5. 本轮对研究/历史材料做的降级动作

为了减少后续 AI 误读，本轮给几份高风险文档补了顶部提示或口径修正：

| 文件 | 动作 |
|---|---|
| `docs/selection/market_heat/README.md` | 明确它是模块说明，不是总入口真相；旧库名按兼容理解 |
| `docs/strategy-rework/data-map-current.md` | 明确它是阶段盘点快照，不代表当前正式读法 |
| `docs/strategy-rework/handoff-for-next-ai.md` | 明确旧 worktree / 旧入口只按历史上下文理解 |
| `docs/selection/model_development_sop.md` | 明确 manifest 示例不等于当前正式默认 atomic 入口，并把示例名改成 `compact_current` |

## 6. 当前结论

当前最容易误导后续 AI 的，不是页面服务代码本身，而是：

1. 看起来像“当前真相”的阶段盘点文档
2. 仍保留旧库名的研究脚本和兼容脚本

所以正确顺序不是“全删 / 全替换”，而是：

1. 先修活跃入口
2. 再给研究材料降级
3. 之后按模块逐批处理研究脚本族

## 7. 后续建议顺序

下一批更适合按模块做，而不是按字符串替换：

1. `market_heat` 研究脚本族
2. `selection research / watchlist / doubler` 研究脚本族
3. `snapshot / sync / local compatibility` 脚本族

每一批都只做三件事：

1. 识别它服务哪个业务模块
2. 判断是否还是当前正式入口
3. 决定保留、降级提示、还是后续可归档
