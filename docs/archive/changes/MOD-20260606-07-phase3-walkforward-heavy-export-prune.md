# MOD-20260606-07 Phase 3 walk-forward 重型导出瘦身

## 1. 基本信息
- 标题：Phase 3 walk-forward 重型导出瘦身
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-07-phase3-walkforward-heavy-export-prune`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-SELECTION-RESEARCH`
- 关联 STG：`MOD-20260606-03`

## 2. 背景与目标

`data/selection/opportunity_discovery/walk_forward_2024_daily_strict_v0_1/` 中最大的单文件是 `daily_scored_candidates.csv`，约 `212MB`。  
当前代码和说明书消费的是这组研究结果里的摘要、top10、summary，而不是这份全量日度打分明细。

这一批只做一件事：

1. 删除不参与当前正式入口和当前研究说明的重型原始导出；
2. 保留 `summary.json`、`daily_summary.csv`、`daily_top10.csv`、`topk_summary.csv` 等轻量结论文件。

## 3. 方案与边界

- 做什么：
  1. 删除 `walk_forward_2024_daily_strict_v0_1/daily_scored_candidates.csv`
- 不做什么：
  1. 不删 `summary.json`
  2. 不删 `daily_top10.csv`
  3. 不删 `exit_policy_trades.csv`
  4. 不动 `opportunity_discovery_trade_l2_v0_1/`、`postclose_exit_v0_2/` 等当前仍有消费方的目录

## 4. 执行步骤（按顺序）
1. 复核代码和文档是否直接消费这份 CSV。
2. 确认目录内已有轻量摘要文件可保留结论。
3. 删除重型 CSV。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-06` 的 `daily_scored_candidates.csv` 约 `212MB`，且目录内已有轻量摘要文件。
- When 删除这份全量打分导出。
- Then 应减少一笔明显不属于当前正式入口的研究体积，并保留可读结论文件。

## 6. 风险与回滚

主要风险：

1. 错删当前页面或脚本仍直接读取的训练导出。

回滚原则：

1. 这份 CSV 属于研究过程重导出，可通过原研究脚本重新生成。

## 7. 结果回填
- 实际改动：
  - 删除 `data/selection/opportunity_discovery/walk_forward_2024_daily_strict_v0_1/daily_scored_candidates.csv`
- 验证结果：
  - 当前代码与说明书未见直接消费该文件；保留的轻量结论文件包括 `summary.json`、`daily_summary.csv`、`daily_top10.csv`、`topk_summary.csv`
- 遗留问题：
  - `opportunity_discovery` 目录下仍有多份 `*_train_samples.csv.gz`，后续需按“是否仍被当前训练脚本 /说明书要求保留”继续逐批判断
