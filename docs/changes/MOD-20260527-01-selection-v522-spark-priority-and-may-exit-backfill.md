# MOD-20260527-01-selection-v522-spark-priority-and-may-exit-backfill

## 1. 基本信息
- 标题：选股工作台 v5.2.2 星火优先、单源配额收紧与 5 月持仓回补
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260527-01-selection-v522-spark-priority-and-may-exit-backfill`
- 关联 CAP：`CAP-SELECTION-RESEARCH`

## 2. 背景与目标

用户确认本轮只处理当前主线里的每日选股工作台，不扩展到未来所有新策略的通用规则。

核心问题有四个：
- `每日综合候选` 里星火模型没有排在前面；
- `资金流回调稳健` 单日产出 10 条，过多；
- 星火持仓/卖出只落在 `2026-05-26` 一天，没有按实际日期分散；
- 持仓/卖出展示质量差，很多只显示代码，不显示名称。

同时还需要查清 `2026-05-25` 星火为什么没结果。

## 3. 方案与边界
- 做什么：
  - 在统一候选池聚合层增加来源优先级，确保星火排在策略前面；
  - 只把 `stable_capital_callback` 的单日上限从 `10` 收紧到 `3`；
  - 新增 5 月星火持仓/卖出月度回补脚本；
  - 前端右侧 `exit_watchlist` 一并补拉名称；
  - 升版本到 `v5.2.2`；
  - 回写契约文档，明确“模型源优先于策略源，配额按来源单独配置”。
- 不做什么：
  - 不把“每天最多几条”抽象成未来通用全局规则；
  - 不重跑 2026-05 全月星火买入推荐；
  - 不把 2024-09 以来全历史持仓都回灌；
  - 不提交并行开发中的 Spark pattern prototype 相关改动。

## 4. 执行步骤（按顺序）
1. 盘点库内 `2026-05` 星火候选、运行记录和持仓落库现状。
2. 修改 daily workbench 与候选聚合逻辑。
3. 修改选股页名称补拉逻辑。
4. 新增 5 月持仓/卖出月度回补脚本并执行回补。
5. 重跑 `2026-05-25`、`2026-05-26` 候选，重启本地服务。
6. 回写版本号与契约文档。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-05-25` 本地正式数据已同步完成
- When 运行当日选股刷新
- Then `spark_opportunity_selector` 应产出 3 条，不再是 0 条

- Given `2026-05-26` 的每日综合候选
- When 页面读取 `/api/selection/daily-candidates?date=2026-05-26&include_exit_watchlist=true`
- Then 排名前 3 应为星火候选，`stable_capital_callback` 只保留 3 条

- Given `2026-05` 的星火历史前三已沉淀在 `selection_candidate_sources`
- When 执行 5 月回补脚本
- Then `selection_exit_watchlist_daily` 应覆盖 `2026-05` 的实际交易日，而不是只集中在 `2026-05-26`

## 6. 风险与回滚
- 风险：
  - 星火日跑推理依赖本机 Python 环境与正式 selection/atomic/heat 库；
  - 5 月持仓回补脚本执行时间较长；
  - 持仓名称主要靠前端 quote 补拉，不等于后端源表名字质量已经彻底治理。
- 回滚：
  - 回退 `selection_candidate_store.py`
  - 回退 `selection_daily_workbench.py`
  - 回退 `SelectionResearchPage.tsx`
  - 删除 `backfill_spark_exit_watchlist_month.py`
  - 恢复版本号到上一版

## 7. 结果回填
- 实际改动：
  - 修改 `backend/app/services/selection_candidate_store.py`
  - 修改 `backend/app/services/selection_daily_workbench.py`
  - 修改 `src/components/selection/SelectionResearchPage.tsx`
  - 新增 `backend/scripts/backfill_spark_exit_watchlist_month.py`
  - 修改 `docs/selection/daily_candidate_source_contract.md`
  - 修改 `README.md`、`docs/04_OPS_AND_DEV.md`、`docs/AI_QUICK_START.md`
  - 修改 `package.json`、`package-lock.json`、`src/version.ts`、`backend/app/main.py`
- 验证结果：
  - 实际写库验证：`2026-05-25` 星火已从 0 条修正为 3 条；
  - 实际写库验证：`2026-05-26` 每日综合候选前 3 条已是星火；
  - 实际写库验证：`selection_exit_watchlist_daily` 已覆盖 `2026-05-06` 到 `2026-05-26` 共 15 个交易日；
  - 服务验证：本地后端 `8001` 和前端 `3001` 可正常启动。
- 遗留问题：
  - 当前仓库还有并行中的 Spark pattern prototype 改动，未纳入本次提交；
  - `docs/portfolio-ops/` 为用户未跟本轮合并的未跟踪目录，不纳入本次提交。

## 8. 归档信息
- 归档时间：2026-05-28
- Archive ID：
- 归档路径：
