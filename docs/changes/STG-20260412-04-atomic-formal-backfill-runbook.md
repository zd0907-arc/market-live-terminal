# STG-20260412-04 原子事实层正式回补执行方案（Windows 批量口径）

> 当前母卡入口：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`

## 1. 这张卡解决什么问题
本卡解决两件事：
1. **Windows 批量执行口径统一**：不再从 Mac 侧通过 SSH 拼长命令传一堆路径；
2. **正式回补批次方案落地**：给原子事实层提供可持续跑的本地 runner。

---

## 2. 本次新增的正式执行入口
### 2.1 Windows 本地 runner
- `backend/scripts/run_atomic_backfill_windows.py`

定位：
- Windows 本地读取 JSON 配置；
- 按批次、按交易日执行；
- 每天解压、处理、删临时目录；
- 最后统一重建 `limit_state`。

### 2.2 Windows 启动包装器
- `ops/win_run_atomic_backfill.bat`

定位：
- 避免手写超长命令；
- 固定 Python / ROOT / log 路径；
- 直接接受一个 config 路径。

### 2.3 配置模板
- `backend/scripts/configs/atomic_backfill_windows.sample.json`
- `backend/scripts/configs/atomic_backfill_windows.pilot.sample.json`

---

## 3. 本次解决的核心问题
### 3.1 路径问题
之前从 Mac 侧直接 SSH 调 Windows 命令时，长路径里的反斜杠容易被吃掉，导致：
- 生成错路径 DB 副本；
- 标准目录和实际产物不一致。

本次改成：
- **Mac 只负责同步脚本**；
- **Windows 本地自己读 config 执行**；
- 路径在 JSON / bat 中固定，不再通过 SSH 命令串传参。

### 3.2 解压策略
当前正式 runner 采用：
- **按天处理**；
- **处理完就删 staging**；
- 原始 `.zip/.7z` 保留不删；
- 默认 staging 根：`Z:/atomic_stage`。

这和当前机器磁盘约束是一致的：
- `D:` 原始包保留；
- `Z:` 负责 L2 全市场整日临时解压；
- 不做长时间全量展开。

---

## 4. 当前 runner 的真实能力
### 4.1 legacy 段（2025-01 ~ 2026-02）
- 输入：`YYYY-MM-DD.zip`
- 当前支持：
  - `atomic_trade_5m`
  - `atomic_trade_daily`
- 当前不做：
  - order / book / auction / phase（因为 raw 没有）

### 4.2 L2 段（2026-03+）
- 输入：`YYYYMMDD.7z`
- 当前支持：
  - `atomic_trade_5m`
  - `atomic_trade_daily`
  - `atomic_order_5m`
  - `atomic_order_daily`
  - `atomic_open_auction_l1_daily`
  - `atomic_open_auction_l2_daily`
  - `atomic_open_auction_phase_l1_daily`
  - `atomic_open_auction_phase_l2_daily`
  - `atomic_open_auction_manifest`
  - `atomic_book_state_5m`
  - `atomic_book_state_daily`
- 批次结束后统一生成：
  - `atomic_limit_state_5m`
  - `atomic_limit_state_daily`

---

## 5. 过滤范围（当前默认）
当前 config 默认：
- `include_bj = false`
- `include_star = false`
- `include_gem = true`
- `main_board_only = false`

即：
- **默认聚焦沪深，不跑北交所**；
- **默认不跑科创板**；
- 深交所主板 / 创业板可保留；
- 后续如要扩大范围，改 config，不改脚本。

### 5.1 当前已确认的真实目标池口径
以 `2026-04-01` 日包目录抽样：
- 原始目录总数：`7702`
- 去北交 / 去科创后的沪深总数：`7097`
- **沪深主板真实数：`3182`**
  - 上证主板：`1695`
  - 深证主板：`1487`
- 创业板：`939`

因此后续若按你的当前真实研究口径，推荐直接冻结：
- `include_bj = false`
- `include_star = false`
- `include_gem = false`
- `main_board_only = true`

这样正式日任务的真实池子约为 **3180+**，不再按 `7097` 的虚高口径估时。

---

## 6. 已完成验证
### 6.1 样板 4 只票
已完成：
- 利通 `sh603629`
- 中百 `sz000759`
- 贝因美 `sz002570`
- 粤桂 `sz000833`

### 6.2 正式 runner 冒烟
已用 `atomic_backfill_windows.pilot.sample.json` 在 Windows 跑通：
- `2026-02-27` legacy
- `2026-03-11` l2
- 4 只样板票
- 结果：`2` 个交易日、`8` 条 `limit_state_daily`，成功收口。

这说明：
- Windows 本地批量口径已经可用；
- bat + config + runner 组合能正常跑；
- 不再依赖 SSH 长命令传路径。

---

## 7. 推荐正式批次方案
### 阶段 A：先补 2026-02 全市场 legacy
目标：
- 先把老数据段最近一个月完整补齐；
- 验证全市场 legacy trade 层的吞吐与稳定性。

建议：
- 批次：`2026-02-01 ~ 2026-02-28`
- 口径：沪深、排除北交、排除科创
- workers：`6`
- staging：`Z:/atomic_stage`

### 阶段 B：再补 2026-03 ~ 当前全市场 L2
目标：
- 把 L2 段全量状态层补齐；
- 让后续复盘/选股直接建立在新底座上。

建议：
- 批次：`2026-03-01 ~ 当前已落地日`
- workers：`6`
- 若稳定，再提到 `8`

### 阶段 C：回补 2025 年 legacy
目标：
- 把旧 raw 的成交层价值尽量榨干；
- 为将来删除 raw 做准备。

建议：
- **按月回补**，不要一次跨全年；
- 每个月单独 state / report；
- 每月验一次条数和失败清单。

---

## 8. 当前仍保留的风险
1. `book_state` 的 `resting_amount` 仍是十档金额和，不是全盘口金额；
2. `limit_state` 仍是批次末统一重建，后续若量更大可再做成按日增量；
3. 全市场整日全解压会比较重，因此正式运行必须坚持：
   - 一天一处理；
   - staging 及时清理；
   - **L2 全市场整日解压固定走 `tar -xf` + `Z:` staging，不再使用 `G:` + `7z.exe` 作为正式主链路**；
   - 最新复测后，当前正式默认改为 **`12 worker`**，不再冻结 `8 worker`。

## 8.1 2026-04-12 新增踩坑结论
1. **Windows 数据治理统一盘位规则**：单票验证、全市场回补、bench、临时实验全部统一使用 `Z:`，不再使用 `G:`。
2. 已实测 `Z:` 是当前稳定高吞吐盘位；`G:` 已从未来执行口径中移除。
3. 2026-04-01 真实包（约 `5.30GB`）用旧稳定 prepare 路径可在约 `255.5` 秒完成 prepare，并切出 `7702` 个 symbol / `8` 个 shard。
4. 因此文档冻结：
   - **正式方案 = `Z:` + `tar -xf` + 单日 prepare + 12 worker**；
   - **禁止再次把 `G:` 用于 Windows 数据治理执行链路**。

---


## 8.2 G盘遗留目录处理原则
- `G:` 上历史遗留目录（如 `G:\tmp_*_validation`、`G:\atomic_bench_stage`、`G:\atomic_extract_*`）均视为旧实验残留，不再复用。
- 4只样板票的最终验证结果已经落到：
  - `D:\market-live-terminal\data\atomic_facts\litong_validation.db`
  - `D:\market-live-terminal\data\atomic_facts\zhongbai_validation.db`
  - `D:\market-live-terminal\data\atomic_facts\beingmate_validation.db`
  - `D:\market-live-terminal\data\atomic_facts\yuegui_validation.db`
- 因此只要没有进程占用，`G:` 这些临时目录都可以清理；它们**不是正式运行依赖**。

## 8.3 连续按月倒序正式回补口径
- 正式连续批次固定为：
  1. `2026-04`
  2. `2026-03`
  3. `2026-02`
  4. `2026-01`
  5. `2025-12 -> 2025-01` 按月倒序
- 中途不停月，不人工每月重启；统一由单一 config 串行推进。
- 查询时只看：
  - 当前正在处理哪一天
  - 已完成多少天 / 最后完成到哪一天

## 8.4 2026-04-12 性能剖析与第一轮提速结论
### 已做验证
1. `commit` 规则已做小样本对比：
   - `current_like`（逐 symbol commit）vs `batch_commit_4`
   - 结果：**写库时间和 lock_wait 确实下降，但总耗时几乎不变**
2. 第一版细粒度 profiling（优化前）：
   - 脚本：`backend/scripts/benchmark_atomic_detailed_profile.py`
   - 样本：`2026-04-01` L2 day root
   - `8` 个 symbol 样本平均：**≈ 5.147s / symbol**
   - live 吞吐：**≈ 15.46 symbol/min**
   - 对 `2026-04-01`（沪深非科创）约 `7097` symbols 估算：
     - **单日 wall time ≈ 7.6 小时**
3. 第一轮提速已落地：
   - 同一 symbol/day 改成 **只读 1 次 raw**
   - `order` 聚合改成向量化，不再 `groupby + lambda + loc`
   - `book` 金额与留存量改成向量化
   - `auction / phase` 改成复用同一份 raw frame，不再反复读盘
4. 第一轮提速后复测：
   - `8` 个 symbol 样本平均：
     - `load_bundle ≈ 0.987s`
     - `trade ≈ 0.595s`
     - `order ≈ 0.048s`
     - `book ≈ 0.199s`
     - `auction_l1 + auction_l2 + phase ≈ 0.067s`
     - **合计 ≈ 1.895s / symbol**
   - 单 symbol CSV 读取次数：
     - **15 次 -> 3 次**
   - 对 `2026-04-01` 约 `7097` symbols 估算：
     - **单线程理论 ≈ 3.74 小时**
5. 第二轮提速（trade 聚合去重）已落地：
   - `trade` 侧不再重复跑：
     - `compute_5m_review_bars`
     - `_bucket_stats_from_ticks`
     - `_build_trade_feature_maps`
   - 改成单次 bucket 聚合 + 单次 parent 聚合直接产出 rows + daily_feature
6. 第二轮提速后复测：
   - `8` 个 symbol 样本平均：
     - `load_bundle ≈ 0.900s`
     - `trade ≈ 0.288s`
     - `order ≈ 0.040s`
     - `book ≈ 0.177s`
     - `auction_l1 + auction_l2 + phase ≈ 0.061s`
     - **合计 ≈ 1.465s / symbol**
   - 对 `2026-04-01` 约 `7097` symbols 估算：
     - **单线程理论 ≈ 2.89 小时**
     - **8 worker 理想并行下 ≈ 21.7 分钟**

### 关键瓶颈结论
当前已经确认：
1. **旧瓶颈已被拆掉一大半**
   - 重复读盘
   - order 重复聚合
   - book 逐行 apply
   - auction / phase 重复清洗
2. 现在新的主要耗时变成：
   - `load_bundle`
   - `trade`（已压一轮，但在超大样本票上仍明显）
3. 说明下一轮若继续提速，应优先盯：
   - `ticks / order_events` 标准化
   - `load_bundle` 内 dataframe 标准化和清洗

## 8.5 2026-04-12 第三轮提速与正式 runner 多进程收口
### 已落地优化
1. `load_bundle` 再压一轮：
   - 先按 `time_text` 过滤连续竞价时段，再做 `datetime`
   - `pd.to_datetime` 改显式 `format='%Y-%m-%d %H:%M:%S'`
   - `OrderID` 对齐从 `set + sorted(list)` 改为 `Index.intersection()` 计数
2. 大票 `trade` 再压一轮：
   - 不再把 `buy_parent_total / sell_parent_total` map 回每一笔成交
   - 改成 **parent_bucket + parent_daily** 一次聚合，直接产出 L2 大单金额/计数
3. 正式 Windows runner 已从**线程单库**改成**多进程分片库 + 合并回主库**
   - 分片 worker 各自写 `worker_N.db`
   - 主进程顺序 merge 回正式原子库
   - 已修复 `DETACH DATABASE ... locked` 问题

### 最新实测（`2026-04-01`，沪深非科创）
1. 多进程 benchmark：
   - 脚本：`backend/scripts/benchmark_atomic_process_shards.py`
   - `8 process / 160 symbols`
   - 结果：`52.48s -> 39.20s`
   - 吞吐：`182.92 -> 244.91 symbol/min`
   - 推全市场 `7097` symbols：**≈ 28.98 分钟**
2. 正式 runner benchmark（已解压 day root）：
   - 配置：`atomic_backfill_windows.debug_reuse_20260401_160.json`
   - `8 worker / 160 symbols`
   - 结果：**≈ 40.19s**
   - 说明：正式 runner 的多进程分片 + merge 开销已基本收口，和 benchmark 基本一致
3. `10 / 12 process` 复测：
   - `10 process ≈ 136.68 symbol/min`
   - `12 process ≈ 161.33 symbol/min`
   - 结论：**当前机器仍以 8 process 最优**

### 当前结论
1. **计算链路目标已达成**：
   - 对“已解压的全市场单日目录”，正式 runner 已能把单日计算压到 **30 分钟以内**
2. **尚未最终收口的是全链路总耗时**：
   - 还需把“整日 `tar -xf` 解压 + 正式 runner”合并算总 wall time
   - 若总耗时仍超 30 分钟，下一轮优先继续压：
     - 整日解压 prepare
     - 解压与跑数的串并行衔接

## 8.6 2026-04-12 主板 3 天连续预演结果
### 预演配置
- 时间：`2026-04-01 ~ 2026-04-03`
- 口径：
  - `include_bj=false`
  - `include_star=false`
  - `include_gem=false`
  - `main_board_only=true`
- 并发：`8 worker`（旧基线）
- 解压：`tar -xf`
- DB：
  - `D:\market-live-terminal\data\atomic_facts\preflight_mainboard_3d_20260401_20260403.db`

### 结果
1. **3 天全部跑完，0 失败**
2. 全批次总耗时：
   - **`2365.61s` ≈ `39.43` 分钟**
3. 单日主板样本数：
   - `2026-04-01: 3182`
   - `2026-04-02: 3182`
   - `2026-04-03: 3183`
4. 平均单日 wall time：
   - **约 `13.14` 分钟 / 天**

## 8.7 2026-04-12 真实性能复测结论（替代旧默认）
### 单日完整链路复测
- 口径：`2026-04-01`、主板 only、从 archive 解压到正式原子库
- `8 worker`：`743.23s`（约 `12.39` 分钟）
- `12 worker`：`696.06s`（约 `11.60` 分钟）
- 结论：**`12 worker` 已超过 `8 worker`，成为当前最快正式口径**

### overlap / prefetch 复测
- `12 worker + prefetch_next_day_extract=true` 在 `Z:` staging 上实测触发：
  - `database or disk is full`
  - 次日 `tar -xf` 预解压失败
- 结论：**当前正式长跑不启用 overlap**；该能力保留，但要等后续 staging 容量或落盘策略再开。

### 落库验真
该 3 天预演库已验证存在以下落表结果：
- `atomic_trade_daily = 9547`
- `atomic_trade_5m = 465603`
- `atomic_order_daily = 9547`
- `atomic_order_5m = 465824`
- `atomic_book_state_daily = 9547`
- `atomic_book_state_5m = 458251`
- `atomic_open_auction_l1_daily = 9547`
- `atomic_open_auction_l2_daily = 9547`
- `atomic_open_auction_phase_l1_daily = 9547`
- `atomic_open_auction_phase_l2_daily = 9547`
- `atomic_open_auction_manifest = 9547`
- `atomic_limit_state_daily = 9547`
- `atomic_limit_state_5m = 465603`

### 抽样证明（已实查）
1. `atomic_trade_daily`
   - `sh600519 / 2026-04-01`
   - `total_amount = 4109050365.08`
   - `l2_main_net_amount = 130822839.04`
2. `atomic_order_daily`
   - `sz000008 / 2026-04-01`
   - `add_buy_amount = 2861956051.0`
   - `cancel_buy_amount = 61056443.0`
   - `oib_delta_amount = -406314227.7`
3. `atomic_book_state_daily`
   - `sh600519 / 2026-04-02`
   - `close_bid_resting_amount = 7149587.0`
   - `close_ask_resting_amount = 19020972.64`
   - `valid_bucket_count = 48`
4. `atomic_limit_state_daily`
   - `sz000008 / 2026-04-03`
   - `up_limit_price = 3.43`
   - `down_limit_price = 2.81`
   - `is_limit_down_close = 1`
5. `atomic_open_auction_l1_daily`
   - `sh600519 / 2026-04-03`
   - `auction_price = 14595.4`
   - `auction_match_amount = 11238458.0`

### 预解压重叠说明
- runner 已具备 `prefetch_next_day_extract` 能力；
- 若未来要启用 overlap，仍必须同时配 `reuse_extracted_day_if_exists=true`；
- 但 `2026-04-12` 最新复测已经确认：**主板 only + 12 worker + overlap 会把 `Z:` staging 顶爆**。

因此当前正式 config 明确冻结为：
- `prefetch_next_day_extract = false`
- `reuse_extracted_day_if_exists = false`

也就是说：**能力保留，但本轮正式长跑先不用。**

## 8.7 未来正式跑数的状态查询命令
统一使用：

```bash
bash /Users/dong/Desktop/AIGC/market-live-terminal-data-governance/ops/check_atomic_backfill_status_brief.sh <config文件名>
```

例如：

```bash
bash /Users/dong/Desktop/AIGC/market-live-terminal-data-governance/ops/check_atomic_backfill_status_brief.sh atomic_backfill_windows.preflight_mainboard_3d_20260401_20260403.json
```

返回的人话重点只看：
- 当前是否在跑
- 已完成多少天
- 最后完成到哪一天
- 当前已落库多少 `trade/order/book daily`

### 当前明确的优化方向
优先级冻结为：
1. **继续优化 load_bundle**
   - 评估 `逐笔成交 / 逐笔委托` 标准化是否还能再减少中间列与重复过滤
2. **继续优化 trade**
   - 重点看 `_build_trade_feature_maps / compute_5m_review_bars`
3. **预解压流水线** 只作为次优项
   - 在 raw 解析瓶颈未压下去前，不应把主要精力放在解压并行上

### 当前结论
第二轮提速后：
> **单 symbol 理论耗时已从 ~5.15s 降到 ~1.47s，累计降幅约 72%。**

并且最新真实 wall time 已经验证：
1. `8 worker`：`12.39` 分钟 / 天；
2. `12 worker`：`11.60` 分钟 / 天；
3. 当前正式默认直接切 `12 worker / no-overlap`。

## 9. 当前结论
这轮不是只写方案，已经真正落了：
- Windows 正式 runner
- bat 包装器
- config 模板
- pilot 冒烟验证

所以下一步不需要再讨论“怎么跑”，而是：
> **直接按阶段 A / B / C 进入正式回补。**

## 8.8 2026-04-12 正式主板批量回补最新冻结口径
- 正式 config：`backend/scripts/configs/atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json`
- 正式 DB：`D:\market-live-terminal\data\atomic_facts\market_atomic_mainboard_full_reverse.db`
- 当前口径固定：
  - `include_bj=false`
  - `include_star=false`
  - `include_gem=false`
  - `main_board_only=true`
  - `workers=12`
  - `prefetch_next_day_extract=false`
  - `reuse_extracted_day_if_exists=false`
- 备注：
  - `12 worker` 是当前最快真实可落地配置；
  - overlap 不是逻辑问题，而是当前 `Z:` staging 容量不足；
  - 因此正式长跑按 **12 worker / no-overlap** 执行。
- Mac 查询命令：

```bash
bash /Users/dong/Desktop/AIGC/market-live-terminal-data-governance/ops/check_atomic_backfill_status_brief.sh atomic_backfill_windows.mainboard_full_reverse_202604_to_202501.json
```
