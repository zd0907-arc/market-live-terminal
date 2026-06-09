# MOD-20260525-01-spark-exit-watchlist-integration

## 1. 基本信息
- 标题：星火进攻版持仓跟踪与次日卖出接入
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260525-01-spark-exit-watchlist-integration`
- 关联 CAP：`CAP-SELECTION-RESEARCH`

## 2. 背景与目标

当前系统里，星火模型已经接入每日选股工作台，并且每天展示 3 个候选。

缺口是：
- 只告诉第二天买什么；
- 不告诉历史已推荐股票在盘后是否该卖；
- 用户无法在页面里持续跟踪“星火历史前三”的卖点。

本次改动目标：
- 保持训练/研究口径继续按 `top1`；
- 产品运行口径改成“历史所有入选过星火前三的票，默认进入跟踪池，直到盘后出现卖点”；
- 每天在同一个工作台里同时展示“明日可操作”“次日卖出”“持仓跟踪”。

## 3. 方案与边界
- 做什么：
  - 新增星火盘后持仓跟踪服务；
  - 基于 `postclose_exit_v0_2` 产物接入 `pc_model_th6_stop12`；
  - 给 `/selection/daily-candidates` 增加 `exit_watchlist`；
  - 给 `/selection/daily-profile/{symbol}` 补齐星火持仓态 / 卖出态字段；
  - 前端工作台新增“次日卖出”“持仓跟踪”分组；
  - 右侧详情区分买入态、持有态、卖出态。
- 不做什么：
  - 不改星火训练收益评估口径；
  - 不回灌 2024-09 以来历史星火候选；
  - 不改其他策略的持仓管理逻辑。

## 4. 执行步骤（按顺序）
1. 盘点星火选股、卖出模型产物、每日工作台和详情字段落点。
2. 新增 `spark_opportunity_exit.py`，实现历史前三跟踪、盘后卖点判定、同日缓存。
3. 扩展 daily workbench 接口，返回 `exit_watchlist` 并支持卖出票详情。
4. 调整前端列表和右侧详情展示。
5. 运行后端真数据校验与最小单测。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-05-22` 的每日工作台数据已存在
- When 调用 `/selection/daily-candidates?date=2026-05-22`
- Then 返回值里除当日候选外，还应包含 `exit_watchlist`

- Given 星火历史前三跟踪池有效
- When 查看 `2026-05-22`
- Then 应能得到盘后“次日卖出”清单与“继续持有”清单

- Given 某只卖出票在 `2026-05-22` 触发卖点
- When 调用 `/selection/daily-profile/{symbol}?date=2026-05-22`
- Then 返回值应包含 `entry_date / exit_signal_date / exit_date / exit_plan_summary`

## 6. 风险与回滚
- 风险：
  - 实时推理依赖本地 `postclose_exit_v0_2` 产物目录；
  - 目前历史跟踪池只覆盖 `selection_candidate_sources` 里已沉淀的星火候选日期；
  - 页面左侧新增两个分组后，用户会看到比原先更多的星火条目。
- 回滚：
  - 移除 `spark_opportunity_exit.py`
  - 回退 `selection_daily_workbench.py`
  - 回退 `SelectionResearchPage.tsx / SelectionDecisionPanel.tsx / src/types.ts`

## 7. 结果回填
- 实际改动：
  - 新增 `backend/app/services/spark_opportunity_exit.py`
  - 修改 `backend/app/services/selection_daily_workbench.py`
  - 修改 `src/components/selection/SelectionResearchPage.tsx`
  - 修改 `src/components/selection/SelectionDecisionPanel.tsx`
  - 修改 `src/types.ts`
  - 新增对应单测
- 验证结果：
  - `pytest backend/tests/test_selection_daily_workbench.py -q` 通过
  - 真数据验证：`2026-05-22` 当天星火跟踪池 18 个，其中次日卖出 5 个、继续持有 13 个
- 遗留问题：
  - 前端构建链当前环境缺本地 `vite/typescript` CLI，未在本次 worktree 完成整包构建
  - 更早历史段星火候选未回灌，跟踪池暂未覆盖 2024-09 起全历史

## 8. 归档信息
- 归档时间：2026-05-25
- Archive ID：
- 归档路径：
