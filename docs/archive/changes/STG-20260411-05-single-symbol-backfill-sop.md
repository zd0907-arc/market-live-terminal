# STG-20260411-05 单票补数 SOP（Windows raw -> 本地落库）

> **历史过程卡。**
> 当前项目主线 / 当前目录 / 当前版本 / 当前分支纪律，请优先看：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
> 当前数据治理主题真实状态，请优先看：`docs/changes/MOD-20260411-14-market-data-governance-current-state.md`


## 1. 基本信息
- 标题：单票补数 SOP（Windows raw -> 本地落库）
- 状态：ACTIVE
- 负责人：Codex
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联 Task ID：`CHG-20260411-05`

## 2. 适用场景
这份 SOP 用于：
- 你发现某只票页面缺数据；
- 想先补单票，不想先动全市场；
- 想验证 raw、脚本、落库、页面是否打通。

当前这份 SOP 已由利通 `sh603629` 验证过。

---

## 3. 总原则
单票补数不是长期正式路径，但非常适合：
- 问题定位；
- 样本修复；
- 案例复盘；
- 全市场重跑前演练。

原则：
1. 只拉单票，不拉整月；
2. 只解压当天，不堆 staging；
3. 先写本地，再验收；
4. 不直接修改旧模块读口径。

---

## 4. 输入与前提

### 4.1 需要的条件
- Tailscale 可达
- SSH 可连 Windows 跑数机
- Windows 原始包存在于：
  - `D:\MarketData\YYYYMM\YYYYMMDD.7z`

### 4.2 当前冻结的单票临时路径
- Windows 临时解压：
  - `D:\tmp_l2_audit\YYYYMMDD`
- 本地临时目录：
  - `/tmp/lt_l2/YYYYMMDD/603629.SH`

### 4.3 目标数据库
- 本地主库：
  - `/Users/dong/Desktop/AIGC/market-live-terminal/data/market_data.db`

---

## 5. 标准流程

## Step 1：确认这天 raw 是否存在
先确认：
- `D:\MarketData\YYYYMM\YYYYMMDD.7z` 是否存在；
- 目标 symbol 在包里是否存在。

---

## Step 2：只解压目标票
在 Windows 上：
- 删除旧的 `D:\tmp_l2_audit\YYYYMMDD`
- 用 `7za` 只解压该 symbol 所在目录

目标是：
- 避免整包长期展开；
- 控制磁盘占用；
- 减少传输体积。

---

## Step 3：拉三类文件回本地
只拉：
- `行情.csv`
- `逐笔成交.csv`
- `逐笔委托.csv`

不要拉整个目录树。

---

## Step 4：本地执行回填
运行：
- `backend/scripts/l2_daily_backfill.py`

输入目录就是：
- `/tmp/lt_l2/YYYYMMDD`

并指定：
- `--symbols sh603629`
- `--db-path data/market_data.db`

---

## Step 5：SQL 验证
至少验证两层：

### 日线层
检查：
- `history_daily_l2`
- 是否有：
  - close
  - `l2_main_net`
  - `l2_super_net`
  - `quality_info`

### 5m 事件层
检查：
- `history_5m_l2`
- 是否有：
  - `l2_add_buy_amount`
  - `l2_cancel_buy_amount`
  - `l2_cvd_delta`
  - `l2_oib_delta`

---

## 6. 推荐命令模式

## 6.1 单天单票模式
推荐使用稳定的 shell 直跑模式，不优先依赖半成品 helper。

核心模式：
1. Windows `ssh` 解压单票
2. `scp` 拉三文件
3. 本地 `python3 backend/scripts/l2_daily_backfill.py ...`
4. `sqlite3` 验证

这是当前最稳的方式。

---

## 6.2 不推荐直接依赖的东西
当前不建议把：
- `backend/scripts/backfill_local_symbol_from_windows_raw.py`

当成正式唯一入口。

原因：
- 这个 helper 仍踩过路径层级坑；
- 适合后续继续修稳；
- 但当前最稳的还是 shell 直跑模式。

---

## 7. 验收标准

## 7.1 基础通过
- `history_daily_l2` 有该日记录；
- `history_5m_l2` 有该日记录；
- 不报解析失败。

## 7.2 事件层通过
- 这天若属于 `2026-03+`：
  - `l2_add_* / l2_cancel_* / l2_cvd_delta / l2_oib_delta`
  - 不再全空

## 7.3 质量标签通过
- 如果 raw 本身有 `OrderID` 缺口：
  - 允许 `quality_info` 提示偏小；
  - 不因此判定补数失败。

---

## 8. 利通样板结论
利通 `sh603629` 已按这条 SOP 完成：

- 老数据窗口：`2026-02-02 ~ 2026-02-27`
- 新数据窗口：`2026-03-02 ~ 2026-04-10`
- 合计：`44` 个交易日

结果：
- 连续竞价 trade 原子层已完整落库：
  - `atomic_trade_daily=44`
  - `atomic_trade_5m=2148`
- 新数据段 order 原子层已完整落库：
  - `atomic_order_daily=29`
  - `atomic_order_5m=1416`
- 新数据段集合竞价摘要层已完整落库：
  - `atomic_open_auction_l1_daily=29`
  - `atomic_open_auction_l2_daily=29`
  - `atomic_open_auction_manifest=29`
- 已证明：
  1. 老 zip 可按单票定向抽 `603629.csv`
  2. 新 7z 可按单票定向抽 `YYYYMMDD\\603629.SH\\*`
  3. 不需要整包长期展开
  4. 不需要依赖旧正式主库已有底表，也能直接从 raw 生成新库原子层

### 8.1 这次单票实际获取过程（利通样板）
1. 在 Windows 检查 raw 包是否存在
   - 老数据：`D:\\MarketData\\202602\\2026-02-xx.zip`
   - 新数据：`D:\\MarketData\\202603\\202603xx.7z` / `D:\\MarketData\\202604\\202604xx.7z`
2. 用 `7z` **按单票定向解压**
   - 老数据只抽：`603629.csv`
   - 新数据只抽：`YYYYMMDD\\603629.SH\\行情.csv / 逐笔成交.csv / 逐笔委托.csv`
3. 写入独立验证库，而不是改旧库
   - `D:\\market-live-terminal\\data\\atomic_facts\\litong_validation.db`
4. 老数据段直接从成交 raw 构建：
   - `atomic_trade_5m`
   - `atomic_trade_daily`
5. 新数据段直接从成交 + 委托 raw 构建：
   - `atomic_trade_5m / daily`
   - `atomic_order_5m / daily`
   - `atomic_open_auction_l1_daily / atomic_open_auction_l2_daily`
6. 最后再做 SQL 覆盖校验，确认日期范围与行数正确

### 8.2 这次样板票的意义
这次单票不是为了“只修利通”，而是为了验证三件事：
1. **表设计是不是能落**
2. **Windows raw 结构是不是支持我们按股票精确抽取**
3. **不用大规模全量回补，能不能先证明新治理方案是通的**

现在这三件事都已经被利通样板票验证通过。

---

## 9. 什么时候用单票 SOP，什么时候不用

## 9.1 适合用单票 SOP
- 页面只缺某一只票；
- 想先做案例复盘；
- 想做链路验证；
- 想先证明 raw 没问题。

## 9.2 不适合继续只靠单票 SOP
- 需要全市场研究；
- 需要正式长期可用；
- 需要修最近整段 `2026-03+`。

这时就该切到：
- Windows 正式链路升级
- 单日演练
- 再批量重跑

---

## 10. 后续改进建议
1. 把 helper 脚本修稳；
2. 把“解压 -> 回传 -> 落库 -> 验证”做成半自动；
3. 但仍坚持：
   - 单票模式用于样本；
   - 正式链路用于全市场。

---

## 11. 当前短结论
- 单票补数这条路已经被利通验证可行；
- 它适合做：
  - 问题定位
  - 样本修复
  - 案例复盘前置
- 但它不是全市场长期正式方案，正式方案仍是 Windows 整体链路升级。
