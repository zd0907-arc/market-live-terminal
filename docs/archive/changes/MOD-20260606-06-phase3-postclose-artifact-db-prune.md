# MOD-20260606-06 Phase 3 旧盘后 artifact DB 瘦身

## 1. 基本信息
- 标题：Phase 3 旧盘后 artifact DB 瘦身
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-06-phase3-postclose-artifact-db-prune`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`, `CAP-NAS-OPS`
- 关联 STG：`MOD-20260606-03`, `MOD-20260606-04`, `MOD-20260606-05`

## 2. 背景与目标

`Phase 2` 已确认 `.run/postclose_l2` 是旧盘后兼容链路现场。  
继续细看后发现，这个目录约 `1.5G` 的主要来源不是 `report.json` 或 `worker_logs`，而是历史日期目录下的 `artifacts/worker_*.db`，总量约 `1.3G`。

这一批目标不是清空整个旧盘后目录，而是：

1. 保留状态摘要、当日 latest 对应目录、排障日志；
2. 删除历史日期的重型 `artifact db`；
3. 先把最重的冗余产物裁掉。

## 3. 方案与边界

- 做什么：
  1. 读取 `.run/postclose_l2/latest.json`，识别当前 latest 对应交易日。
  2. 删除早于 latest 交易日的 `artifacts/*.db`。
- 不做什么：
  1. 不删 `.run/postclose_l2/latest.json`
  2. 不删任何 `report.json`
  3. 不删任何 `atomic_config.json`
  4. 不删任何 `worker_logs/*.log`
  5. 不删 latest 对应当日目录

## 4. 执行步骤（按顺序）
1. 复核 `.run/postclose_l2` 的状态消费方只依赖 `latest.json` 与摘要文件。
2. 统计 `artifacts/*.db` 总量。
3. 删除早于 latest 交易日的历史 artifact db。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-06` 的 `.run/postclose_l2/latest.json` 指向 `20260521`，且历史 `artifacts/*.db` 总量约 `1.3G`。
- When 删除早于 `20260521` 的历史 artifact db。
- Then 应显著降低 `.run/postclose_l2` 体积，同时保留旧链路状态查看和摘要回溯能力。

## 6. 风险与回滚

主要风险：

1. 错删 latest 对应当日的 artifact db。
2. 错删摘要文件，影响状态查看。

回滚原则：

1. 这批删除对象属于旧链路历史中间产物，可通过原链路重跑重建。
2. 摘要文件和 latest 当日目录不在本批删除范围。

## 7. 结果回填
- 实际改动：
  - 删除 `.run/postclose_l2` 中早于 latest 交易日的历史 `artifacts/*.db`
- 验证结果：
  - `ops/check_postclose_l2_status.sh` 只读取 `.run/postclose_l2/latest.json`
  - `backend/scripts/run_postclose_l2_daily.py` 保留的摘要核心是 `latest.json`、`report.json`、`atomic_config.json`、`worker_logs`
  - 历史 `artifacts/*.db` 清理前总量约 `1.3G`
- 遗留问题：
  - `.run/postclose_l2` 仍保留大量旧摘要与 worker logs，后续可再决定是否继续只保留最近窗口
