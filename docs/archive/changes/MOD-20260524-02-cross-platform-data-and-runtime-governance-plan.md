# MOD-20260524-02 Mac 与 Windows 数据库和运行产物综合治理方案

## 1. 基本信息
- 标题：Mac 与 Windows 数据库和运行产物综合治理方案
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-02-cross-platform-data-and-runtime-governance-plan`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`
- 关联 STG：`N/A`

## 2. 目标

这份文档专门回答跨端问题：

1. Windows 端现在到底有哪些正式库、兼容库、运行产物。
2. Mac 端外置正式数据根里现在到底有哪些正式库、兼容库、研究缓存。
3. Windows -> Mac -> Cloud 这三端之间，哪些同步链路是正式主线，哪些只是兼容残留。
4. 后续如何在不误删、不打断跑数的前提下，逐步把数据库和运行产物收口。

## 3. 总结论

### 3.1 三端职责已经有主线，但“正式产物命名”和“旧链路残留”还没收干净

当前正式语义已经很清楚：

1. `Windows`：唯一正式外采节点、唯一正式跑数主站
2. `Mac`：同步后的本地正式研究消费端
3. `Cloud`：轻量盯盘和应急查看

但数据库与运行产物层还有两个核心问题：

1. **同一类正式产物在不同端名字不统一**
2. **旧 `market_data.db + merge_l2_day_delta.py` 链路仍活着，而新框架已经走 atomic / selection / model_feature_store 独立增量**

所以现在真正要治理的不是“删文件”，而是先把两套语义彻底分开。

### 3.2 当前最危险的不是 archive，而是“两套主线并存”

现在并存的是两套运行哲学：

#### 旧链路

- 核心对象：`market_data.db`
- 盘后总控：`ops/run_postclose_l2.sh`
- 关键 merge：`merge_l2_day_delta.py`
- 特征：L2 增量要 merge 回 Windows / Mac / Cloud 的 `market_data.db`

#### 新链路

- 核心对象：`atomic + selection + model_feature_store`
- 日跑入口：`ops/run_daily_new_framework.sh`
- 关键 merge：`merge_atomic_day_delta.py`、`merge_selection_day_delta.py`、`merge_model_feature_store_day_delta.py`
- 特征：不再以 `market_data.db` 作为唯一主库

当前治理重点就是：**不要让旧链路继续伪装成唯一正式主线，也不要在未完成切换前误删它。**

## 4. 远端实际核查结果

### 4.1 Windows 端

只读核查到的关键事实：

1. 项目根目录：`D:\market-live-terminal`
2. 数据目录：`D:\market-live-terminal\data`
3. 运行目录：`D:\market-live-terminal\.run`
4. 实时 crawler 日志确实在 `.run/` 下持续产出

关键数据对象：

- `D:\market-live-terminal\data\market_data.db`：约 `2.38G`
- `D:\market-live-terminal\data\selection\selection_research_windows.db`：约 `2.73G`
- `D:\market-live-terminal\data\selection\selection_research.db`：只有 `110KB`，明显是占位/兼容对象
- `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_smoke_20260401_20260515.db`：约 `73.7G`
- `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_smoke_20260401_20260515_bak_limit_prev_close_202509_three_rows_20260521_212756.db`：约 `39.3G`
- `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_validation_202605.db`：约 `1.8G`
- `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db`：只有 `241KB`，已不是正式有效主库

额外关键事实：

1. `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_compact_current.db` **不存在**
2. `selection_research_windows.db` 存在，`selection_research.db` 也存在，但后者只是占位
3. 这说明 Windows 端当前已经不是“full_reverse 主库”，而是“某个 compact smoke 文件承担实际主库角色”

### 4.2 Mac 端外置正式数据根

只读核查到的关键事实：

正式外置数据根：

- `/Users/dong/Desktop/AIGC/market-data`

关键数据对象：

- `market_data.db`：约 `4.6G`
- `selection/selection_research.db`：约 `3.2G`
- `selection/model_feature_store.db`：约 `4.3G`
- `selection/model_market_index_daily.db`：约 `768KB`
- `atomic_facts/market_atomic_mainboard_compact_current.db`：约 `64G`
- `atomic_facts/market_atomic_mainboard_full_reverse.db`：当前是 `0B`
- `market_heat/` 全目录：约 `364M`

额外关键事实：

1. Mac 端当前已经存在 `compact_current.db`
2. Mac 端 `full_reverse.db` 当前是空文件，已经不具备真实主库意义
3. 这意味着 **Mac 端已经基本切到 compact，Windows 端却还停留在“具体文件名 smoke 库”**

## 5. 跨端对象分类

### 5.1 正式主线对象

| 对象 | Windows | Mac | 当前角色 |
|---|---|---|---|
| `market_data.db` | `data/market_data.db` | `market-data/market_data.db` | 正式消费库，但属于旧主链核心对象 |
| `selection_research` 正式库 | `data/selection/selection_research_windows.db` | `market-data/selection/selection_research.db` | 生产端主写库 / 消费端主读库 |
| compact atomic 主库 | 当前实际是 `compact_smoke_20260401_20260515.db` | `atomic_facts/market_atomic_mainboard_compact_current.db` | atomic 主库，但两端命名未收口 |
| `model_feature_store.db` | 当前 Windows 侧仍是 smoke 名称 | `market-data/selection/model_feature_store.db` | 新框架正式派生产物 |
| `model_market_index_daily.db` | `data/selection/model_market_index_daily.db` | `market-data/selection/model_market_index_daily.db` | 新框架正式依赖前置库 |

### 5.2 兼容 / 过渡对象

| 对象 | 当前判断 |
|---|---|
| `selection_research.db`（Windows 110KB 版本） | 占位库 / 兼容名字，不是正式生产库 |
| `market_atomic_mainboard_full_reverse.db`（两端） | 兼容 fallback / 历史命名残留，不再是真实主库 |
| `ops/run_postclose_l2.sh` 及 `merge_l2_day_delta.py` | 旧盘后链路仍可运行，但不应继续冒充未来主链 |
| `sync_cloud_db.sh` | 旧 Cloud 整库拉回脚本 |
| `sync_local_to_cloud.sh` | 旧本地应急直抓再注入 Cloud 脚本 |
| `ops/sync_windows_research_snapshot.sh` | 过渡验证工具，不是正式同步方案 |

### 5.3 运行产物 / 可周期清理对象

#### Windows `.run/`

当前明确可见的运行族包括：

- `l2_postclose/`
- `postclose_l2/`
- `postclose_atomic/`
- `daily_new_framework/`
- `windows_new_framework_months/`
- `mac_sync_202502_202505/`
- `mac_sync_backfill_202506_202509/`
- `mac_sync_backfill_202510_202512/`
- `model_feature_store_batch/`
- `model_feature_store_smoke/`
- `postclose_sync/`
- `live_crawler*.log`

这些对象的共同特征是：

1. 大多是日跑/批跑产物，不是正式消费库
2. 但它们承载了“是否成功、产出了哪些 delta”的审计价值
3. 所以它们不能粗暴删除，而要先定保留周期

#### Mac 运行与研究缓存

- repo 内 `.run/`
- repo 内 `data/local_research/research_snapshot.db`
- `market-data/market_heat/cache/*`
- `market-data/market_heat/*.json/*.md` 大量实验输出

这些对象的问题不是体积最大，而是**最容易被误当作主数据源**。

## 6. 当前链路风险

### 6.1 风险 1：Windows 与 Mac 的 atomic 正式库命名不一致

当前真实情况是：

1. Mac：`compact_current.db` 已存在且承担正式读取角色
2. Windows：`compact_current.db` 不存在，真正大库是具体日期命名的 `compact_smoke_20260401_20260515.db`

这会造成两个问题：

1. 文档和脚本默认值会继续分叉
2. AI 很容易把 `smoke` 名称理解成“临时库”，但它实际上已经在承担正式主库角色

### 6.2 风险 2：Windows 的 selection 正式库和兼容库并存

当前真实情况是：

1. `selection_research_windows.db` 是真正的大库
2. `selection_research.db` 只是一个很小的占位库

这会让人和脚本都误判“哪个才是正式库”。

### 6.3 风险 3：旧 `market_data.db` 链路仍在正式入口里

当前真实情况是：

1. 文档层已说新框架日跑独立
2. 但 `ops/run_postclose_l2.sh` 仍在正式白名单中
3. 这条链路仍会把 L2 delta merge 回 Cloud / Windows / Mac 的 `market_data.db`

所以现在不是单纯的“老脚本还在”，而是**老脚本还在正式入口层**。

### 6.4 风险 4：Cloud 仍残留半中转职责

Cloud 按架构本该只是轻量盯盘库，但旧链路仍会往 Cloud merge `market_data.db`，说明它还残留历史中转语义。

### 6.5 风险 5：快照与研究缓存混入主阅读路径

以下对象最容易被误当主数据源：

1. `data/local_research/research_snapshot.db`
2. `data/local_research/selection/selection_research.db`
3. `market-data/market_heat/cache/*.json`
4. 各种 `*_latest.json`、`*_validation.db`、`*_smoke.db`

## 7. 解决方案

### 7.1 先冻结一张“正式产物清单”

这是第一优先级。

必须明确写死下面这张表，后续所有脚本、文档、AI 入口都按它解释：

| 类别 | Windows 正式对象 | Mac 正式对象 | 说明 |
|---|---|---|---|
| 主业务消费库 | `data/market_data.db` | `market-data/market_data.db` | 旧主链仍依赖 |
| atomic 主库 | 一个固定别名，不再直接用 `smoke_*` 文件名 | `atomic_facts/market_atomic_mainboard_compact_current.db` | 两端命名必须统一 |
| selection 正式库 | 一个固定正式名，不再让 `selection_research_windows.db` 和 `selection_research.db` 并列漂浮 | `selection/selection_research.db` | 建立主写/主读关系 |
| model feature 正式库 | 一个固定正式名 | `selection/model_feature_store.db` | 不再用 `smoke_*` 名称承载正式角色 |
| model index 正式库 | `selection/model_market_index_daily.db` | `selection/model_market_index_daily.db` | 保持一致 |

在这张清单没冻结前，不要删任何大库。

### 7.2 把“正式库名”和“物理大文件名”分开

建议做法：

1. 正式角色统一用稳定别名
2. 具体构建产物允许保留日期或 smoke 名称

例如：

- 正式别名：`market_atomic_mainboard_compact_current.db`
- 物理产物：`market_atomic_mainboard_compact_20260401_20260515.db`

现在 Windows 端缺的就是这一步。

### 7.3 把运行产物分成 3 桶

#### A. 审计保留桶

保留最近一个窗口，用于排障：

- `.run/daily_new_framework/*`
- `.run/postclose_atomic/*`
- `.run/postclose_l2/*`
- `.run/live_crawler*.log`

#### B. 可归档桶

批跑完成后可以压缩或外移：

- `.run/mac_sync_backfill_*`
- `.run/mac_sync_202502_202505/*`
- `.run/windows_new_framework_months/*`
- `.run/model_feature_store_batch/*`

#### C. 应降级为 legacy 工具桶

- `sync_cloud_db.sh`
- `sync_local_to_cloud.sh`
- `ops/sync_windows_research_snapshot.sh`

它们先不要删，但要从正式入口剥离。

### 7.4 把旧链路与新链路显式分家

后续必须在文档和脚本层同时明确：

#### 旧链路

- `run_postclose_l2.sh`
- `merge_l2_day_delta.py`
- `market_data.db` 中心化 merge

角色：`legacy-compatible`

#### 新链路

- `run_daily_new_framework.sh`
- `atomic / selection / model_feature_store` 增量

角色：`current-target`

只要这两个标签不钉死，后面还会持续混。

### 7.5 快照与缓存单独移出“正式数据语义”

建议后续单独建一条语义：

- `snapshot/validation-only`

把这些对象统一收进去：

1. `data/local_research/*`
2. `research_snapshot.db`
3. `market_heat/cache/*`
4. 各种 `*_smoke.db`
5. 各种 `*_validation.db`

目标不是马上移动文件，而是先让文档和脚本不再把它们当主输入。

## 8. 推荐执行顺序

### Step 1

先补“正式产物清单”文档，并把 Windows / Mac 两端正式库名固定。

### Step 2

给 Windows atomic / selection / model feature 建稳定正式别名，停止让 `smoke_*` 名称承担正式角色。

### Step 3

把 `run_postclose_l2.sh` 从“正式主入口”降级为“旧链路兼容入口”，把 `run_daily_new_framework.sh` 升成当前主线入口。

### Step 4

把 `sync_cloud_db.sh`、`sync_local_to_cloud.sh`、`ops/sync_windows_research_snapshot.sh` 从主阅读路径移开，统一标成 legacy/manual recovery。

### Step 5

给 `.run/` 和 `market-data/market_heat/` 制定保留周期：

1. 最近运行窗口保留
2. 历史批跑产物转归档或外移
3. 长期无引用的 smoke/validation 库再做清理

## 9. 当前不建议直接做的事

1. 不建议现在直接删 Windows 端 `selection_research.db`
2. 不建议现在直接删 `market_data.db`
3. 不建议现在直接删 `market_heat/cache`
4. 不建议现在直接删 `.run` 全目录
5. 不建议现在直接把 `full_reverse` 文件都删掉

因为现在真正的问题不是“哪些文件大”，而是“哪些名字还在承担错误语义”。

## 10. 这份方案之后该怎么接

最合适的下一步不是删文件，而是补两份东西：

1. 一份“正式产物清单”
2. 一份“运行产物保留策略”

这两份一旦写完，后面再做清理就不会靠猜。

当前已补：

1. [docs/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260524-03-canonical-data-artifacts-manifest.md)
2. [docs/changes/MOD-20260524-04-runtime-artifact-retention-policy.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260524-04-runtime-artifact-retention-policy.md)
