# MOD-20260516-01-project-governance-phase1

## 1. 基本信息
- 标题：项目治理线第一阶段收口
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260516-01-project-governance-phase1`
- 关联 CAP：`N/A（治理线规则卡）`
- 关联 STG：`N/A`

## 2. 背景与目标
- 当前项目已有多条业务线、研究线、并行 worktree 与历史过程卡，治理规则需要先收口到统一入口。
- 第一阶段只处理治理规则、入口文档、只读巡检纪律与最小事实回流，不进入业务实现或策略扩写。

## 3. 方案与边界
- 做什么：
  - 明确项目管理工作先做 `main` 只读排查；
  - 明确并行 worktree 存在时，治理工作必须在独立治理分支 / worktree；
  - 明确过程记录只进 change card，`AI_HANDOFF_LOG.md` 只写短日志；
  - 明确已解决 pending 必须从 `07_PENDING_TODO.md` 清理；
  - 把选股研究入口的最小事实回流到治理线入口文档。
- 不做什么：
  - 不改业务代码；
  - 不改 README；
  - 不改 `docs/selection/market_heat/README.md`；
  - 不改 `src/backend/data/public`；
  - 不扩写业务方案、策略实现、接口设计。

## 4. 执行步骤（按顺序）
1. 只读检查治理入口与选股研究入口现状。
2. 更新 `00 / 06 / 08 / AI_QUICK_START / development-workflow` 治理规则。
3. 最小回流 `daily_candidate_source_contract` 与 `selection_research_master` 入口事实。
4. 追加一条 `AI_HANDOFF_LOG` 短日志，只记录结论与链接。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-05-16` 治理线需要做第一阶段收口，
- When 按限制仅修改指定治理文档与入口文档，
- Then 文档中应明确第一阶段只含治理规则、入口文档、只读巡检，不包含业务代码改动。

## 6. 风险与回滚
- 风险：若把治理规则写成业务规则，会扩大本轮范围。
- 回滚：仅回退本卡关联的治理文档变更，不触碰业务文件。

## 7. 结果回填
- 实际改动：
  - 新建本卡并回填治理线第一阶段范围；
  - 收口治理规则、入口文档和最小事实回流；
  - 追加 `AI_HANDOFF_LOG` 短日志。
- 验证结果：
  - 修改范围限制在指定文件内；
  - 未触碰 README、`market_heat/README.md`、业务代码与数据目录。
- 遗留问题：
  - `07_PENDING_TODO.md` 的实际清理动作留待对应已解决事项逐项收尾时执行，本轮仅固化规则。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
