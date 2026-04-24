# 选股数据治理与全量历史回补总说明（2026-04-12 收口版）

> **当前真实运行架构已更新：请优先阅读 `docs/changes/MOD-20260415-02-local-research-station-architecture.md`。**
>
> 若问题已经从“数据治理过程复盘”变成“当前项目主线现在到底怎么运行”，请再优先看：
> `docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`


> 本文档是这次“为选股研究重做数据底座”的**单文档总入口**。  
> 如果只看一份文档，优先看这份。

---

## 1. 这次改造的业务背景

这次不是单纯做 ETL，也不是单纯做复盘，而是为了支撑你后面的整个平台三件事：

1. **盯盘**
2. **复盘**
3. **选股**

其中当前最核心的新诉求是：

- 你已经有了较长历史数据；
- 现有系统更偏盯盘/复盘；
- 但现有数据层不够“可研究”，很难稳定支撑：
  - 主力隐蔽吸筹识别
  - 启动确认
  - 出货风险识别
  - 日后按全市场做规则扫描和回测

所以这次主线不是“先做选股页面”，而是：

> **先把原始成交 / 挂单数据治理成一套稳定、可复用、可扩展的原子事实层，再用它反过来支撑选股、复盘、盯盘。**

---

## 2. 当时冻结下来的总体规划

### 2.1 目标

把你已有两段历史原始数据，统一沉淀成一套新的原子事实层：

- `2025-01 ~ 2026-02`
  - 只有成交类历史数据（legacy）
- `2026-03 ~ 2026-04`
  - 有 L2 成交 + L2 挂单 + 行情快照

并且明确：

- **旧功能不能受影响**
- **旧表口径不乱改**
- 新能力先沉淀到**新库 / 新表 / 新链路**
- 先用单票和小样本反复验证，再做全市场长跑

### 2.2 为什么必须先做数据治理

因为如果底层只保留“简单日汇总”或“简单 5 分钟净额”，后面每发现一个新研究思路，就要重跑一遍原始数据。

这正是你最担心的点。

所以本次设计的原则是：

> **尽量一次性把原始数据榨干到“原子事实层”这一级，后面的策略、页面、研究都尽量只读这层，不再频繁回头重刷原始包。**

---

## 3. 最终落地的数据层设计

### 3.1 原子层的核心职责

原子层不是最终策略层，它只做两件事：

1. **把原始逐笔 / 委托 / 行情 / 竞价信息整理成标准化事实**
2. **保留足够多的细粒度证据，供未来选股 / 复盘 / 盯盘复用**

### 3.2 本轮最终落下来的核心表

#### 成交层
- `atomic_trade_5m`
- `atomic_trade_daily`

#### 挂单层
- `atomic_order_5m`
- `atomic_order_daily`

#### 盘口存量快照层
- `atomic_book_state_5m`
- `atomic_book_state_daily`

#### 集合竞价层
- `atomic_open_auction_l1_daily`
- `atomic_open_auction_l2_daily`
- `atomic_open_auction_phase_l1_daily`
- `atomic_open_auction_phase_l2_daily`
- `atomic_open_auction_manifest`

#### 涨跌停状态层
- `atomic_limit_state_5m`
- `atomic_limit_state_daily`

### 3.3 这套表想解决什么问题

它要同时支持：

- 只看成交就能做的分析
- 挂单 + 成交联动分析
- 看“主力是不是在偷偷吃货”
- 看“盘口托单/压单厚度”
- 看竞价阶段的独立行为
- 看涨跌停极端状态下的数据失真问题

也就是说，这一层已经不只是给“一个页面”准备，而是给未来的**整个平台研究能力**准备。

---

## 4. 这次是怎么一步一步落地的

### 4.1 第一阶段：先用单票把链路跑通

第一只重点样本是：

- **利通电子**

后来又补了 3 只不同风格的票做交叉验证：

- 中百
- 贝因美
- 粤桂

单票阶段的目标不是做策略，而是验证三件事：

1. 原始包能不能稳定抽出来
2. 新原子层表能不能稳定落下来
3. 新表能不能真的支撑我们对一只票做更深的复盘分析

### 4.2 第二阶段：补齐原子层缺口

在利通和其他样本复盘过程中，我们逐步确认了仅有成交净流入是不够的，于是继续补：

1. **涨跌停状态层**
2. **集合竞价层**
3. **盘口存量快照层**

这一步的意义是：

- 不是为了做更多表而做更多表；
- 而是为了把未来最可能反复用到的事实一次性沉淀下来。

### 4.3 第三阶段：从单票验证转向全市场回补

当单票链路跑通后，才转向全市场问题：

- 盘位用哪个
- 解压怎么做
- worker 开多少
- 临时目录怎么清
- 长任务怎么查状态
- 月份怎么逆序跑

这里的目标就变成：

> **把“可分析”变成“可长期执行”。**

---

## 5. 最后确定下来的正式跑数口径

### 5.1 范围

当前正式全量回补范围冻结为：

- **沪深主板 only**
- 不含：
  - 北交所
  - 科创板
  - 创业板

原因很简单：

- 这是你当前真实交易范围；
- 能立刻缩小任务规模；
- 不影响未来扩展。

### 5.2 时间范围

正式长跑配置当前是：

- `2026-04`
- `2026-03`
- `2026-02`
- `2026-01`
- `2025-12 ~ 2025-01`

即：

> **从新数据往前倒着跑。**

### 5.3 月份与日期的执行逻辑

正式任务是按配置里的 batch 顺序跑：

1. 先跑 `2026-04`
2. 再跑 `2026-03`
3. 然后一路往前到 `2025-01`

每个月内部则按自然日期正序读配置范围内存在的交易包。

当前真实执行的意义是：

- 先尽快把最近两个月最有价值的 L2 全量数据沉淀下来；
- 再回头吃老的 legacy 成交数据。

---

## 6. 这次跑数过程中踩到的关键坑

### 6.1 最大坑：盘位选错

中途曾经一度走偏到：

- `G:` 盘
- `7z.exe`

后来复核旧稳定方案才确认：

- 真正稳定高吞吐的是 **`Z:` staging**
- L2 全市场整日 prepare 的主链路应走 **`tar -xf`**

这一步修正后，解压速度和稳定性才恢复正常。

### 6.2 第二个坑：并发模型不对

之前慢的一大原因，是：

- 单库并发写
- 锁竞争重
- 每个 symbol 重复开关 sqlite

后来改成：

- **多进程分片**
- 每个 worker 写自己的 shard DB
- 主进程最后 merge 回主库

这一步是最关键的结构性提速。

### 6.3 第三个坑：单票内部重复读 / 重复算

之前同一只股票会反复读：

- 成交
- 委托
- 行情

并且 trade / order / auction / book 各自再做一遍处理。

后来统一收口为：

- 同一 `symbol/day` raw **只读一次**
- `trade / order / book / auction` 共用这份 prepared bundle

这一步把单票处理时间明显压下来了。

### 6.4 第四个坑：时间与 groupby 处理过重

后面又继续压了几个点：

- 先按交易时段过滤，再做 datetime
- `to_datetime(format=...)`
- `groupby(sort=False)`
- OrderID 对齐改 `Index.intersection`
- book 聚合去掉每个 bucket 的重复排序

这些属于一层一层抠出来的 CPU 时间。

### 6.5 第五个坑：overlap 会把 staging 顶爆

我们本来想进一步提速：

- 当天计算时预解压下一天

这个能力代码已经做了。

但真实压测后发现：

- **`12 worker + prefetch/overlap`**
- 在当前 `Z:` staging 上会触发：
  - `database or disk is full`
  - 次日预解压失败

所以当前正式口径明确改成：

- **不开 overlap**
- 先保证长期长跑稳定

---

## 7. 这次是怎么把速度一步步压下来的

### 7.1 初始痛点

你最开始最不接受的是：

- 如果一天要跑几个小时
- 那两三百天的数据就根本跑不完

这个判断完全正确，所以这次优化的目标非常明确：

> **必须把单日全市场回补压到一个能持续执行的级别。**

### 7.2 速度优化路径

#### 第 1 层：修正错误执行路径
- 从错误的 `G:` + `7z.exe` 回到 `Z:` + `tar -xf`

#### 第 2 层：单票内减少重复工作
- raw 只读一次
- order / book / auction 共用 prepared bundle
- 向量化替代部分逐行处理

#### 第 3 层：并发架构升级
- 线程 / 单库写
- 改成多进程 / 分 shard 库 / 最后 merge

#### 第 4 层：继续做局部 CPU 优化
- 时间转换
- groupby
- OrderID 对齐
- book 聚合
- sqlite pragma
- shard 内连接复用

#### 第 5 层：重新选正式 worker 数

真实复测后，不再迷信之前的旧结论，而是重新测：

- `8 worker`
- `10 worker`
- `12 worker`

最后确定：

- **当前主板 only 场景下，12 worker 最优**

### 7.3 当前最新真实速度结果

#### 小样本 benchmark
- `160 symbols`
  - `8 worker`: `33.29s`
  - `12 worker`: `31.58s`

#### 完整真实单日回补（主板 only）
- `2026-04-01`
  - `8 worker`: `743.23s` ≈ `12.39 分钟`
  - `12 worker`: `696.06s` ≈ `11.60 分钟`

所以本轮最终正式冻结为：

> **主板 only + Z: staging + tar -xf + 12 worker + no-overlap**

---

## 8. 这次全量回补的真实结果（2026-04-14 更新）

### 8.1 正式配置与正式库
正式配置文件：

- `backend/scripts/configs/atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json`

正式原子库：

- `D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db`

冻结口径仍是：

- 沪深**主板 only**
- `2026-04 -> 2026-03 -> ... -> 2025-01`
- `workers = 12`
- `extractor = tar`
- `prefetch_next_day_extract = false`
- `reuse_extracted_day_if_exists = false`

### 8.2 这次长跑真正跑到了什么程度
截至 `2026-04-14` 复核，正式批次的真实结果是：

- `completed_days = 307`
- `failed_days = 0`
- `last_completed_day = full_202501:2025-01-27`
- 最后一条主日志停在：
  - `rebuild_limit_state date_from=2025-01-01 date_to=2026-04-30`
- 错误日志明确报错：
  - `sqlite3.OperationalError: database or disk is full`

也就是说：

> **主数据按批次已经全部跑完，但最后统一回填 `limit_state` 时因为磁盘空间不足失败了。**

### 8.3 当前库里已经真正落下来的东西
当前正式库大小约：

- **`19.46 GB`**

当前已核实的主表行数：

- `atomic_trade_daily = 974571`
- `atomic_order_daily = 92396`
- `atomic_book_state_daily = 92396`
- `atomic_trade_5m = 47545635`
- `atomic_limit_state_daily = 0`

所以当前可以明确判断：

1. **trade 主数据已落完**
2. **order / book / auction 主数据已落完**
3. **缺口集中在最后一步 `limit_state` 统一回填**

### 8.4 为什么状态脚本还显示 running
因为当前卡住的是：

- Python 进程已经退出；
- `tar.exe` 也已经退出；
- 但 `state.json` 还停留在旧的 `status = running`。

所以它不是“还在偷偷跑”，而是：

> **任务已结束，但状态文件没有来得及收尾。**

这也是下一步 P0 需要单独修的一部分。

---

## 9. 现在可以怎么清空间（你手工删）

### 9.1 D 盘原始月包：已验过，可优先删
我已经复核了 `2025-01 ~ 2025-03` 这三个月：

- `D:\MarketData\202501`：`20.982 GB`
  - 已完成交易日：`18`
- `D:\MarketData\202502`：`26.561 GB`
  - 已完成交易日：`18`
- `D:\MarketData\202503`：`27.590 GB`
  - 已完成交易日：`21`

合计可释放约：

- **`75.133 GB`**

当前判断这三个月**可以删**，原因是：

1. 它们对应的交易日已经全部进入 `completed_days`；
2. 当前正式原子库里的主数据已经落下来了；
3. 现在缺的是 `limit_state` 收尾，不依赖重新保留这三个月 raw 才能继续；
4. 你前面也明确说过：`2025` 这段 legacy raw 的目标就是尽量榨干后再删。

### 9.2 D 盘原始包：建议先别删的部分
当前建议先保留：

- `2026-03`
- `2026-04`

因为这两个月是你目前最看重的 **L2 全量成交 + 挂单** 研究样本，后面还要继续支撑：

- `limit_state` 收尾后的抽样校验；
- 利通及其它样板票继续复盘；
- 后续新的 L2 派生思路验证。

### 9.3 Z 盘明显可删的临时/测试目录
以下目录都属于**bench / preflight / staging 临时产物**，不是正式结果库：

- `Z:\atomic_bench_extract\20260401`：`43.399 GB`
- `Z:\atomic_bench_stage\bench_20260401`：`43.399 GB`
- `Z:\atomic_bench_stage\bench_runner_20260401_10`：`43.399 GB`
- `Z:\atomic_bench_stage\bench_runner_20260401_160`：`43.399 GB`
- `Z:\atomic_preflight_stage_w12\preflight_mainboard_3d_overlap_20260401_20260403_w12`：`30.247 GB`
- `Z:\atomic_extract_bench_z\20260401`：`4.861 GB`
- `Z:\l2_stage_smoke\20260401`：`43.399 GB`
- `Z:\atomic_stage_profile_bench`：仅小型 bench DB，可删
- `Z:\atomic_writer_bench_small`：仅小型 bench DB，可删
- `Z:\atomic_bench_full_w8\*`：当前均为空壳
- `Z:\atomic_bench_full_w12\*`：当前均为空壳
- `Z:\atomic_preflight_stage\*`：当前均为空壳
- `Z:\atomic_stage\.worker_shards`：空目录，可删
- `Z:\atomic_stage\full_202501 ~ full_202604`：当前均为空目录，可删

### 9.4 Z 盘里你特别提到的 `l2_stage`
我已经盘过：

- `Z:\l2_stage\20260401`：`43.399 GB`
- `Z:\l2_stage\20260413`：`41.911 GB`

这两份更像是之前的 **L2 日级解压/审计测试目录**，不是正式原子库结果。

当前建议是：

- **如果你后面不打算继续直接拿这两个 stage 目录做 raw 审计，就可以删。**
- 如果你还想保留一个“L2 原始日目录样本”做人工对照，那就只留其中一天，另一份删掉也行。

### 9.5 当前盘位现实情况
本次复核时：

- `D:` 剩余约 **`7.18 GB`**
- `Z:` 剩余约 **`87.77 GB`**

所以现在最优先释放的仍然是：

1. `D:\MarketData\202501~202503`
2. `Z:` 上的大型 bench / stage 临时目录

---

## 10. P0 收尾结果（2026-04-14 已完成）

### 10.1 已完成的收尾动作
本轮 P0 已经做完：

1. **已单独补跑 `limit_state`**
   - 不重跑主数据；
   - 只基于现有正式原子库重建：
     - `atomic_limit_state_5m`
     - `atomic_limit_state_daily`

2. **已修正状态文件**
   - `state.json` 不再是假 `running`；
   - 当前状态已收口为 `done`。

3. **已生成正式 report / validation**
   - `D:\market-live-terminal\data\atomic_facts\runs\atomic_backfill_mainboard_full_reverse_report.json`
   - `D:\market-live-terminal\data\atomic_facts\runs\atomic_backfill_mainboard_full_reverse_validation.json`

### 10.2 当前收尾后的核心结果
当前已确认：

- `atomic_limit_state_daily = 974571`
- `atomic_limit_state_5m = 47545635`
- `state.status = done`
- `report.status = done`

### 10.3 关于“expected_day_count 变小”的解释
P0 收尾脚本里看到的 `expected_day_count = 250`，不是说历史主数据只跑了 `250` 天，而是因为：

- 这个数反映的是**当前 raw 存量快照**；
- 你已经手工删除了 `2025-01 ~ 2025-03` 的原始月包；
- 所以当前 raw 快照比最初完成的 `completed_days=307` 更小。

真正该看的是：

- `completed_days = 307`
- 月度落库覆盖
- 各主表 / `limit_state` 的最终行数

这三项现在都已经成立。

---

## 11. 现在这些数据和现有功能是什么关系

你的理解还是对的：

- 这次跑出来的是**新原子事实层库**；
- **还没有正式切进旧复盘 / 旧盯盘 / 旧选股页面**。

所以当前真实状态是：

1. **新底座已经基本建出来了；**
2. **但页面和接口还没有正式迁移到这套新底座。**

这也是故意这么做的，因为本轮一直遵守的红线就是：

> **先把新数据底座独立跑扎实，再决定怎么平移旧功能，不直接在旧链路上硬改。**

---

## 11.5 第一阶段迁移已完成什么（2026-04-14 晚）

为了遵守“**先迁移、验证没问题、再考虑删旧表/旧链路**”的原则，这一轮没有硬切旧接口，而是先做了**兼容 fallback 层**。

### 已落地的兼容策略
1. **复盘 / 历史多维旧接口不改返回结构**
   - 仍然走原来的：
     - `query_l2_history_5m_rows`
     - `query_l2_history_daily_rows`
     - `/api/review/*`
     - `/api/history/multiframe`
   - 但底层已新增：
     - **旧表有数据优先读旧表**
     - **旧表缺数据时自动读新原子表**
     - **同一 symbol/date 若两边都有，旧表优先，原子表只补缺口**

2. **复盘股票池也已接入原子表 bounds fallback**
   - `query_review_pool` 不再只依赖 `history_daily_l2`；
   - 当旧正式复盘表缺 coverage 时，可以从 `atomic_trade_daily` 补 symbol/date bounds；
   - 名称和市值仍优先复用旧 `stock_universe_meta`，不改旧元数据表。

3. **选股研究 L2 loader 也已接原子表 fallback**
   - `_load_l2_daily`
   - `_load_l2_5m_daily`
   - 现在会在旧 `history_daily_l2/history_5m_l2` 不足时，从新原子表补齐研究输入。

### 这一步的意义
这一步不是最终迁移完成，而是先实现：

> **现有复盘/历史查询链路在不改接口结构的前提下，已经具备“读新原子表”的能力。**

### 已做验证
已新增并通过：
- `backend/tests/test_atomic_review_fallback.py`
- 以及复跑：
  - `test_review_router.py`
  - `test_history_multiframe_router.py`
  - `test_selection_research.py`

当前这部分测试通过说明：
- review pool 可以从 atomic fallback 出数据；
- review data 可以从 atomic 5m/daily fallback 出数据；
- history multiframe 不被这次兼容改坏；
- selection research 可以从 atomic fallback 读 L2 输入。

## 11.6 第二阶段迁移新补了什么（2026-04-14 夜）

第一阶段解决的是“代码已经会 fallback”；第二阶段补的是“**部署和验收口径也明确下来**”。

### 这一步新增的内容
1. **统一 atomic DB 路径配置**
   - `backend/app/core/config.py` 新增统一候选路径函数；
   - 复盘 fallback 与选股 research loader 不再各自散落写默认路径；
   - Docker 侧显式支持：
     - `ATOMIC_MAINBOARD_DB_PATH`
     - `ATOMIC_DB_PATH`

2. **补齐 history multiframe 的 atomic-only 显式测试**
   - 新增 `backend/tests/test_atomic_history_multiframe_fallback.py`
   - 直接覆盖：
     - 旧 `history_daily_l2 / history_5m_l2` 为空
     - 只有 atomic 表有数据
     - `/api/history/multiframe` 仍可稳定返回 `1d / 30m`

3. **选股 research 新增 atomic-only 行情兜底**
   - 当本地 `local_history` 为空或覆盖不足时；
   - 现在允许用 `atomic_trade_daily` 映射出：
     - `close`
     - `net_inflow`
     - `main_buy_amount`
     - `main_sell_amount`
     - `activity_ratio`
   - 继续完成 feature / signal / profile 计算；
   - 也就是说，本地只要挂上正式 atomic DB，选股页不再必然因为缺 `local_history` 而整页空掉。

### 这一步的意义
到这一步，兼容迁移不再只是“本地函数层会 fallback”，而是进一步收口为：

> **配置层知道去哪里找 atomic DB，接口层也有 atomic-only 测试兜底。**

因此下一步就可以更稳地进入：
- 本地复盘页链路验收
- 选股 research / candidates / profile 验收
- 再决定哪些真实页面先切到新原子层

## 12. 接下来的建议顺序

最合理的顺序现在已经很清楚：

1. P0 已完成，下一步转为：
   - 复盘页接新原子层
   - 选股页特征建模 / 回测 / 接口映射
2. 后续新增日数据，直接沿用当前正式原子层 runner 做增量，不再回到这次历史长跑逻辑里。

也就是说，当前不是继续纠结“怎么设计原子层”，而是：

> **这次正式回补的 P0 已收尾，接下来应该进入功能对接和建模。**

---

## 13. 当前一句话总结

如果只用一句话概括现在的真实进度：

> **主板范围 `2026-04 -> 2025-01` 的原子主数据、`limit_state` 收尾和全量校验都已经完成，下一步就是把新底座真正接到复盘/选股能力上。**
