# 选股研究清理与模型落地清单

> Archive-Meta
- Archive-ID: ARC-LEG-20260519-selection-research-cleanup-plan
- Archive-Type: LEG
- Archived-At: 2026-05-19
- Source-Path: docs/selection/selection_research_cleanup_plan.md
- Status: FROZEN

更新时间：2026-05-16

## 结论

这轮选股研究里，真正应该保留的是：

1. **星火机会模型** `spark_opportunity_selector`
2. **守势持仓模型** `sentinel_postclose_exit`
3. **星火进攻版 / 星火稳健版** 两个模型组合的验证结论
4. 一套接入选股工作台的统一模型输出表

不建议继续保留大量中间实验目录、旧编号页面、失败路线的逐笔明细。它们最多保留一页摘要日志，原始过程数据可以删。

## 1. 模型是否需要新数据库

不需要新增一套原始行情数据库。

模型依赖的原始和特征数据已经在现有库里：

| 数据 | 当前库 | 用途 |
|---|---|---|
| L2 交易 / 5分钟聚合 / 日级聚合 | `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db` | 次日开盘价、未来高低收、L2 资金、5分钟聚合 |
| 选股特征 | `/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db` | 价格位置、资金流、stealth/breakout/distribution 等特征 |
| 热点主题 | `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db` | 热点主题、主题生命周期、主题成员 |

需要新增的不是原始库，而是**轻量结果表**。建议就放在 `/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db`，避免再多一个难维护的数据库。

最低需要三张表：

| 表 | 作用 |
|---|---|
| `model_candidate_daily` | 每天盘后写入模型推荐票 |
| `model_position_daily` | 记录真实/模拟持仓快照 |
| `model_action_daily` | 每天盘后写入持仓模型的 `hold / sell_next_open` |

## 2. 每天盘后怎么跟现有 L2 流程衔接

现有流程是你每天盘后跑 L2 更新。模型应该接在 L2 更新完成之后：

1. 跑 `backend/scripts/run_postclose_l2_daily.py`，更新 L2 原子库。
2. 更新或确认 `selection_feature_daily`、`selection_signal_daily` 已覆盖最新交易日。
3. 跑星火机会模型，对最新交易日生成次日候选。
4. 把候选写入 `model_candidate_daily`。
5. 读取当前持仓或模拟持仓。
6. 跑守势持仓模型，生成次日开盘处理建议。
7. 把持仓建议写入 `model_action_daily`。
8. 选股工作台读取统一候选池，把老策略、模型、热点主题一起展示。

当前还缺的是第 3-7 步的生产化封装。研究脚本已经能训练和导出最新候选，但还没有一个稳定的 `run_daily_model_signals.py` 入口，也没有把结果写进工作台统一表。

## 3. 和选股工作台怎么融合

当前 `/api/selection/candidates` 主要还是老策略入口：

- `stable_capital_callback`
- `trend_continuation_callback`
- `v2`
- 旧的 `stealth / breakout / distribution`

星火模型还没有正式接进去。

建议不要再给每个模型单独做一个新 tab。应该改成统一候选池：

| 字段 | 说明 |
|---|---|
| `trade_date` | 信号日 |
| `symbol` | 股票代码 |
| `source_type` | `model` / `rule_strategy` / `hot_theme` / `manual_watchlist` |
| `source_id` | 例如 `spark_opportunity_selector` |
| `source_name` | 星火机会模型 |
| `rank` | 来源内部排名 |
| `score` | 来源内部评分 |
| `horizon` | `22d`、`5d`、`event` 等 |
| `suggested_action` | `candidate_buy` / `hold` / `sell_next_open` / `watch` |
| `buy_rule` | 次日买入约束 |
| `risk_tags` | 高开过大、涨停不可买、主题高潮、出货风险等 |
| `explain_factors` | 资金强、突破强、热点强、位置合适等解释 |
| `model_version` | 模型版本 |

工作台展示逻辑：

- 同一只票被多个来源命中时合并成一张卡。
- 显示来源徽标：星火机会、资金流回调、趋势中继、热点主题、人工观察。
- 如果已有持仓，则优先展示守势持仓模型给出的 `hold / sell_next_open`。
- 如果仓位已满，模型新候选只进入观察，不强行提示买入。

## 4. 必须保留

### 文档

| 路径 | 原因 |
|---|---|
| `docs/selection/opportunity_discovery_model_final.md` | 当前最终说明书，必须保留 |
| `docs/selection/selection_research_master.md` | 总入口，保留但后续要瘦身 |
| `docs/selection/selection_research_cleanup_plan.md` | 本清理清单 |

### 模型产物

| 路径 | 原因 |
|---|---|
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/model.joblib` | 星火机会模型 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/feature_columns.json` | 推理必需 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/summary.json` | 训练与验证摘要 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/latest_candidates.csv` | 最新候选参考 |
| `data/selection/opportunity_discovery/postclose_exit_v0_2/models/*_postclose_exit.joblib` | 守势持仓模型 |
| `data/selection/opportunity_discovery/postclose_exit_v0_2/models/*_postclose_continuation.joblib` | 强势续拿判断 |
| `data/selection/opportunity_discovery/postclose_exit_v0_2/summary.json` | 持仓模型摘要 |
| `data/selection/opportunity_discovery/postclose_exit_v0_2/postclose_exit_strategy_summary.csv` | 组合回测摘要 |

### 验证摘要

| 路径 | 原因 |
|---|---|
| `data/selection/opportunity_discovery/walk_forward_old_v0_1/walk_forward_summary.csv` | 月度滚动验证摘要 |
| `data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1/locked_strategy_summary.csv` | 最终组合锁定验证摘要 |
| `data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1/locked_strategy_monthly_realized.csv` | 月度收益参考 |
| `data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1/locked_strategy_pnl_concentration.csv` | 收益集中度参考 |

### 脚本

| 路径 | 原因 |
|---|---|
| `backend/scripts/research_opportunity_discovery_model.py` | 星火机会模型训练/候选导出 |
| `backend/scripts/research_opportunity_postclose_exit_models.py` | 守势持仓模型训练/回测 |
| `backend/scripts/research_opportunity_walk_forward.py` | 滚动验证 |
| `backend/scripts/export_postclose_exit_locked_validation.py` | 锁定版本验证摘要导出 |
| `backend/scripts/export_opportunity_trade_review_payload.py` | 交易复盘页数据导出 |

### 页面

| 路径 | 建议 |
|---|---|
| `src/components/selection/SelectionResearchPage.tsx` | 保留，主工作台 |
| `src/components/selection/SelectionDecisionPanel.tsx` | 保留，右侧决策面板 |
| `src/components/selection/OpportunityTradeReviewPage.tsx` | 暂时保留，作为最终模型交易复盘页 |
| `public/research/opportunity_trade_review_payload.json` | 暂时保留，复盘页静态数据 |

## 5. 建议删除或只留摘要后删除

以下不是马上执行删除，而是清理建议。

### 可以直接删除的候选

| 路径 | 原因 |
|---|---|
| `data/selection/opportunity_discovery/postclose_exit_v0_1/` | 已被 v0.2 替代 |
| `data/selection/opportunity_discovery/fusion_h5_22_v0_1/` | H5 重排结论不作为主线，保留文档摘要即可 |
| `public/research/s06-fusion-h5-22-report.json` | 对应废弃融合页面的数据 |
| `src/components/selection/S06FusionTradeReviewPage.tsx` | S06 临时编号页面，不应长期保留 |
| `docs/selection/opportunity_postclose_exit_plan.md` | 已被最终说明书覆盖 |

### 先保留摘要，再删原始过程数据

| 路径 | 建议 |
|---|---|
| `data/selection/opportunity_discovery/short_horizon_v0_1/` | H5 有参考价值，但不是当前主模型；保留一段结论即可 |
| `data/selection/opportunity_discovery/execution_v0_1/` | 早盘买点模型不符合“盘后决策”主流程；保留结论即可 |
| `data/selection/opportunity_discovery/exit_audit_v0_1/` | 卖飞分析已沉淀到最终结论；原始逐笔可删 |
| `data/selection/opportunity_discovery/robustness_old_v0_1/` | 体积 53M，只需保留滚动结论 |
| `docs/strategy-rework/strategies/S06-opportunity-discovery/` | 可合并进最终说明书后删除旧 S06 编号文档 |

### 大概率应该删除的旧研究线

| 路径 | 原因 |
|---|---|
| `data/selection/evolution_lab/` | RL/PPO 路线当前没有形成有效产出，占 79M |
| `src/components/selection/PPOBacktestReportPage.tsx` | 如果不再看 PPO 报告，可删除 |
| `docs/strategy-rework/evolution-lab/` | 只保留一条“尝试过 PPO，当前不采用”的日志即可 |
| `docs/strategy-rework/_archive/early-experiments/` | 已经是归档中的早期实验，和当前模型无直接生产关系 |
| `docs/strategy-rework/_archive/obsolete-strategy-dirs/` | 已标记 obsolete，可删除 |

### 暂不建议动

| 路径 | 原因 |
|---|---|
| `data/selection/selection_research.db` | 当前选股特征库，生产/研究共用 |
| `data/selection/market_heat/` | 热点主题仍要做候选交叉验证 |
| `docs/selection/market_heat/` | 体积大，但它是热点模块文档，不完全属于本轮模型清理 |
| `docs/selection/long_term_trends/` | 属于长期趋势研究，不和短线模型混删 |
| `data/selection/aggressive_10cm/` | 是另一条策略研究线，建议单独判断后再删 |

## 6. 研究目录未来规则

以后选股研究不要继续无限归档。建议统一规则：

1. 每条研究线只允许一个最终说明书。
2. 失败实验只保留一条日志：做了什么、结果如何、为什么不采用。
3. 中间 CSV、逐笔交易、临时页面数据，默认 7 天后可删。
4. 只有进入候选生产链路的模型，才保留 `model.joblib`、`feature_columns.json`、`summary.json`。
5. 临时页面必须命名为业务名，不再用 `S06` 这类编号。
6. 新模型必须登记中文名、英文 ID、目标周期、输入、输出、适用行情、风险、当前状态。

## 7. 下一步建议

建议下一步先做两件事：

1. 写 `run_daily_model_signals.py`，把星火模型和守势持仓模型接到盘后 L2 流程后面。
2. 新增三张结果表，并让选股工作台读取 `model_candidate_daily` 和 `model_action_daily`。

等工作台能稳定看到模型输出后，再执行文件删除。删除顺序建议先从 S06 融合页面、PPO 页面、v0.1 模型目录开始。
