# 选股研究历史归档摘要

> 说明：这是 `2026-05-16` 这一轮选股研究清理与机会发现模型收口的压缩摘要，不是整个项目总入口。
> 当前主入口：`docs/selection/daily_candidate_source_contract.md`、`docs/selection/opportunity_discovery_model_final.md`
> 当前现行文档：`docs/selection/opportunity_discovery_model_final.md`、`docs/selection/daily_selection_workbench_integration_plan_2026-05-16.md`、`docs/selection/model_development_sop.md`
> 详细过程留痕已迁入 `docs/archive/`。

## 结论

- `docs/selection` 顶层只保留现行说明书、现行接入方案和少数长期主题入口。
- `cleanup plan / execution todo / deleted manifest / opportunity archive summary` 这 4 份一次性过程文档已迁入 `docs/archive/`。
- 机会发现模型保留为“盘后候选来源 + 盘后持仓建议”研究主线；H5、早盘执行、卖飞审计、旧滚动验证、S06 旧编号资料不再占顶层入口。

## 顶层保留项

- `docs/selection/daily_candidate_source_contract.md`
  - 工作台统一候选池入口。
- `docs/selection/opportunity_discovery_model_final.md`
  - 机会发现模型当前正式说明书。
- `docs/selection/opportunity_discovery_model_final.md`
  - 机会发现模型当前正式说明书。
- `docs/selection/daily_selection_workbench_integration_plan_2026-05-16.md`
  - 每日选股工作台当前接入方案。
- `docs/selection/model_development_sop.md`
  - 后续模型接入工作台的统一交付规范。

## 已迁入 Archive 的过程文档

- `docs/archive/ARC-LEG-20260519-selection-research-cleanup-plan.md`
- `docs/archive/ARC-LEG-20260519-selection-cleanup-execution-todo.md`
- `docs/archive/ARC-LEG-20260519-selection-cleanup-deleted-manifest.md`
- `docs/archive/ARC-LEG-20260519-opportunity-discovery-research-archive-summary.md`

这些文件仍保留追溯价值，但不再作为默认阅读入口。

## 不再延续为主线的研究分支

- `short_horizon_v0_1`
  - H5 对短线启动确认有参考价值，但不作为独立主策略。
- `fusion_h5_22_v0_1`
  - 不再用 H5 直接重排 22 日主模型。
- `execution_v0_1`
  - 依赖次日开盘和早盘 5 分钟信息，不符合当前“盘后决策”主流程。
- `exit_audit_v0_1`
  - 只保留“确实存在卖飞，但不能简单一直拿”的结论。
- `robustness_old_v0_1`
  - 只保留“22 日机会信号有价值但稳定性不足”的结论。
- `S06-opportunity-discovery`
  - 旧编号专题已退出顶层，不再作为当前入口。

## 暂缓处理项

- `PPO / evolution lab`
  - 仍有页面、API、服务和数据目录引用，后续应单独清理，不在本批混处理。
- `aggressive_10cm`
  - 属于另一条策略研究线，单独判断。
- `market_heat / long_term_trends`
  - 属于其他专题主线，不和本轮短线模型归档混做。

## 当前正确使用方式

- 想看机会发现模型当前是什么：读 `docs/selection/opportunity_discovery_model_final.md`
- 想看工作台现在应该怎么接：读 `docs/selection/daily_selection_workbench_integration_plan_2026-05-16.md`
- 想看后续模型必须按什么契约交付：读 `docs/selection/model_development_sop.md`
- 只在需要追溯“为什么删、删了什么、旧实验为什么不用”时，再下钻 `docs/archive/`
