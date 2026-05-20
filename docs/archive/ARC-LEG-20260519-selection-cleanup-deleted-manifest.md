# 选股研究清理删除清单（2026-05-16）

> Archive-Meta
- Archive-ID: ARC-LEG-20260519-selection-cleanup-deleted-manifest
- Archive-Type: LEG
- Archived-At: 2026-05-19
- Source-Path: docs/selection/selection_cleanup_deleted_manifest_2026-05-16.md
- Status: FROZEN

## 回滚边界

- 清理前 checkpoint：`5eef68e chore: checkpoint selection research before cleanup`
- 当前清理分支：`codex/selection-cleanup-20260516`
- 已跟踪文件可通过 Git 恢复。
- 未跟踪实验数据目录不受 Git 保护；本清单记录删除范围和原因。

## 第一批删除范围

| 路径 | 状态 | 删除前大小 | 原因 |
|---|---:|---:|---|
| `data/selection/opportunity_discovery/postclose_exit_v0_1/` | 未跟踪目录 | 32M | 已被 `postclose_exit_v0_2/` 替代 |
| `data/selection/opportunity_discovery/fusion_h5_22_v0_1/` | 未跟踪目录 | 1.6M | H5 融合重排不作为每日盘后主线 |
| `public/research/s06-fusion-h5-22-report.json` | Git 跟踪文件 | 436K | 对应废弃 S06 融合复盘页 |
| `src/components/selection/S06FusionTradeReviewPage.tsx` | Git 跟踪文件 | 24K | S06 临时编号页面，不进入长期入口 |
| `docs/selection/opportunity_postclose_exit_plan.md` | Git 跟踪文件 | 4K | 已被当前清理计划和结论文档覆盖 |

## 保留不动

- PPO / evolution lab 暂不删除，后续单独确认。
- 当前机会发现模型主线、`postclose_exit_v0_2/` 和正式选股数据库不删除。
- 旧脚本中生成这些过期目录的参数暂不删除，避免把研究脚本清理和产物清理混在一批。

## 第二批删除范围

已先将研究结论压缩到 `docs/selection/selection_research_archive_decision_summary.md`，详细实验摘要保留在 `docs/archive/ARC-LEG-20260519-opportunity-discovery-research-archive-summary.md`。

| 路径 | 状态 | 删除前大小 | 原因 |
|---|---:|---:|---|
| `data/selection/opportunity_discovery/short_horizon_v0_1/` | 未跟踪目录 | 29M | H5 短周期只作为启动确认标签，不保留模型和中间 CSV |
| `data/selection/opportunity_discovery/execution_v0_1/` | 未跟踪目录 | 11M | 早盘买点模型不符合每日盘后主流程 |
| `data/selection/opportunity_discovery/exit_audit_v0_1/` | 未跟踪目录 | 56K | 卖飞审计结论已归档，逐笔对比不保留 |
| `data/selection/opportunity_discovery/robustness_old_v0_1/` | 未跟踪目录 | 53M | 旧滚动 split 体积大，保留结论即可 |
| `docs/strategy-rework/strategies/S06-opportunity-discovery/` | Git 跟踪文档目录 | 40K | S06 旧编号文档已合并为正式归档摘要 |

## 暂留脚本

以下脚本仍可能作为旧实验重跑入口，先不和产物清理混删：

| 路径 | 说明 |
|---|---|
| `backend/scripts/research_opportunity_short_horizon.py` | 可重跑 H5 短周期实验 |
| `backend/scripts/research_opportunity_fusion_h5_22.py` | 可重跑 H5 + 22 日融合实验 |
| `backend/scripts/research_opportunity_execution_models.py` | 可重跑早盘执行实验 |
| `backend/scripts/research_opportunity_exit_audit.py` | 可重跑卖飞审计 |
| `backend/scripts/research_opportunity_postclose_exit_models.py` | 仍关联持仓/离场研究，不在本批删除 |
