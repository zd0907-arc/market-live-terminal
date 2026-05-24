# MOD-20260524-11 shadow db 与主链物理名治理

## 1. 基本信息
- 标题：shadow db 与主链物理名治理
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-11-shadow-db-and-mainchain-physical-name-governance`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-L2-HISTORY-FOUNDATION`

## 2. 这次治理回答的问题

这批不是在删库，也不是在动主链逻辑，而是在把“名字像实验、实际承担主链”与“真的只是 shadow / sample”分清。

当前最容易误导人的对象分两类：

1. 后端目录里的 shadow / sample 对象
2. Windows 实际承担主链，但物理名还带 `smoke` 的对象

## 3. 已确认的后端 shadow / sample 对象

| 对象 | 当前角色 | 结论 |
|---|---|---|
| `backend/market.db` | 空壳 | 不承担业务，不是正式运行库 |
| `backend/app/db/market_data.db` | 空壳 | 不承担业务，不是正式运行库 |
| `backend/app/market_data.db` | 小样本库 | 不是正式主链，但可作为样本/演示资产理解 |

这三项的主要问题不是线上会不会跑，而是：

1. 人看到路径会误以为它们还在被服务使用
2. 排障时可能误把它们当正式库入口

## 4. 已确认的主链物理名混淆对象

| 对象 | 当前正式语义 | 当前风险 |
|---|---|---|
| `selection_research_windows.db` | Windows 主写的每日选股研究库 | 容易被误看成临时库或并列正式库 |
| `compact_smoke_*` | 实际承担 atomic 盘后明细主链 | 容易被误看成试验库 |
| `model_feature_store_smoke_*` | 实际承担模型特征主链 | 容易被误看成烟测件 |

## 5. 本轮实际动作

### 5.1 shadow / sample 说明

已把下面对象明确成“非正式运行库”：

- `backend/market.db`
- `backend/app/db/market_data.db`
- `backend/app/market_data.db`

### 5.2 主链物理名说明

已把下面对象明确成“名字保留历史，但正式语义不变”：

- `selection_research_windows.db`
- `compact_smoke_*`
- `model_feature_store_smoke_*`

## 6. 当前结论

当前最重要的不是物理删除，而是：

1. 不让 backend shadow / sample 继续假装正式库
2. 不让 `smoke` 继续假装临时件
3. 把“正式主链语义”和“物理文件名”分开写

后续如果继续治理，更适合先做：

1. shadow / sample 的目录迁移规划
2. 主链物理名正式别名规划
3. 再决定是否进入代码治理
