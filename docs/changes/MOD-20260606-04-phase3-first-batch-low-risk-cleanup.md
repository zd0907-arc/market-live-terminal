# MOD-20260606-04 Phase 3 首批低风险清理

## 1. 基本信息
- 标题：Phase 3 首批低风险清理
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-04-phase3-first-batch-low-risk-cleanup`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 关联 STG：`MOD-20260606-03`

## 2. 背景与目标

`Phase 2` 已明确当前仓库里同时存在：

1. 仍有兼容引用、暂时不能碰的大库；
2. 明确只是误导残留或一次性临时目录的对象。

这一批只处理第二类，目标是先消掉“高误导、低风险、可直接清理”的对象，不碰仍有兼容引用的大库和状态现场。

## 3. 方案与边界

- 做什么：
  1. 删除 `data/market_heat/market_heat.db` 这个 `0B` 的热点误导残留。
  2. 删除 `.run/tmp_market_heat_release_check/` 这个临时 release 校验目录。
- 不做什么：
  1. 不动 `data/market_data.db`、`data/selection/selection_research.db`。
  2. 不动 `.run/daily_new_framework`、`.run/postclose_l2` 的状态现场。
  3. 不改正式规则文件 `data/market_heat/*.json`。

## 4. 执行步骤（按顺序）
1. 复核两类对象是否仍被正式代码 / 脚本直接引用。
2. 删除 `0B` 误导库和 `tmp` 临时目录。
3. 记录这批清理只影响误导残留与临时校验现场。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-06` 仓库内仍有 `0B` 热点残留库和临时 market heat 发布校验目录。
- When 完成引用复核并删除这两类低风险对象。
- Then 仓库应减少一类明显误导对象和一类明确临时目录，且不影响正式入口、兼容入口和当前状态查看链。

## 6. 风险与回滚

主要风险：

1. 误把临时目录当成正式状态现场。
2. 删掉仍被正式代码读取的热点主库。

本批回滚很简单：

1. `data/market_heat/market_heat.db` 原本就是 `0B` 空文件，若真要恢复只需重新创建空壳。
2. `.run/tmp_market_heat_release_check/` 只是临时校验目录，可按需重新生成。

## 7. 结果回填
- 实际改动：
  - 删除 `data/market_heat/market_heat.db`
  - 删除 `.run/tmp_market_heat_release_check/`
- 验证结果：
  - `rg -n "tmp_market_heat_release_check"` 未发现正式入口依赖
  - `rg -n "data/market_heat/market_heat.db|market_heat.db"` 未发现正式代码读取该空库
- 遗留问题：
  - 下一批优先对象是 `.run/mac_sync_backfill_*`、`.run/postclose_l2` 历史窗口、`data/sandbox_exports/*`
