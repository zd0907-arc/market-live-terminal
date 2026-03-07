# 09_30M_DIAGNOSIS_PLAN_2026-03-07（30分钟线问题诊断与修复方案）

## 1) 结论摘要
- 用户反馈成立：`sz000833`（粤桂股份）在 `2026-02-13` 存在日线与30分钟线明显不一致。
- 问题不是单票：watchlist 抽样显示同批日期窗口存在系统性偏差。
- 本次先完成“查清楚 + 方案”，暂不改核心逻辑代码（待用户确认后实施）。

## 2) 已核查事实（生产环境）

### 2.1 粤桂股份 `2026-02-13`
- 日线（`/api/history_analysis?source=sina`）`net_inflow ≈ +657,448,698.63`
- 日线（`/api/history_analysis?source=local`）`net_inflow ≈ +43,788,337.96`
- 30分钟线（`/api/history/trend` 当日合计）`net_inflow ≈ +38,420,764.30`

### 2.2 30分钟线结构异常（系统性）
- 异常日期窗口普遍出现 **10 bars/day**（应为 8 bars/day），并出现 `11:30` 与 `15:00` 时间点。
- 典型异常特征：**8 根 bar 的资金流为 0，但 OHLC 非 0**（占位K线）。
- 在 `2026-01-15` 到 `2026-02-13`、`2026-02-24` 到 `2026-02-27` 区间，watchlist 多票都出现该模式。

### 2.3 数据源完整性现状
- 生产库在部分历史日期（如 `2026-02-13`）`trade_ticks` 为 0，无法在云端用 raw ticks 反算校验 30m。
- 这意味着修复必须依赖 Windows 离线 ETL 历史源重建，而不是仅靠云端在线补算。

## 3) 根因判断

### R1. history_30m 混入“占位K线”数据
- `backend/scripts/fetch_local_data.py` 与 `backfill.py::_backfill_history_kline` 会写入 OHLC，但资金流字段全 0。
- 这类数据用于“先出图”可行，但未隔离到独立表，后续与真实资金流混合造成误读。

### R2. 30m 分桶口径在不同链路不统一
- ETL 与后端聚合的时间桶定义不一致（8/10 bar混用风险）。
- 历史数据一旦跨来源 merge，容易出现同日内部分 bar 为真实、部分 bar 为占位。

### R3. 云端缺 raw ticks 的日期无法自证
- 仅靠 `history_30m` 无法追溯真值，必须用 Windows 原始L2数据重建。

## 4) 修复方案（待确认后执行）

## Phase A：数据审计基线（只读）
- 生成 `symbol,date` 级审计表：`bar_count`、`sum_30m_net`、`local_daily_net`、`zero_flow_ohlc_count`。
- 目标：锁定受影响日期清单（按 symbol 细化）。

## Phase B：代码收敛（最小改动）
1. 统一 30m 时间桶口径为 8 bars/day（去除混用）。
2. 禁止“资金流=0 的占位K线”写入 `history_30m`（若要保留OHLC，移入独立表或显式标记来源）。
3. 为 `history/trend` 增加质量护栏（异常 bar_count 或占位比例过高时打告警日志）。

## Phase C：历史数据重建（Windows ETL）
1. 在 Windows 使用历史L2源重跑目标日期窗口，产出新 `market_data_history.db`。
2. 上传到云端，执行 `backend/scripts/merge_historical_db.py` 按日期删除后重写。
3. 发布后复核：`bar_count==8` 且 `zero_flow_ohlc_count==0`（或显著下降到可解释范围）。

## Phase D：验收门禁
- 核心票：`sz000833` + watchlist 其余票。
- 核心日：`2026-02-13` 与异常窗口抽样日。
- 验收标准：
  - 30m 每日 bar 数固定 8；
  - 不再出现“8根占位0流入 bar”模式；
  - 30m 日合计与本地日线口径偏差进入可解释范围（非硬性等值，因口径源不同）。

## 5) Windows 执行准备（已更新）
- 运行目录统一：`D:\market-live-terminal`
- 该路径已写入：
  - `docs/04_OPS_AND_DEV.md`
  - `docs/REMOTE_CONTROL_GUIDE.md`

## 6) 当前阻塞
- 远程自动化到 Windows 仍缺免密/交互凭据（当前 SSH 为密码认证，Agent 无法代输密码）。
- 可选处理：
  1. 用户在本机终端手动执行一次 `./sync_to_windows.sh`（输入密码）；
  2. 或配置 Windows SSH 公钥，后续全自动执行。
