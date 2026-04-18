# MOD-20260417-01 本地研究站当前真实状态（数据治理收口）

> **当前真实方案母卡。**
> 现在关于“数据治理做到哪、三端怎么分工、每天怎么跑、删旧表怎么验证”，统一先看本卡。

## 1. 当前结论

截至 `2026-04-17`：

- Windows / Mac / Cloud 三端职责已冻结；
- Windows -> Mac 首次 full processed DB 同步已完成；
- 日常盘后总控 `ops/run_postclose_l2.sh` 已实跑补齐到 `2026-04-15`；
- 本地 3 套正式库当前都已到 `2026-04-15`：
  - `data/market_data.db`
  - `data/atomic_facts/market_atomic_mainboard_full_reverse.db`
  - `data/selection/selection_research.db`
- 选股健康检查已验证 `latest_signal_date = 2026-04-15`；
- 当前状态可以视为：**本地研究站已进入可日用阶段**。

但同时要明确：

- **云端生产仍只保留轻量盯盘链路**；
- 不把 full atomic / full selection / 本地研究站整套能力直接发布到云端；
- 当前仍建议保留一段短观察期，确认连续多日盘后日跑稳定。

---

## 2. 三端职责（当前冻结真相）

### 2.1 Windows（数据主站 / 真相源）
负责：
- raw 原始日包落盘；
- 每日盘后跑数；
- full processed 主库产出；
- atomic / selection 正式结果生成；
- 对 Cloud 输出轻量盯盘增量；
- 对 Mac 输出 full processed 增量。

### 2.2 Mac（本地研究工作台）
负责：
- 主开发环境；
- 主使用环境；
- 本地复盘 / 选股 / 深度研究；
- 持有一份与 Windows 同口径的 full processed 库；
- 本地前后端启动与页面验收。

### 2.3 Cloud（轻量生产）
负责：
- 轻量盯盘；
- 手机端临时查看；
- 基于 `market_data.db` 的轻量历史/盯盘能力；
- 不负责承载 full atomic / full selection。

---

## 3. 当前正式数据目录

### 3.1 Mac 正式主库
- `data/market_data.db`
- `data/atomic_facts/market_atomic_mainboard_full_reverse.db`
- `data/selection/selection_research.db`
- `data/user_data.db`（本机独立保留）

### 3.2 已废弃的旧验证目录
以下内容已经退出主方案：
- `data/local_research/`
- 其下的 `research_snapshot.db*`
- 其下的旧 `selection_research.db*`
- 各类 `*.bak.* / *.wal / *.shm`

这些属于 **旧 snapshot 过渡验证产物**，不再作为正式数据源。

---

## 4. 当前“新表 / 老表”边界

## 4.1 新治理主线表（本轮数据治理后继续保留）

### A. `market_data.db` 中的新治理表
- `history_5m_l2`
- `history_daily_l2`
- `l2_daily_ingest_runs`
- `l2_daily_ingest_failures`
- `stock_universe_meta`

用途：
- 云端轻量盯盘；
- 本地复盘轻量历史；
- 选股 / 复盘基础日期口径；
- 元数据映射。

### B. atomic 正式库（全部属于新治理主线）
- `atomic_trade_5m`
- `atomic_trade_daily`
- `atomic_order_5m`
- `atomic_order_daily`
- `atomic_book_state_5m`
- `atomic_book_state_daily`
- `atomic_open_auction_l1_daily`
- `atomic_open_auction_l2_daily`
- `atomic_open_auction_phase_l1_daily`
- `atomic_open_auction_phase_l2_daily`
- `atomic_open_auction_manifest`
- `atomic_limit_state_5m`
- `atomic_limit_state_daily`
- `atomic_data_manifest`
- `cfg_limit_rule_map`

### C. selection 正式库（全部属于新治理主线）
- `selection_feature_daily`
- `selection_signal_daily`
- `selection_backtest_runs`
- `selection_backtest_trades`
- `selection_backtest_summary`

## 4.2 存量运行表（旧链路 / 兼容链路，但当前仍被运行时代码读取）

### A. 历史 / 实时旧链路表
- `history_1m`
- `history_30m`
- `local_history`
- `realtime_5m_preview`
- `realtime_daily_preview`
- `trade_ticks`

### B. 舆情存量表
- `sentiment_comments`
- `sentiment_daily_scores`
- `sentiment_events`
- `sentiment_snapshots`
- `sentiment_summaries`

注意：
- 这些表里很多虽然“旧”，但**现在还在跑**；
- 当前运行时代码仍直接读取它们，尤其是：
  - 盯盘 / 当日分时：`trade_ticks`、`history_1m`、`realtime_*`
  - 旧复盘 / 多维：`history_30m`、`local_history`
  - 舆情：`sentiment_*`
- 所以“旧表”≠“现在就能删”；
- 当前阶段必须按“**先副本验证，再迁移，再正式清理**”处理。

---

## 5. 你提的“删到回收站验证”方案，是否可行

### 结论
**思路可以，但执行方式要改：不要直接删正式库里的旧表。**

这个方法更适合做“最后一轮剥离验收”，不适合作为当前第一步。

### 为什么
因为现在旧链路表大量共存在 `market_data.db`：
- 如果直接删除表，回滚成本高；
- 一旦误删，旧页面/旧接口可能直接坏；
- 对 sqlite 来说，删表不是一个好的“灰度验证”方式。

### 正确做法
建议按下面顺序：

#### 方案 A（推荐）
1. **先保留正式库不动**；
2. 拷贝一份 `market_data.db` 到测试副本；
3. 在测试副本中按表组逐步删除存量表；
4. 让本地服务指向这份“删旧表测试库”；
5. 跑页面验收；
6. 若无问题，再决定是否正式清理。

#### 方案 B（次优）
1. 先把旧表所在旧库文件/旧备份移到回收站；
2. 不对正式主库做 drop；
3. 用“功能是否正常”反推是否还有隐藏依赖。

### 不推荐
- 不推荐直接在当前正式 `market_data.db` 上删旧表；
- 不推荐一边删表一边继续日跑；
- 不推荐未做页面验收就清空 `trade_ticks / local_history / history_1m / realtime_preview / sentiment_*`。

### 当前建议的验证顺序
1. 先验证“新治理主线库”本身是健康的（当前已到 `2026-04-15`）；
2. 再单独做“删旧表测试副本”；
3. 若页面坏，说明还有运行时依赖，需要继续切代码；
4. 若页面不坏，才能把对应表组列入正式清理候选。

---

## 6. 当前稳定性结论

### 6.1 已验证通过
- `ops/bootstrap_mac_full_processed_sync.sh`：首次整库同步通过；
- `ops/run_postclose_l2.sh`：补齐缺失交易日通过；
- `ops/check_postclose_l2_status.sh`：人话版状态查询可用；
- `2026-04-13 / 2026-04-14 / 2026-04-15` 已完成真实补跑；
- 跑数链路中曾出现的 Windows 路径/引号/selection export 问题已修复。

### 6.2 当前可认为已稳定的部分
- Windows prepare / shard / merge / cloud merge / Mac merge 主链路；
- Windows -> Mac selection / atomic day delta 回流；
- 本地选股健康检查；
- 本地研究站默认读 full processed 正式库。

### 6.3 仍建议继续观察的部分
- 连续多日自然盘后日跑是否还会出现新的 Windows SSH 特殊转义问题；
- selection day delta 导出在不同交易日上的稳定性；
- 旧页面对旧表的依赖范围。

---

## 7. 当前正式日常命令

### 7.1 首次整库同步
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal-local-research
bash ops/bootstrap_mac_full_processed_sync.sh
```

### 7.2 每日盘后正式入口
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal-local-research
bash ops/run_postclose_l2.sh
```

### 7.3 人话版状态查询
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal-local-research
bash ops/check_postclose_l2_status.sh
```

返回包含：
- 批次日志
- 当前状态
- 当前交易日
- 最近完成
- 已完成列表
- 最后进展

---

## 8. 当前是否可以发生产

### 结论
**不建议把本地研究站整套发到云端生产。**

### 原因
- 新架构已经冻结为：Cloud 轻量、Windows 数据主站、Mac 研究主站；
- 云端继续只保留轻量盯盘链路即可；
- 真正的新能力（atomic / selection / 深度复盘）应以本地工作站为主。

### 当前可发布的定义
- 可以把本轮代码作为**主线开发成果**合并 / 归档；
- 可以继续让云端使用轻量 `market_data` 更新；
- 但不应把 full processed / 本地研究站 UI 强行推成云端正式产品。

---

## 9. 下一步建议

### P0
把当前真实状态同步回核心文档（`02 / 04 / 07 / AI_QUICK_START / AI_HANDOFF_LOG`）。

### P1
连续几天做自然盘后日跑观察，确认链路完全稳定。

### P2
做“旧表依赖剥离验证”：
- 先做测试副本；
- 再删旧链路表；
- 用页面回归判断是否还有隐性依赖。

### P3
在确认旧依赖清楚后，再决定是否正式清理旧链路表。

---

## 10. 一句话结论

当前项目已经从“数据治理探索期”进入：

> **Windows 跑数、Mac 研究、Cloud 轻量盯盘 的可日用阶段**

接下来最重要的不是继续大改，而是：
- 收口文档；
- 观察稳定性；
- 做旧链路依赖剥离验证。
