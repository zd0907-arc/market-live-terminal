# MOD-20260606-08 Phase 3 根目录历史兼容库下沉

## 1. 基本信息
- 标题：Phase 3 根目录历史兼容库下沉
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260606-08-phase3-root-legacy-db-downscope`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`
- 关联 STG：`MOD-20260606-03`

## 2. 背景与目标

仓库根目录残留 `market_data.db` 与 `market_data_history.db` 两个历史兼容库。  
它们当前不是正式主链，但文件名极易误导，而且都不应长期占根目录。

这一批的目标不是删除它们，而是：

1. 保留旧 merge 脚本的兼容语义；
2. 把历史兼容库从仓库根目录下沉到 `data/legacy/`；
3. 让根目录更接近“只有代码和文档”的长期维护状态。

## 3. 方案与边界

- 做什么：
  1. 新建 `data/legacy/`
  2. 把根目录 `market_data.db` 下沉为 `data/legacy/root_market_data.db`
  3. 把根目录 `market_data_history.db` 下沉为 `data/legacy/root_market_data_history.db`
  4. 更新仅存的旧 merge 脚本，优先读取新位置，兼容回退旧根路径
- 不做什么：
  1. 不删 `data/market_data.db`
  2. 不删 `data/selection/selection_research.db`
  3. 不删 `data/market_data_history.db`

## 4. 执行步骤（按顺序）
1. 复核根目录兼容库的真实消费方。
2. 更新旧 merge 脚本路径解析。
3. 下沉两个根目录历史兼容库。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-06` 仓库根目录仍存在 `market_data.db` 与 `market_data_history.db` 两个高误导兼容库。
- When 将其下沉到 `data/legacy/` 并同步兼容脚本入口。
- Then 根目录不再堆放历史兼容大库，旧 merge 脚本仍可找到这些对象。

## 6. 风险与回滚

主要风险：

1. 旧 merge 脚本仍硬编码根目录路径，导致下沉后找不到库。

回滚原则：

1. merge 脚本已保留“优先新位置、回退旧根路径”的兼容逻辑；
2. 若需回滚，只需把文件再移回根目录。

## 7. 结果回填
- 实际改动：
  - 新增 `data/legacy/`
  - 下沉 `market_data.db` -> `data/legacy/root_market_data.db`
  - 下沉 `market_data_history.db` -> `data/legacy/root_market_data_history.db`
  - 清理根目录遗留的 `market_data.db-shm/.wal`、`market_data_history.db-shm/.wal`
  - 更新 `backend/scripts/merge_historical_db.py`
  - 更新 `backend/scripts/merge_historical_db_local.py`
- 验证结果：
  - 旧 merge 脚本现在优先读取 `data/legacy/*`，兼容回退旧根路径
- 遗留问题：
  - `data/market_data_history.db` 与 `data/market_data_history_202602_fix.db` 仍需在后续继续做“兼容 / 修复快照 / 是否归档”的角色收口
