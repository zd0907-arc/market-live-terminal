# MOD-20260524-05 数据与运行产物治理执行清单（业务审批版）

## 1. 基本信息
- 标题：数据与运行产物治理执行清单（业务审批版）
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-05-business-view-governance-execution-checklist`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`
- 关联文档：
  - [docs/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md)
  - [docs/changes/MOD-20260524-04-runtime-artifact-retention-policy.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260524-04-runtime-artifact-retention-policy.md)

## 2. 这份清单怎么用

这份表不是让你一次全批，而是后续一类一类过。

每次只看 5 件事：

1. 这个对象到底服务什么页面/功能。
2. 它现在是不是还在用。
3. 如果删错了，你能在系统里感知到什么。
4. 当前建议是保留、改名、归档还是以后退役。
5. 真要动它时，核心文档要同步改哪些。

当前阶段默认动作仍然是：不删。

## 3. 执行清单

| 对象类别 | 业务解释 | 现在是否还在用 | 删错/改错会影响什么 | 当前建议动作 | 何时可以动 | 必须同步回写的核心文档 |
|---|---|---|---|---|---|---|
| Windows `selection_research_windows.db` 与小号 `selection_research.db` | 每日选股研究主库与兼容占位库并存 | 是 | 选股研究页、候选池、策略结果可能断或错读 | 先保留，后做命名收口 | 当脚本和文档都能明确主写/主读映射时 | `01`、`03`、`docs/contracts/storage.md`、`04` |
| Windows `compact_smoke_*` 承担 atomic 主库角色 | 复盘/选股/热点研究底层明细实际主库 | 是 | 复盘明细、选股详情、热点底层数据会直接受影响 | 先保留，后补正式别名 | 当默认入口和兼容 fallback 都改完时 | `01`、`03`、`docs/contracts/storage.md`、`04` |
| Windows `model_feature_store_smoke_*` 承担正式特征库角色 | 模型训练特征主库 | 是 | 训练、特征验证、跑数核验会受影响 | 先保留，后补正式别名 | 当训练入口和文档都切到正式口径时 | `03`、`docs/contracts/storage.md`、`04` |
| `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db` | 后端目录里的 shadow / 样本对象 | 否，正式链不依赖 | 最主要是误导人以为它们仍是正式运行库 | 先补降级说明，样本库后续再做目录迁移规划 | 当仓库里明确不再把它们当正式排障目标时 | `01`、`03`、`docs/contracts/storage.md`、`08` |
| `market_atomic_mainboard_full_reverse.db` | 旧 atomic 兼容入口 | 部分兼容仍在 | 历史脚本、旧 fallback、部分研究说明可能断 | 先保留，后退役 | 当代码默认入口和文档都不再依赖它时 | `01`、`03`、`04` |
| `data/local_research/research_snapshot.db` 及其副本 | 本地研究站快照 | 是 | 本地快照研究站打不开或数据版本不对 | 保留当前 1 份 + 最近回退点 | 当确认有更新快照且页面验证通过时 | `04`、`08` |
| `market_heat/cache/fine_heat_snapshots_*.json` | 热点页面缓存 | 是 | 热点页可能变慢，或当前缓存窗口缺失 | 控量保留，不清空 | 当已确认更近窗口可用且页面不再依赖旧窗口时 | `04`、`08` |
| Windows `.run/daily_new_framework/*`、`.run/windows_new_framework_months/*` | 当前跑数/月批现场 | 是 | 你无法追踪当前批次进度和失败点 | 当前不动 | 等当前批次明确结束后 | `04`、`08` |
| `day_delta_*.db` 这类中间增量库 | 跑数中间件，不是正式库 | 部分在用 | 影响补跑、merge 核验和问题复盘 | 短期保留，后续清 | 当 merge 和 verify 都确认完成时 | `04`、`08` |
| `*_validation*` / `*_smoke*` 非正式验证产物 | 验收、烟测、结构校验 | 部分在用 | 主要影响复核，不该影响正式页面 | 阶段结束后归档或清理 | 当结论已写回文档时 | `04`、`08` |
| repo 内 `data/market_heat/market_heat.db` | 历史热点残留库，最容易误导 AI | 不确定，当前看不像正式主库 | 最主要风险是误读，不一定是页面立刻挂 | 暂不删，先标为高风险误导对象 | 当确认没有正式入口引用时 | `01`、`03`、`docs/contracts/storage.md`、`08` |

## 4. 后续一批一批怎么做

建议按下面顺序做，每次只处理一类：

1. 命名收口：先处理 3 条正式主链
   - `selection_research`
   - `atomic compact`
   - `model_feature_store`
   - backend shadow / sample db
2. 运行控量：再处理
   - 旧日志 / `.pid` / `.lock`
   - 已完成的 `day_delta_*.db`
   - 非当前窗口热点缓存
3. 快照压缩：最后处理
   - 本地研究站旧快照备份
   - 已结束批次的历史摘要

## 5. 文档回写规则

每次治理动作，如果改变的是：

- 系统角色和主线分工：改 [docs/01_SYSTEM_ARCHITECTURE.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/01_SYSTEM_ARCHITECTURE.md)
- 正式库/表/路径口径：改 [docs/03_DATA_CONTRACTS.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md) 和 [docs/contracts/storage.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/contracts/storage.md)
- 运行入口、同步方法、保留策略：改 [docs/04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md)
- 治理机制本身：改 [docs/08_DOCS_GOVERNANCE.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md)

不允许只改治理卡，不回写核心文档。
