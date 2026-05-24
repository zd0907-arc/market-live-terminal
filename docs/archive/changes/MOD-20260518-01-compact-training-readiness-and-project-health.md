# MOD-20260518-01-compact-training-readiness-and-project-health

## 1. 基本信息
- 标题：compact DB 基线下 4-5 月重跑数据对现有系统支持度复核
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260518-01-compact-training-readiness-and-project-health`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 关联 STG：`STG-20260516-01-atomic-db-governance-compact-rollout-plan`

## 2. 背景与目标
- `main` 已切到 compact DB 基线，当前主仓基准为 `main @ 513119c chore: release 5.2.0 app baseline`。
- 当前并行 worktree 已明显收敛：主仓为 `main`，另有模型训练数据审计线 `codex/model-training-data-audit`。
- 用户这轮短期关注点已经收敛为一个问题：
  1. `2026-04` 到 `2026-05` 已重跑出来的数据，是否已经足以完整支撑现有系统页面和主链功能；
  2. 若还不能叫“完美支持”，具体缺口在哪里。
- 模型训练长期基线只保留为次级上下文，不作为本轮主验收条件。

## 3. 方案与边界
- 做什么：
  - 只读复核当前 worktree、compact 主链、模型训练数据审计线；
  - 重点核实现有系统页面/API 对 `2026-04` / `2026-05` 新重跑数据的真实依赖与覆盖；
  - 把“主链可用”和“完美支持”拆开评估；
  - 固化当前最关键的数据健康判断和后续治理优先级。
- 不做什么：
  - 不改业务代码；
  - 不改数据库 schema；
  - 不推进 merge / rebase；
  - 不处理模型训练实现；
  - 不处理 compact 兼容实现细节。

## 4. 执行步骤（按顺序）
1. 核实当前 worktree 和主线基准。
2. 核实 compact 基线对 review / selection / market heat / history multiframe 的覆盖情况。
3. 核实 `stock_universe_meta`、`history_*_l2`、`market_heat snapshot/cache` 这三处剩余风险。
4. 回填“主链可用性”和“完美支持差距”两套结论。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-05-18` 项目已经切到 compact DB 基线，
- When 只读复核 compact 主链与 `2026-04` / `2026-05` 新重跑数据，
- Then 必须明确区分：
  - 当前主链是否已可用；
  - 当前页面级功能是否已达到“完美支持”；
  - 若未达到，缺口是否会阻断主链，还是只造成质量退化。

## 6. 风险与回滚
- 风险：若把“接口 200 / 页面能开”误写成“4-5 月数据已经完美覆盖”，会掩盖真实数据来源和字段质量退化。
- 风险：若只盯 `atomic_limit_state_5m`，会错过当前更实际的缺口：`stock_universe_meta`、`history_*_l2`、`market_heat` 旧 snapshot/cache。
- 回滚：本卡只回退文档，不影响业务代码与数据库。

## 7. 结果回填
- 实际改动：
  - 新增本卡，沉淀 compact 基线下 4-5 月重跑数据对现有系统的支持度判断；
  - 同步 `07_PENDING_TODO.md`，回填主链数据质量缺口；
  - 追加 `AI_HANDOFF_LOG` 短日志。
- 验证结果：
  - 当前主仓 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal`
  - 当前主仓分支：`main`
  - 当前模型数据审计 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-model-data-audit`
  - 当前模型数据审计分支：`codex/model-training-data-audit`
  - compact 主线验证依据：
    - `scripts/compare_atomic_backend_modes.py`
    - `scripts/smoke_compact_research_station.py`
    - `docs/changes/STG-20260516-01-atomic-db-governance-compact-rollout-plan.md`
- 遗留问题：
  - 页面主链虽可用，但尚未达到“完美支持”，见本卡第 7.2 节。

### 7.1 当前项目状态结论

1. **主链能跑，compact cutover 对当前主链成立。**
   - 重跑后的 `2026-04` / `2026-05` 数据已经足够支撑 review、history multiframe、selection、market heat 主链接口与主要页面打开。
   - `scripts/smoke_compact_research_station.py` 在去掉本机 proxy 污染后，`25` 个 API 检查与 `8` 个页面检查的必需项均为 `0` 失败。

2. **但这还不能叫“完美支持”。**
   - 当前更准确的结论是：`现有系统主链可用，但仍存在 3 类非阻断、可感知的数据质量缺口`。
   - 这些缺口不会立刻打断主流程，但已经影响字段完整性、来源透明度和局部页面准确性。

3. **当前主要风险已经从“compact 能不能跑”转移到“哪些链路只是勉强能跑”。**
   - 本轮最该盯的是：
     - `stock_universe_meta`
     - `history_daily_l2 / history_5m_l2`
     - `market_heat` 的 snapshot/cache/atomic source 一致性

### 7.2 还不能叫“完美支持”的三个具体缺口

1. **`stock_universe_meta` 当前为空，导致复盘池和选股画像元数据退化。**
   - `stock_universe_meta` 在正式库和 repo 内本地库中均为 `0` 行。
   - `review/pool` 因此回退成 `name=symbol`、`market_cap=0.0`、`as_of_date=""`。
   - `selection/profile` / `selection/research-context` 虽仍可用，但 `market_cap` 为空，名称只能依赖其他 fallback 补齐。
   - 结论：**不阻断主链，但页面质量已退化。**

2. **`history_daily_l2 / history_5m_l2` 在 `2026-04-01` 到 `2026-04-10` 这段缺失，部分页面靠 fallback 继续工作。**
   - 正式库中 `history_daily_l2`、`history_5m_l2` 在这段日期没有行。
   - `/api/history/multiframe` 因 query 层会 merge atomic 数据，所以仍可能 `200` 且出数。
   - 但 `/api/review/data` 并不保证命中 atomic fallback；它也可能只是 `200 + 无数据`。
   - 当前业务层返回里的 `source="l2_history"`、`fallback_used=false` 也不能准确表达“实际来自 atomic merge”。
   - 结论：**主链能跑，但覆盖与来源表达都还不够干净。**

3. **`market_heat` 仍会读旧 snapshot/cache，且默认 atomic source 解析还可能落到空的 old full_reverse 库。**
   - `/api/market_heat/latest` 常见是在读旧 `latest.json` snapshot，里面残留的是旧 `full_reverse` 路径。
   - `market_heat` 默认 atomic 候选顺序里，compact 只有在显式开启 `ENABLE_ATOMIC_COMPACT_READ=1` 后才会参与候选。
   - 当前 old `full_reverse` 本机库是空库，导致 fine dashboard 的涨停/炸板补充统计可能全为 `0`。
   - 结论：**页面主体能开，但不是只有 lineage/meta 过期，局部统计准确性也已受影响。**

### 7.3 次级上下文：模型训练长期基线

1. 本轮不把“训练长期基线是否跑完”作为主验收条件。
2. 训练长期补数仍在进行中，这符合用户当前的实际操作方式，不构成本轮否定主链的理由。
3. 但后续若要把同一套数据正式作为训练主入口，仍需单独复核长窗覆盖和派生层重算，不与本卡混在一起下结论。

### 7.4 当前治理优先级

短期优先级应收敛为：

1. 先补 `stock_universe_meta`，恢复复盘池与选股画像的基础元数据完整性。
2. 再明确 `2026-04-01 ~ 2026-04-10` 的 `history_*_l2` 正式覆盖策略，并决定是否要把 atomic merge 显式标成 fallback/source。
3. 再处理 `market_heat` 的 snapshot/cache 清理与 compact atomic source 收敛，避免空 old full_reverse 继续污染统计。

不应再把主要精力放在：

- 继续争论 compact cutover 是否成立
- 回到旧 `atomic_limit_state_5m`
- 把“页面能开”直接等同于“数据质量已完全复原”

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
