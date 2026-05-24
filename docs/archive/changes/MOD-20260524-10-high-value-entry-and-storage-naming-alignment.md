# MOD-20260524-10 高收益入口与存储命名收口

## 1. 基本信息
- 标题：高收益入口与存储命名收口
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-10-high-value-entry-and-storage-naming-alignment`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 这次为什么还要改文档

前面几批已经把高混淆模块入口基本收住了，但重新盘点后发现，当前最容易继续把后续 AI 带偏的，不再是专题过程卡，而是几类默认入口和默认命名：

1. `README / AI_QUICK_START / 04_OPS_AND_DEV` 的版本和当前口径不完全一致
2. 外置 `market-data` 与 repo 内 `data/` 的正式 / 回退角色还不够显眼
3. `postclose-l2`、Windows 主站、策略研究交接材料里，旧兼容链仍然曝光过高

所以这批继续做的不是“再压历史文档”，而是把默认认知再收紧一层。

## 3. 本轮实际动作

### 3.1 统一当前版本口径

已更新：

- `README.md`
- `docs/AI_QUICK_START.md`
- `docs/04_OPS_AND_DEV.md`

现在三处都统一到当前版本 `v5.2.0`，不再出现默认入口页各说各话。

### 3.2 补清正式数据根目录与回退副本角色

已更新：

- `README.md`
- `docs/AI_QUICK_START.md`
- `docs/03_DATA_CONTRACTS.md`
- `docs/contracts/storage.md`

现在文档明确写清：

1. Mac 正式主读数据根目录是 `/Users/dong/Desktop/AIGC/market-data`
2. repo 内 `data/market_data.db`、`data/selection/selection_research.db` 只按回退 / 兼容副本理解
3. `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 的主写 / 主读语义继续固定

### 3.3 继续压低旧兼容链曝光

已更新：

- `docs/ops/postclose-l2-runbook.md`
- `docs/ops/windows-data-station.md`
- `docs/strategy-rework/README.md`
- `docs/strategy-rework/handoff-for-next-ai.md`

当前都明确写了：

1. `run_daily_new_framework.sh` 才是当前盘后正式主链
2. `run_postclose_l2.sh` 只是兼容旧链路
3. `strategy-rework/handoff-for-next-ai.md` 只适合历史追溯，不是当前默认先读入口
4. 旧 `full_reverse`、旧 worktree、旧实验入口只按历史语境理解

### 3.4 重排治理待办优先级

已更新：

- `docs/07_PENDING_TODO.md`
- `docs/changes/MOD-20260524-01-repo-governance-survey-and-cleanup-framework.md`

现在治理方向改成：

1. 先做最后一批高收益入口 / 命名收口
2. 再决定是否进入代码治理
3. 不再把“大面积继续压历史文档”当默认下一步

## 4. 当前结论

到这一步，项目治理线已经基本完成“先止血、再收口默认入口”的阶段。

当前剩余高收益点，已经从“文档入口太乱”缩小到更具体的几类命名对象：

1. `market-data` vs repo `data/`
2. `selection_research_windows.db` / `compact_smoke_*` / `model_feature_store_smoke_*`
3. `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db`
4. `data/market_heat/market_heat.db`

后续如果继续治理，更适合围绕这些对象做“命名收口 / 降级说明 / 目录迁移规划”，而不是再从大面积文档瘦身开始。
