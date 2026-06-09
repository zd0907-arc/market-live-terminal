# MOD-20260606-05 Phase 3 第二批过程产物清理

## 1. 基本信息
- 标题：Phase 3 第二批过程产物清理
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-05-phase3-second-batch-artifact-cleanup`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 关联 STG：`MOD-20260606-03`, `MOD-20260606-04`

## 2. 背景与目标

首批低风险清理已经去掉明显误导残留和临时校验目录。  
这一批继续只处理“过程工作区 / 导出物”，不碰仍被兼容链路引用的大库与状态现场。

## 3. 方案与边界

- 做什么：
  1. 删除 `.run/mac_sync_backfill_202506_202509/`
  2. 删除 `.run/mac_sync_backfill_202510_202512/`
  3. 删除 `.run/relay_test_2/`
  4. 删除 `data/sandbox_exports/`
- 不做什么：
  1. 不动 `.run/daily_new_framework/`
  2. 不动 `.run/postclose_l2/`
  3. 不动 `data/sandbox/review_v2/*`
  4. 不动 `data/market_data.db`、`data/selection/selection_research.db`

## 4. 执行步骤（按顺序）
1. 复核上述目录是否存在正式代码 / 脚本入口引用。
2. 删除纯过程工作区与导出物。
3. 将下一批治理继续限定在“旧盘后历史现场”和“研究导出大目录”。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-06` 仓库里仍保留若干一次性回填工作区、relay 测试目录和 sandbox 导出物。
- When 完成引用复核并删除这些过程产物。
- Then 仓库应减少一批不属于正式运行链、正式研究链或正式配置链的本地产物，且不影响当前主链和兼容链。

## 6. 风险与回滚

主要风险：

1. 错把回填工作区当成仍需重复运行的正式工具入口。
2. 错把导出物当成正式数据库或页面输入。

回滚原则：

1. 这些目录都属于可重建过程产物，若需恢复，应通过原脚本重新生成，而不是从 Git 回退。

## 7. 结果回填
- 实际改动：
  - 删除 `.run/mac_sync_backfill_202506_202509/`
  - 删除 `.run/mac_sync_backfill_202510_202512/`
  - 删除 `.run/relay_test_2/`
  - 删除 `data/sandbox_exports/`
- 验证结果：
  - `rg -n "mac_sync_backfill_202506_202509|mac_sync_backfill_202510_202512|sandbox_exports|relay_test_2"` 未发现正式入口依赖
- 遗留问题：
  - 下一批优先对象是 `.run/postclose_l2` 历史窗口与 `data/selection` 下大型研究导出目录
