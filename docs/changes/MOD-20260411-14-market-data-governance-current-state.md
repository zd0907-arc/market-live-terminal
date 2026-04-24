# MOD-20260411-14 数据治理当前真实总方案（持续更新母卡）

> **数据治理主题总入口。**
> 若要看当前项目主线、当前目录、当前分支纪律与当前版本，请优先看：
> `docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`

## 1. 基本信息
- 标题：数据治理当前真实总方案（持续更新母卡）
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`, `CAP-HISTORY-30M`
- 关联 Task ID：`CHG-20260411-14`

## 2. 为什么要新增这张母卡
这条数据治理线已经经过多轮确认和纠偏：
- 先是“整体数据怎么处理”；
- 再到“原子事实层怎么设计”；
- 再到“字段差异 / P0 落库 / DDL / 脚本骨架”；
- 再到“集合竞价要不要单独处理”；
- 再到“集合竞价的 L1 / L2 分层怎么存”。

所以现在不能再让真实方案散落在很多张 STG 里。

## 这张母卡从现在开始作为：
## **数据治理唯一总入口 / 当前真实状态文档**

以后看数据治理，先看这张，再按需要下钻到分卡。

> 当前正式批量回补 runbook：`docs/changes/STG-20260412-04-atomic-formal-backfill-runbook.md`

> 2026-04-14 起，如果只想看**这次数据治理 + 全量历史回补的最新单文档收口结果**，优先看：`docs/changes/MOD-20260412-05-selection-atomic-backfill-retrospective.md`。

> 这张母卡继续保留为“数据治理主题总入口”；`MOD-20260412-05` 则是本轮正式回补的最新真实收尾说明。

---

## 3. 当前总目标（没有变化）
我们做数据治理，不是为了某一个页面，而是为了给系统补一套长期可复用的数据底座，稳定支持：

1. **盯盘**
2. **复盘**
3. **选股研究**

更具体地说，就是要做到：
- 以后大多数研究不再反复回 raw；
- L1 / L2、成交 / 挂单、主力 / 超大单能长期复用；
- 后面无论研究选股、复盘单票、还是做盘中/盘后对照，都尽量在统一底座上完成。

---

## 4. 当前已冻结的总体架构

### 4.0 治理迁移原则（本轮新增冻结）
- **旧库只读，不原地改造**
- **新库独立承接治理结果**
- 当前主库 / 旧表继续服务原盯盘、复盘、舆情，不插入高风险 schema 改造
- 原子事实层、竞价摘要层、后续 manifest 一律优先写入 **独立治理库**
- 后续如果要让页面/能力切到新底座，也必须先经过：
  1. 新库构建完成
  2. 新链路校验通过
  3. 页面/接口平移验证通过
  4. 再决定是否替换旧读链路

这条原则的目的不是“永远保留两套”，而是：
- 先把治理和验证放在新库完成；
- 避免在旧库上来回改，误伤现有功能；
- 降低大批量历史回填时的运行风险和回滚成本。

### 4.1 数据按两段处理
#### 第一段：`2025-01 ~ 2026-02`
- 只有成交 raw
- 没有真实挂单事件 raw
- 正确目标：**把成交级价值榨干**

#### 第二段：`2026-03+`
- 有 `行情.csv + 逐笔成交.csv + 逐笔委托.csv`
- 正确目标：**把成交层 + 挂单事件层一起做厚**

---

### 4.2 事实层和策略层彻底分开
#### 事实层
- 成交事实
- 挂单事实
- 竞价事实
- 质量与覆盖事实

#### 研究/策略层
- feature
- signal
- backtest
- 页面解释结果

原则：
- 事实层尽量一次性做厚；
- 策略层允许不断重算。

---

## 5. 当前真实数据底座设计（已收口）

### 5.1 连续竞价主原子层（当前主线）
这是目前已经进入 P0 落库执行阶段的主线：

1. `atomic_trade_5m`
2. `atomic_trade_daily`
3. `atomic_order_5m`
4. `atomic_order_daily`
5. `atomic_data_manifest`

作用：
- 支撑连续交易时段的盯盘 / 复盘 / 选股研究。
- 默认写入独立治理库 `market_atomic.db`，**不回写旧主库**。

### 5.2 开盘集合竞价摘要层（新补进来的子模块）
这是这两轮新增补充的部分：

1. `atomic_open_auction_l1_daily`
2. `atomic_open_auction_l2_daily`
3. `atomic_open_auction_manifest`

作用：
- 支撑集合竞价阶段的独立研究和后续 L1/L2 对照。
- 也优先落在独立治理库 / 独立 schema，不污染旧表。

### 5.3 盘口存量快照层（基础版已实现）
当前新增：

1. `atomic_book_state_5m`
2. `atomic_book_state_daily`

作用：
- 记录每个 `5m` bucket 结束时的盘口剩余厚度；
- 支撑“高位稳住 / 托单承接 / 压单强度”类复盘；
- 只覆盖 `2026-03+` 新数据段，不要求老数据段补齐。

当前基础口径：
- `resting_volume`：优先取 `叫买总量 / 叫卖总量`，缺失时 fallback 为十档量和；
- `resting_amount`：当前先按十档金额和落值；
- `15:00` 快照归并到 `14:55` bucket；
- 这层已接入 `run_symbol_atomic_validation.py`。
- `2026-04-12` 已在 Windows 对 4 只样板票完成实跑，全部成功。

### 5.4 为什么竞价层单独成组
因为已经通过 Windows raw 样本确认：
- 集合竞价不是普通连续竞价；
- 它至少包含：
  - `09:15~09:24:59` 的过程窗口
  - `09:25` 的边界点
- 所以不能再简单并入 `09:30` 第一根连续竞价 bar。

### 5.5 P1 增强设计已进入正式方案
- 当前新增正式设计卡：`STG-20260411-16-atomic-p1-enhancement-design.md`
- 定位：给 P0 主骨架补一批高复用事实字段，减少以后为了‘偷偷吃货 / 提前埋伏’反复回 raw。
- 当前冻结为两层：
  1. **P1-A（立即执行）**：母单数量、集中度、最大母单、单笔强度、OIB 连续性与集中度
  2. **P1-B（先记设计）**：复权因子、独立事件层、竞价 phase 细分、盘口存量
  3. **涨跌停状态层**：已进入专项设计，详见 `STG-20260412-01-limit-state-layer-design.md`
  4. **竞价 phase 过程层**：已进入专项设计，详见 `STG-20260412-02-open-auction-phase-layer-design.md`
  5. **盘口存量快照层**：基础版已实现并接入样板 runner，详见 `STG-20260412-03-order-book-state-layer-design.md`
- 原则：**先把高价值、低争议、直接来自 raw 的字段补进新库；仍有口径争议的，先冻结设计，不阻塞主线。**

### 5.6 当前新库的真实表组（截至 2026-04-12）
当前独立治理库已经稳定写入以下表组：

#### A. 连续竞价成交层
1. `atomic_trade_5m`
2. `atomic_trade_daily`

#### B. 挂单事件层
3. `atomic_order_5m`
4. `atomic_order_daily`

#### C. 盘口存量快照层
5. `atomic_book_state_5m`
6. `atomic_book_state_daily`

#### D. 集合竞价摘要层
7. `atomic_open_auction_l1_daily`
8. `atomic_open_auction_l2_daily`
9. `atomic_open_auction_phase_l1_daily`
10. `atomic_open_auction_phase_l2_daily`
11. `atomic_open_auction_manifest`

#### E. 涨跌停状态层
12. `atomic_limit_state_5m`
13. `atomic_limit_state_daily`

#### F. 配置 / manifest
14. `atomic_data_manifest`
15. `cfg_limit_rule_map`

当前可理解为：
- **老数据段**：只会真实落 A 组
- **新数据段**：A+B+C+D+E 组都会落

---

## 6. 当前已冻结的重要边界

### 6.1 价格口径
- 原子层 OHLC 一律按 **Raw Price / 未复权价格** 存；
- 复权因子独立处理，不污染原子事实主表。

### 6.2 时间桶口径
- 连续竞价 5m bar 一律按 **前闭后开 `[t, t+5m)`**。

### 6.3 集合竞价边界
- **必须和连续竞价隔离**；
- 但“最终怎么落得最优”仍可继续微调；
- 当前推荐方向是：**竞价单独成组，不塞进主 5m 表。**

### 6.4 L1 / L2 边界
- 白天实时可见的数据，和晚上盘后增强数据，必须分层保留；
- 不允许混成一份神视角结果。

### 6.5 正式执行范围边界（当前已重收口）
截至 2026-04-12，用户当前真实目标池已收口为：
- **沪深主板**
- 不含北交
- 不含科创
- 不含创业板

对应正式 config 固定参数：
- `include_bj = false`
- `include_star = false`
- `include_gem = false`
- `main_board_only = true`

这意味着：
- 预估真实池子约 `3180+`
- 不再按 `7097` 的虚高沪深总目录口径估时

---

## 7. 当前已经完成到哪一步了

### 7.1 文档层
已完成：
- 数据总方案
- 原子事实层设计
- 字段差异执行表
- P0 落库方案
- 集合竞价 raw 审计方案
- 集合竞价样本结论
- 集合竞价独立落库草案
- 集合竞价 L1/L2 摘要表草案

### 7.2 DDL 层
已完成：
- `atomic_fact_p0_schema.sql`
- `open_auction_summary_schema_draft.sql`

### 7.3 脚本层
已完成：
- `init_atomic_fact_db.py`
- `build_atomic_trade_from_history.py`
- `backfill_atomic_trade_from_raw.py`
- `backfill_atomic_order_from_raw.py`
- `audit_l2_auction_window.py`
- `build_open_auction_summaries.py`
- `build_limit_state_from_atomic.py`
- `build_book_state_from_raw.py`
- `run_atomic_backfill_windows.py`

### 7.4 Windows 样本审计层
已完成第一轮真实样本验证：
- `sh603629 @ 20260302 / 20260311 / 20260408 / 20260410`
- `sz000833 @ 20260311`

当前已经证明确认：
- 集合竞价 raw 确实存在；
- `order / quote` 对竞价过程覆盖更稳定；
- `09:25` 是强边界点。

### 7.5 Windows 正式批量口径（已落地）
当前已新增：
- `backend/scripts/run_atomic_backfill_windows.py`
- `backend/scripts/configs/atomic_backfill_windows.sample.json`
- `backend/scripts/configs/atomic_backfill_windows.pilot.sample.json`
- `ops/win_run_atomic_backfill.bat`

定位：
- 不再从 Mac 侧 SSH 拼超长路径命令；
- 改为 Windows 本地读取 JSON 配置执行；
- 日级解压、日级清理、批次末统一重建 `limit_state`。

### 7.5.1 当前正式 runner 的真实执行链路
按单个交易日，真实执行顺序是：

1. 发现当日 raw 包
2. 解压到 `Z:` staging
3. 枚举当日目标股票目录
4. 按 `8` 个 worker 做**多进程分片**
5. 每个 worker 写自己的 `worker_N.db`
6. 主进程顺序 merge 回正式原子库
7. 清理 worker shard 临时库
8. （若 config 允许）清理当日 staging
9. 全批次结束后统一重建 `limit_state`

这条链路已经替代旧的：
- 单 Python 进程 + 线程池 + 单库并发写

当前已冻结为：
- `Z:` staging
- `tar -xf`
- `12 worker`
- **多进程分片库 + merge 回主库**

### 7.5.2 当前已落地的提速方法（必须记住）
截至 2026-04-12，已经实装的提速点包括：

#### 单票内部提速
1. 同一 `symbol/day` raw **只读 1 次**
2. `order` 聚合改向量化
3. `book` 聚合改向量化
4. `auction / phase` 复用同一份 raw frame
5. 时间处理改为：
   - 先按交易时段过滤
   - 再 `to_datetime(format=...)`
6. OrderID 对齐改为 `Index.intersection`
7. `trade` 侧改为：
   - 单次 bucket 聚合
   - 单次 parent 聚合
   - 不再把 parent total 回填到每一笔成交

#### 全市场并发提速
8. 从“线程并发”切到“多进程分片”
9. 每个 worker 独立写 shard DB，避免单库写锁竞争
10. 最后 merge 回正式主库

#### 范围收口提速
11. 正式口径从“7097 目录级沪深总集合”收口到“3180+ 主板真实池”

#### 前后阶段重叠
12. runner 已支持预解压 / 次日复用能力；
13. 但 `2026-04-12` 实测确认：**主板 only + 12 worker + overlap/prefetch 会把 `Z:` staging 顶到 `database or disk is full`**；
14. 所以当前正式冻结为：
   - `prefetch_next_day_extract = false`
   - `reuse_extracted_day_if_exists = false`

也就是说，**overlap 能力保留，但当前正式批次默认关闭**。

### 7.5.3 当前真实测速结论
1. 旧口径（`7097`）下，计算链路已压到约 `28.98` 分钟
2. 主板口径（`3182`）下，计算链路推算约 `11.6` 分钟
3. 主板 3 天连续预演结果（旧基线）：
   - `2026-04-01 ~ 2026-04-03`
   - 总耗时：`2365.61s`
   - 平均：约 `13.14` 分钟 / 天
   - **3 天全成功**
4. 主板真实全日回补最新复测（新基线）：
   - `2026-04-01`
   - `8 worker`：`743.23s`（约 `12.39` 分钟 / 天）
   - `12 worker`：`696.06s`（约 `11.60` 分钟 / 天）
   - **当前最佳可落地口径 = `12 worker` + 不开 overlap**

### 7.5.4 为什么正式任务还会从 2026-04-01 重新跑
因为：
- 前面的 3 天预演结果落在**独立预演库**
  - `preflight_mainboard_3d_20260401_20260403.db`
- 当前正式任务落在**正式主库**
  - `market_atomic_mainboard_full_reverse.db`

也就是说：
- **预演库 = 验证用**
- **正式库 = 真正长期沉淀用**

所以正式批次从 `2026-04-01` 重新开始是**故意的**，不是重复失误。

### 7.5.5 当前测试产物 / 正式产物怎么区分
#### 正式产物
- `market_atomic_mainboard_full_reverse.db`

#### 预演 / bench / validation 产物
- `preflight_mainboard_3d_20260401_20260403.db`
- `debug_*`
- `bench_*`
- `*_validation.db`
- `*_test.db`

#### staging / shard 临时目录
- `Z:\atomic_stage\...`
- `Z:\atomic_preflight_stage\...`
- `Z:\atomic_stage\.worker_shards\...`
- `Z:\atomic_preflight_stage\.worker_shards\...`

当前原则：
- **正式任务正在跑时，不去动正式正在使用的 staging**
- 与当前正式任务无关的 preflight / debug / bench 产物，后续可以统一清理
- 清理动作要作为单独一次收尾，不在正式任务运行中间穿插

### 7.5.6 以后怎么查进度
Mac 统一查法：

```bash
bash ops/check_atomic_backfill_status_brief.sh atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json
```

返回只看 4 件事：
1. 当前是不是在跑
2. 正在处理哪一天
3. 已完成多少天
4. 最后完成到哪一天

### 7.6 利通验证窗口并行跑数（已完成第二轮）
`2026-04-11` 已在 Windows 用 `6` 个 worker 对利通验证窗口完成两轮并行跑数：
- 验证范围：
  - 老数据：`2026-02-01 ~ 2026-02-28`
  - 新数据：`2026-03-01 ~ 2026-04-10`
- 临时解压盘：
  - `Z:\atomic_validation`
- 验证结论：
  1. **可以按单票定向解压，不必整包全量展开**
     - 老数据 zip：可只抽 `603629.csv`
     - 新数据 7z：可只抽 `YYYYMMDD\603629.SH\*`
  2. 首轮结论曾暴露出：Windows 旧 `history_daily_l2 / history_5m_l2` 只覆盖利通 `2026-03-02 ~ 2026-03-13` 共 `10` 天，因此只靠旧主库底表无法补齐 trade 原子层。
  3. 第二轮已把 `run_symbol_atomic_validation.py` 改成：
     - 老数据：直接从 `603629.csv` raw 构建 `atomic_trade_5m / atomic_trade_daily`
     - 新数据：直接从 `逐笔成交.csv + 逐笔委托.csv` raw 构建 `atomic_trade_5m / atomic_trade_daily`
  4. 第二轮重跑结果已全量成功：
     - `44 / 44` 个任务成功
     - `0` 失败
     - `atomic_trade_daily = 44`（`2026-02-02 ~ 2026-04-10`）
     - `atomic_trade_5m = 2148`
     - `atomic_order_daily = 29`（`2026-03-02 ~ 2026-04-10`）
     - `atomic_order_5m = 1416`
     - `atomic_open_auction_l1_daily = 29`
     - `atomic_open_auction_l2_daily = 29`
     - `atomic_open_auction_manifest = 29`
  5. 因此当前已经正式确认：
     - **单票定向解压可行**
     - **老数据 trade raw-direct build 可行**
     - **新数据 trade/order/auction raw-direct build 可行**
     - 利通已经可以作为“新库治理样板票”继续往下做策略验证和全量回补规划。
     - **book state 基础版已可直接接样板重跑**
  6. `2026-04-11` 晚间已完成 **P1-A 字段对齐后的第三轮利通重跑**：
     - 同样是 `44 / 44` 成功、`0` 失败
     - 新增字段已在验证库中落值：

### 7.7 正式 runner pilot 冒烟（已完成）
已在 Windows 用 pilot config 跑通：
- `2026-02-27` legacy
- `2026-03-11` l2
- 4 只样板票

结果：
- `completed_day_count = 2`
- `limit_state_daily_rows = 8`
- bat + config + runner 全链路可用
       - `l2_main_buy_count / sell_count`
       - `max_parent_order_amount`
       - `top5_parent_concentration_ratio`
       - `order_event_count`
       - `oib_top3_concentration_ratio`
       - `moderate_positive_oib_bar_*`
       - `positive_oib_streak_max`
     - 说明 P1-A 已经不只是设计，已经进入利通样板实跑阶段。

---

## 8. 当前还没做完的真正治理任务

### A. 连续竞价主原子层
当前已推进到：
- `backfill_atomic_trade_from_raw.py` 已完成并在 Windows 真实样本 `sh603629 @ 2026-03-11` 跑通；
- 已验证可把 raw 里的 `trade_count / total_volume` 成功回填到 `atomic_trade_5m / atomic_trade_daily`。
- `backfill_atomic_order_from_raw.py` 已完成首版本地实现，并已在 Windows 真实样本 `sh603629 @ 2026-03-11` 跑通；当前已能从 raw 日包直接构建：
  - `atomic_order_5m`
  - `atomic_order_daily`
  - 并回填 `add/cancel amount + count + volume + cvd/oib`

还缺：
1. 把当前“单票验证窗口”推进到**批量股票 / 批量日期段**执行
2. 补月级 / 日期段批处理入口与 manifest 验证
3. 形成“先按股票回补还是先按日期回补”的正式执行方案
4. 用更多股票验证事件码分布、缺列样式、异常日包规模

### B. 集合竞价摘要层
当前已进入脚本试跑阶段，但还缺：
1. 批量回填更多样本
2. 把试跑结果并回统一 atomic DB
3. 更大样本校正字段定义
4. 再决定是否从“草案表”升级为正式 schema

### C. 管理与删 raw 前置验证
还缺：
1. manifest 按月回填
2. 覆盖审计
3. 删除前条件验证

---

## 8.1 基于利通样板票的原子层设计评估（2026-04-11 结论）

### 当前判断：**主骨架够了，但还不够“封顶”**

也就是：
- 现在这套 `atomic_trade_* + atomic_order_* + auction_*` 设计，
  **已经足够支撑未来大多数股票的复盘主流程**；
- 但如果目标是：
  - 找“偷偷吃货”
  - 做更稳的提前埋伏识别
  - 做更完整的驱动解释

  那当前原子层还需要补几类增强字段。

### 已被利通验证“够用”的部分
1. **成交主骨架够用**
   - `l1/l2 main/super buy/sell/net`
   - `open_30m / last_30m`
   - 正负 bar 数
2. **挂单主骨架够用**
   - `add/cancel amount`
   - `cvd_delta`
   - `oib_delta`
   - `buy_support_ratio / sell_pressure_ratio`
3. **竞价摘要够用作辅助层**
   - 适合做次日确认补充
   - 但还不够独立担任主判据

### 当前最需要补的增强项
#### P1-A：已进入本轮执行
1. `atomic_trade_5m / daily`
   - 母单数量类：`l2_main_buy_count / sell_count` 等
   - 集中度类：`top5_parent_concentration_ratio`
   - 最大母单：`max_parent_order_amount`
   - 单笔分布：`avg_trade_amount / max_trade_amount`

2. `atomic_order_5m / daily`
   - 事件总数：`order_event_count`
   - 更稳定的日级派生：
     - 连续正 OIB bar 段
     - 中等强度正 OIB bar 占比
     - OIB 集中度（是否只靠几根极端 bar）

#### P1-B：已写入正式设计，但不阻塞当前跑数
3. 状态增强（已进入专项设计）
   - `is_limit_up / is_limit_down`
   - `touch_limit_up / touch_limit_down`
   - 详见：`STG-20260412-01-limit-state-layer-design.md`

4. 复权与事件层
   - 独立 `adj_factor` / 复权因子表
   - 新闻 / 财报 / 公告 / 题材事件层

5. 竞价 phase 过程层
   - 当前已单独立卡：`STG-20260412-02-open-auction-phase-layer-design.md`
   - 方向：补过程分段，不上逐笔竞价明细库

### 当前不建议现在就硬补进主线实现的
1. 盘口存量快照类
   - `end_bid_resting_volume`
   - `end_ask_resting_volume`
   - 当前已单独立卡：`STG-20260412-03-order-book-state-layer-design.md`
   - 方向是对的，但必须先审 raw 是否能稳定支撑

2. 过度复杂的集合竞价 phase 细分
   - 原则已经对：必须隔离
   - 但具体怎么拆还没完全冻结，后续再单独讨论

### 一句话结论
如果只问：

> 现在这套原子层设计，够不够先把未来股票复盘主流程跑起来？

答案是：

> **够。**

如果再问：

> 够不够把“偷偷吃货 / 提前埋伏 / 驱动解释”做到更稳？

答案是：

> **还差一批 P1 增强字段 + 事件层。**

---

## 9. 当前推荐的执行顺序（2026-04-14 最新）

### Phase 1：P0 数据治理与全量回补
1. 主板 `2026-04 -> 2025-01` 原子事实层正式回补已完成
2. `limit_state` 已单独补齐
3. `state/report/validation` 已收口

### Phase 2：兼容迁移（当前主线）
1. 继续维持 **旧库只读 / 新库承接 / 旧接口不硬切**
2. 先让复盘链路和选股研究链路具备“旧表缺口 -> 原子表 fallback”能力
3. 明确部署口径，让本地 / Docker / Windows 都能显式挂接 `ATOMIC_DB_PATH`
4. 用接口测试确认：
   - `/api/review/*`
   - `/api/history/multiframe`
   - selection research loader
   在旧表为空时也能稳定吃到新原子层

### Phase 3：功能平移与建模
1. 先复盘页，再选股研究页
2. 在不改旧接口结构的前提下，把真实页面逐步切到新原子层
3. 等链路稳定后，再评估旧表/旧中间产物的下线

---

## 10. 当前这张母卡和其他文档是什么关系
### 这张母卡负责回答
- 现在真实方案是什么
- 已经做到哪
- 下一步干什么
- 哪些结论已经冻结

### 其他文档负责回答
- 细节设计
- 字段级说明
- 调研证据
- 单个子模块草案

也就是说：

## 以后优先看这张母卡，细节再往下钻。

---

## 11. 当前短结论
一句话总结现在的数据治理状态：

## 我们已经从“底座设计 + 全量回补”进入“新原子层 -> 旧功能兼容迁移”阶段；当前主线不是再设计表，而是稳步把复盘/选股读链路接到新原子层上。

### 7.8 全市场原子层回补解压口径纠偏（2026-04-12）
- 本轮已确认：此前新 runner 一度走偏到 `G:` + `7z.exe`，导致全市场整日 L2 解压吞吐异常。
- 重新对照旧稳定方案后确认：
  1. 旧稳定方案一直是 `Z:` staging；
  2. Windows prepare 使用的是 `tar -xf`，不是 `7z.exe` 主链路；
  3. `2026-04-01` 真实包（约 `5.30GB`）按旧 prepare 路径可在约 `255.5` 秒完成解压+切 shard；
  4. 30 秒短测里 `tar -> G:` 约 `1703` 项，`tar -> Z:` 约 `9682` 项，说明主要问题是盘位选错。
- 因此当前真实冻结口径变更为：
  - **全市场整日 L2：`Z:` + `tar -xf` + 单日 prepare + 12 worker**；
  - **正式长跑默认不开 overlap/prefetch**（避免 `Z:` staging 爆盘）；
  - **单票定向验证也统一切到 `Z:` 临时目录**。
- 这条结论已回填到总方案与 runbook，后续不得再把 `G:` 作为任何 Windows 数据治理默认盘位。
