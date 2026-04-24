# INV-20260410-01 利通电子数据审计与原始包解析缺口

> **历史过程卡。**
> 当前项目主线 / 当前目录 / 当前版本 / 当前分支纪律，请优先看：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 当前数据治理主题真实状态，请优先看：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`


## 1. 基本信息
- 标题：利通电子（`sh603629`）原始数据审计与解析缺口定位
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260410-01`

## 2. 目标
- 先确认利通电子近期“看不到 / 看不全 / 事件因子为空”到底是：
  1. 原始数据缺失；
  2. 正式入库缺口；
  3. 清洗脚本解析错误；
  4. 本地与 Windows / 云端环境漂移。

## 3. 本轮核验范围
- 标的：`sh603629`
- 本地库：`data/market_data.db`
- Windows 正式库：`D:\market-live-terminal\data\market_data.db`
- Windows 原始包：
  - `D:\MarketData\202602\2026-02-27.zip`
  - `D:\MarketData\202603\20260309.7z`
  - `D:\MarketData\202603\20260311.7z`
  - `D:\MarketData\202603\20260316.7z`
  - `D:\MarketData\202603\20260317.7z`
  - `D:\MarketData\202603\20260318.7z`

## 4. 结论摘要

### 4.1 `2025-01 ~ 2026-02` 不是“无 L2”，而是“只有成交级、没有挂单事件级”
- Windows `2026-02-27.zip` 抽样确认：包内只有 `603629.csv` 单文件。
- 文件头包含：
  - `TranID/Time/Price/Volume/Type`
  - `SaleOrderID/BuyOrderID`
  - `SaleOrderVolume/BuyOrderVolume`
- 这说明：
  - 可以做**成交级母单归因**，即 `l2_main/super buy/sell`；
  - 但**不能**恢复真实 `add/cancel/oib` 挂单事件层。
- 因此：
  - `2025-01 ~ 2026-02` 的 `l2_add_* / l2_cancel_* / l2_oib_delta` 为空，属于**源数据边界**，不是 bug。

### 4.2 `2026-03+` 原始包里确实有挂单数据
- Windows `20260311.7z` 抽样确认，利通目录下存在：
  - `行情.csv`
  - `逐笔成交.csv`
  - `逐笔委托.csv`
- 原始挂单文件 `逐笔委托.csv` 的真实编码不是旧脚本假设的 `0/1/U`，而是：
  - `A` = add
  - `D` = cancel
  - `S` = 特殊/状态类行（非买卖挂单）
- 所以：
  - 原始包里**有挂单事件**
  - 但旧解析脚本没有正确识别，导致事件层被误丢。

### 4.3 当前清洗链路存在两层问题
1. **解析层 bug**
   - 旧 `backend/scripts/l2_daily_backfill.py` 只识别 `0/1/U`
   - 对 Wind 这批 `A/D` 事件码不兼容
   - 结果：`order_event_rows=0`，`l2_add_* / l2_cancel_* / l2_oib_delta` 全空
2. **环境/版本漂移**
   - Windows 正式库 schema 仍是旧版
   - 缺 `total_volume / l2_add_* / l2_cancel_* / l2_cvd_delta / l2_oib_delta / quality_info`
   - 说明 Windows 正式跑数机还没切到最新增强链路

### 4.4 本地还存在单票覆盖缺口
- 本地 `data/market_data.db` 中，利通原来缺少 `2026-03-09`
- 但 Windows 原始包存在，且 dry-run 可成功生成 `49` 条 5m + `1` 条 daily
- 这说明 `2026-03-09` 属于**本地环境漂移 / 未同步**，不是原始缺失。

## 5. 本轮已落地修复

### 5.1 已修本地解析脚本
- 已更新：`backend/scripts/l2_daily_backfill.py`
- 新增兼容：
  - `A -> add`
  - `D -> cancel`
- 并新增测试：
  - `backend/tests/test_l2_daily_backfill.py`

### 5.2 已验证修复生效
- 本地抽样 `2026-03-11`，修复后：
  - `order_event_rows = 176089`
  - `order_add_rows = 126898`
  - `order_cancel_rows = 49191`
- 说明原始挂单事件已被成功识别。

### 5.3 已对本地利通关键日做单票回补
- 已回补到本地 `data/market_data.db`：
  - `2026-03-09`
  - `2026-03-11`
  - `2026-03-16`
  - `2026-03-17`
  - `2026-03-18`
  - `2026-03-19`
  - `2026-04-01`
- 回补后本地利通 5m 事件层已可读：
  - `2026-03-09`：`add_buy/add_sell/cancel_buy/cancel_sell/cvd/oib` 全部有值
  - `2026-03-11`：同上
  - `2026-03-16 ~ 03-18`：同上
  - `2026-03-19`：同上
  - `2026-04-01`：同上

### 5.4 已补齐利通 `2026-03-02 ~ 2026-04-10` 全窗口事件层
- `2026-04-11` 已继续从 Windows 原始 `7z` 单票抽回并写入本地：
  - `2026-03-02`
  - `2026-03-03`
  - `2026-03-04`
  - `2026-03-05`
  - `2026-03-06`
  - `2026-03-10`
  - `2026-03-12`
  - `2026-03-13`
- 至此，本地利通在 `2026-03-02 ~ 2026-04-10` 的 `29` 个交易日都已有可读事件层。
- 核验结果：
  - `29/29` 个交易日 `l2_add_buy_amount / l2_cancel_buy_amount / l2_cvd_delta / l2_oib_delta` 均不再是全空；
  - 日线 `quality_info` 统一提示：`OrderID 部分缺失，L2 数值可能偏小`，说明事件层已落地，但仍需带质量标记解读。
- 新补 8 天的事件层示例（单位：亿元）：
  - `2026-03-02`：`add_buy≈34.52`，`cancel_buy≈20.18`，`cvd≈-0.09`，`oib≈+0.80`
  - `2026-03-03`：`add_buy≈21.43`，`cancel_buy≈8.01`，`cvd≈-2.01`，`oib≈+2.27`
  - `2026-03-10`：`add_buy≈22.37`，`cancel_buy≈7.48`，`cvd≈-0.63`，`oib≈+1.47`
  - `2026-03-12`：`add_buy≈26.20`，`cancel_buy≈10.24`，`cvd≈-0.35`，`oib≈+0.40`

## 6. 当前可直接用于复盘的真实口径

### 高置信区
- `2025-01 ~ 2026-02`
  - 可看：成交级 L1/L2 主力 / 超大单 / 日线 / 5m
  - 不可看：真实挂单事件层
- `2026-03-02 ~ 2026-04-10`
  - 本地利通已补齐真实挂单事件层
  - 可用于利通整段主升浪 / 高位稳住区间复盘

### 中置信区
- `2026-03+` 其他未单票修复日期
  - 价格与主/超大单仍可看
  - 挂单事件层未必真实入库

## 7. 后续动作（冻结）
1. 基于当前 `2026-03-02 ~ 2026-04-10` 全窗口本地事件层，正式进入利通《分阶段深复盘卡》；
2. 把 Windows 跑数机同步到最新 `l2_daily_backfill.py + l2_history_db.py`；
3. 给 Windows 正式库补 schema 升级；
4. 先做单日正式重跑演练（建议 `2026-03-11`）；
5. 成功后再挑“利通型失败票”做对照。

## 8. 风险
- `2026-03+` 原始包虽然有挂单事件，但仍存在真实 `OrderID` 缺口，`quality_info` 不能忽略；
- Windows 正式跑数机代码仍落后于当前仓库，若不升级，后续新跑数仍会继续丢事件层；
- 当前本轮只修了利通关键日，不代表全市场已修。
