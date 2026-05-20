# 选股研究清理执行 TODO（2026-05-16）

> Archive-Meta
- Archive-ID: ARC-LEG-20260519-selection-cleanup-execution-todo
- Archive-Type: LEG
- Archived-At: 2026-05-19
- Source-Path: docs/selection/selection_cleanup_execution_todo_2026-05-16.md
- Status: FROZEN

## 当前结论

已在 `main` 上完成一次存档提交：

```text
5eef68e chore: checkpoint selection research before cleanup
```

接下来先做文件清理，再做“每日盘后工作流”页面和模型/策略接入开发。

本清单基于：

- `docs/archive/ARC-LEG-20260519-selection-research-cleanup-plan.md`
- `docs/strategy-rework/current-inventory.md`
- `docs/strategy-rework/data-map-current.md`
- `docs/strategy-rework/current-strategy-conclusion.md`
- 当前代码和数据目录盘点

## 分支和 worktree 建议

1. 从当前 checkpoint 后新建清理分支：

```bash
git switch -c codex/selection-cleanup-20260516
```

2. 清理分支只做删除、归档索引和引用修正，不做新功能。
3. 清理合并后，再从最新 `main` 新建开发分支：

```bash
git switch -c codex/daily-selection-workbench
```

4. 新开发分支目标是把选股页改成“每日综合候选中心”，接入规则策略和模型来源。

## 不删除

### 正式数据源

| 路径 | 原因 |
|---|---|
| `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db` | 正式原子行情/L2事实库 |
| `/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db` | 正式选股特征库，未来统一候选表也建议放这里 |
| `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily.db` | 热点主题特征仍会参与模型/解释 |
| `/Users/dong/Desktop/AIGC/market-data/market_heat/fine_theme_heat_daily_v2.db` | 新热点库，先保留 |
| `/Users/dong/Desktop/AIGC/market-data/user_data.db` | 用户数据 |

### 当前模型主线

| 路径 | 原因 |
|---|---|
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/model.joblib` | 星火机会模型 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/feature_columns.json` | 推理必需 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/summary.json` | 模型摘要 |
| `data/selection/opportunity_discovery/opportunity_discovery_trade_l2_v0_1/latest_candidates.csv` | 最新候选参考，未入库前保留 |
| `data/selection/opportunity_discovery/postclose_exit_v0_2/` | 守势持仓模型当前主线 |
| `data/selection/opportunity_discovery/postclose_exit_locked_validation_v0_1/` | 锁定验证摘要，先保留 |

### 当前工作台核心代码

| 路径 | 原因 |
|---|---|
| `src/components/selection/SelectionResearchPage.tsx` | 主工作台 |
| `src/components/selection/SelectionDecisionPanel.tsx` | 右侧决策面板 |
| `backend/app/routers/selection.py` | 选股 API 入口 |
| `backend/app/services/selection_research.py` | 旧底座特征/信号生成 |
| `backend/app/services/selection_strategy_v2.py` | 旧策略特征和模型特征来源 |

## 第一批可删除候选

已执行第一批清理，删除明细见：

```text
docs/archive/ARC-LEG-20260519-selection-cleanup-deleted-manifest.md
```

本批只删已经被明确替代、且不影响当前主线的目录/文件。

| 路径 | 删除理由 |
|---|---|
| `data/selection/opportunity_discovery/postclose_exit_v0_1/` | 已被 `postclose_exit_v0_2` 替代 |
| `data/selection/opportunity_discovery/fusion_h5_22_v0_1/` | H5 重排不作为主线，结论已写入文档 |
| `public/research/s06-fusion-h5-22-report.json` | 对应临时融合页面数据 |
| `src/components/selection/S06FusionTradeReviewPage.tsx` | S06 临时编号页面，不作为长期入口 |
| `docs/selection/opportunity_postclose_exit_plan.md` | 已被最终说明/清理计划覆盖 |

执行前检查：

```bash
rg -n "S06FusionTradeReviewPage|s06-fusion-h5-22-report|postclose_exit_v0_1|fusion_h5_22_v0_1|opportunity_postclose_exit_plan" .
```

如果仍有代码引用，先删除入口或改为指向保留文档，再删文件。

## 第二批先留摘要再删

已将结论汇总到：

```text
docs/selection/selection_research_archive_decision_summary.md
```

并删除原始目录。

这些有研究价值，但不应保留大量逐笔/中间产物。

| 路径 | 处理方式 |
|---|---|
| `data/selection/opportunity_discovery/short_horizon_v0_1/` | 保留 H5 结论，删中间 CSV/模型 |
| `data/selection/opportunity_discovery/execution_v0_1/` | 保留“早盘买点不符合盘后流程”结论，删原始产物 |
| `data/selection/opportunity_discovery/exit_audit_v0_1/` | 保留卖飞分析结论，删逐笔对比 |
| `data/selection/opportunity_discovery/robustness_old_v0_1/` | 保留滚动验证结论，删 split 原始目录 |
| `docs/strategy-rework/strategies/S06-opportunity-discovery/` | 合并进最终说明后，旧 S06 编号文档归档或删除 |

建议新增一个摘要文件：

```text
docs/selection/selection_research_archive_decision_summary.md
```

## 第三批大概率删除

这些当前不进入每日盘后工作流。先确认没有页面/脚本依赖，再删除。

| 路径 | 删除理由 |
|---|---|
| `data/selection/evolution_lab/` | RL/PPO 路线当前未形成有效生产产出 |
| `docs/strategy-rework/evolution-lab/` | PPO/演化实验文档，保留一条结论即可 |
| `src/components/selection/PPOBacktestReportPage.tsx` | 如不再看 PPO 报告，可删 |
| `docs/strategy-rework/_archive/early-experiments/` | 早期实验归档，和当前生产无直接关系 |
| `docs/strategy-rework/_archive/obsolete-strategy-dirs/` | 已标记 obsolete |

执行前检查：

```bash
rg -n "PPOBacktestReportPage|selection-ppo-report|evolution_lab|evolution-lab|obsolete-strategy-dirs|early-experiments" src backend docs data
```

## 暂缓删除

| 路径 | 原因 |
|---|---|
| `data/selection/aggressive_10cm/` | 另一条策略研究线，需要单独判断 |
| `docs/strategy-rework/strategies/aggressive-10cm/` | 同上 |
| `data/selection/long_term_trends/` | 长期趋势研究，不和短线选股清理混删 |
| `docs/selection/long_term_trends/` | 同上 |
| `data/selection/selection_research.db` | 项目内副本，需与正式库比对后再处理 |
| `data/market_data.db`、`market_data.db`、`market_data_history.db` | 需先确认当前本地服务是否仍可能读到 |

## 旧规则策略处理

| 策略 | 清理结论 |
|---|---|
| `v2 / stealth / breakout / distribution` | 不再作为日常页面入口；保留为特征来源 |
| `stable_capital_callback` | 规则源保留，但不能继续读实验 CSV |
| `trend_continuation_callback` | 规则源保留，作为观察/小样本验证来源 |
| S01/S02 实验 CSV | 未来迁入统一候选表后，CSV 只留摘要或归档 |

## 清理后的开发目标

1. 新增统一候选表，放入正式选股库：

```text
model_candidate_daily
model_position_daily
model_action_daily
selection_strategy_registry
selection_candidate_sources
selection_strategy_runs
```

2. 新增每日盘后脚本：

```text
backend/scripts/run_daily_model_signals.py
```

3. 页面改成：

```text
选日期 -> 综合候选结果 -> 单票来源解释 -> 持仓动作建议
```

4. 页面不再让用户每天手动选择策略。策略/模型作为来源徽标和解释明细展示。

## 删除执行规则

每一批删除都按以下顺序：

1. `rg` 搜引用。
2. 删除入口/引用。
3. 删除文件或目录。
4. `npm run check:version`。
5. `npm run build`。
6. 能跑则跑相关测试；失败只记录和本批无关的既有失败。
7. 单独提交，提交信息用：

```text
chore: prune obsolete selection research artifacts batch N
```
