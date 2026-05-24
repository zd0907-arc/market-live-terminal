# MOD-20260524-12 正式别名与 shadow/sample 目录迁移规划

## 1. 基本信息
- 标题：正式别名与 shadow/sample 目录迁移规划
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-12-formal-alias-and-shadow-sample-migration-plan`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 背景与目标

前一轮已经把“谁是正式角色、谁只是 shadow/sample”写清了，但还有两个现实问题没收口：

1. Windows 端承担正式语义的物理文件名仍然带 `smoke` 痕迹。
2. 后端目录里的 `market.db` / `market_data.db` 样本对象还没有迁到更不容易误读的位置。

这份卡只回答一件事：**先把正式别名和迁移顺序定死，再决定是否动文件。**

### 2.1 当前状态快照

| 对象 | 当前物理状态 | 目标正式语义 | 现在卡点 |
|---|---|---|---|
| `atomic_compact_main` | Windows 仍以 `compact_smoke_*` 承担主链 | 稳定正式别名 | 别名未物理落地，不能先改脚本默认路径 |
| `model_feature_store_main` | Windows 仍以 `model_feature_store_smoke_*` 承担主链 | 稳定正式别名 | 同上 |
| `backend/market.db` | 空壳 / shadow | 只保留为非正式对象 | 需要先定目标目录再谈搬迁 |
| `backend/app/db/market_data.db` | 空壳 / shadow | 只保留为非正式对象 | 同上 |
| `backend/app/market_data.db` | 小样本库 | 样本/演示资产 | 需要明确它是否要转 archive 还是留作样本 |

## 3. 方案与边界
- 做什么：
  - 确认 Windows 端 `atomic_compact_main`、`model_feature_store_main` 的稳定正式别名；
  - 确认后端 `shadow/sample` 对象的目标目录与用途；
  - 明确哪些脚本只改默认值，哪些脚本只改文档口径，哪些才允许后续做物理迁移。
- 不做什么：
  - 不直接删库；
  - 不直接重命名现有大文件；
  - 不先动主链跑数逻辑；
  - 不在没有 alias 落地前把 `smoke` 物理名硬替换成不存在的新文件名。

## 4. 执行步骤（按顺序）
1. 盘点仍直接引用 `compact_smoke_*`、`model_feature_store_smoke_*`、`backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 的脚本和文档。
2. 给 Windows 正式主链定义稳定的“业务别名 -> 物理文件名 -> 默认入口”映射。
3. 给 `backend shadow/sample` 定义迁移目标目录和保留策略，先统一文档，再考虑物理搬迁。
4. 在核心文档里同步回写正式别名、兼容入口和迁移边界。
5. 等别名和迁移目标都定清后，再逐个收代码默认值，最后才考虑物理重命名。

### 4.1 后续代码面只看这几处

| 文件 | 现在承担什么 | 后续目标 |
|---|---|---|
| `backend/app/core/config.py` | atomic 默认候选与回退顺序 | 把正式别名与兼容回退分开写清 |
| `ops/start_local_backend_with_atomic.sh` | 兼容直启入口 | 继续只做兼容排查，不冒充默认主线 |
| `backend/scripts/build_local_research_snapshot.py` | 本地研究快照生成 | 只认正式别名，不再默认读旧兼容名 |
| `ops/sync_windows_research_snapshot.sh` | 旧快照同步工具 | 明确为兼容/验证工具 |
| `backend/scripts/run_daily_new_framework.py` | 新框架日跑总控 | 保持正式主链，不回头依赖旧语义 |
| `backend/scripts/run_windows_new_framework_months.py` | Windows 月批 / 阶段跑 | 只处理正式产物，别名收口后再同步默认值 |

## 5. 验收标准（Given/When/Then，绝对时间）
- Given 2026-05-24 之后的新治理轮次；
- When 新 AI 只读 `docs/` 核心文档和这张卡；
- Then 它能直接判断：哪些是正式主链、哪些是兼容残留、哪些是样本对象，且不会误把 `smoke` 当成临时库。

## 6. 风险与回滚
- 风险：过早迁移会打断仍在跑的历史批次。
- 回滚：在正式别名未稳定前，任何物理迁移都不执行；只保留文档和入口层收口。

## 7. 结果回填
- 实际改动：无
- 验证结果：待办与代码引用已确认仍存在混淆
- 遗留问题：正式别名、目录迁移顺序、回写范围待定

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
