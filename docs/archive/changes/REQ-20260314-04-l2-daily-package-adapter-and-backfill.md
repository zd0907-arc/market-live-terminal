# REQ-20260314-04-l2-daily-package-adapter-and-backfill

## 1. 基本信息
- 标题：Phase 2｜Windows 盘后 L2 日包适配与强回补机制
- 状态：DONE
- 负责人：Codex / 后端 AI
- 关联 Task ID：`CHG-20260314-04`
- 关联 CAP：`CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 关联 STG：`STG-20260314-01`

## 2. 背景与目标
- 当前新日包已经验证可做 L2 母单聚合，但格式与旧 ETL 不兼容。
- 本阶段目标是把“中文列名新日包 → 标准 5m/day 的 L1/L2 双派生 → 可重跑的日级回补”这条链路定义清楚。

## 3. 方案与边界
- 做什么：
  - 适配 `行情.csv / 逐笔成交.csv / 逐笔委托.csv`；
  - 从同一日包同时生成 L1 与 L2 的 `5m + daily` 派生结果；
  - 建立按日覆盖重跑与失败重试机制；
  - 支持你后续补下载 3 月任意日期与未来每日增量。
- 不做什么：
  - 不把原始 `逐笔成交/逐笔委托` 上云；
  - 不在本阶段切换页面查询。

## 4. 执行步骤
1. 增加目录扫描规则，优先识别 `YYYYMM/YYYYMMDD/{symbol}`。
2. 建立中文列名到内部标准字段的映射。
3. 建立按单笔阈值的 L1 派生和按母单聚合的 L2 派生。
4. 生成 `history_5m_l2` 与 `history_daily_l2` 所需记录。
5. 写入前执行“按 `symbol + trade_date` 整日删后重写”。
6. 记录本次回补状态、失败清单、重试信息。

## 5. 验收标准（Given/When/Then）
- Given `2026-03-14 18:20`，When 读取 `202603/20260311/000833.SZ`，Then 可同时产出该日 L1/L2 的 5m 与日线结果。
- Given `2026-03-14 18:25`，When 同一天执行两次回补，Then 结果应覆盖更新而不是重复追加。
- Given `2026-03-14 18:30`，When 某个 symbol 文件异常，Then 整体任务状态可见且失败清单可追溯到具体文件。

## 6. 风险与回滚
- 风险：中文列名、价格单位、OrderID 映射若定义不严，会造成 L1/L2 双口径同时污染。
- 回滚：回补表采用整日覆盖语义，失败日可单独重跑，不依赖全量回滚。

## 7. 结果回填
- 实际改动：
  - 新增正式回补脚本：`backend/scripts/l2_daily_backfill.py`
  - 复用/接入 Phase 1 的正式 schema 与目录 helper
  - 新增测试：`backend/tests/test_l2_daily_backfill.py`
- 验证结果：
  - 已支持从 `YYYYMM/YYYYMMDD/{symbol}` 目录读取中文列名日包，并生成 L1/L2 的 `5m + daily` 双派生；
  - 已支持写入 `history_5m_l2 / history_daily_l2 / l2_daily_ingest_runs / l2_daily_ingest_failures`；
  - 已验证失败 symbol 会记录到 failure 表，整日回补支持覆盖写；
  - 自动化：Phase 2 相关测试已补到“部分母单号缺失时允许成交侧回退聚合”的兼容场景；
  - 手动冒烟：
    - `2026-03-11 / 000833.SZ`：成功落库 `49` 条 `history_5m_l2` + `1` 条 `history_daily_l2`；
    - `2026-03-11 / 600519.SH`：成功落库 `48` 条 `history_5m_l2` + `1` 条 `history_daily_l2`；
  - 批量回补进展（`2026-03-15`）：
    - Windows `D:\\MarketData\\202603` 已确认 `20260302 ~ 20260313` 共 10 个交易日日包下载完成；
    - `2026-03-02 ~ 2026-03-13` 当前已下载的全部 10 个交易日，均已通过“Mac 直连多 SSH 会话 + 8 worker shard”路径完成正式回补；
    - 各日正式结果：
      - `2026-03-02`：`history_daily_l2=7731`、`history_5m_l2=347672`
      - `2026-03-03`：`history_daily_l2=7714`、`history_5m_l2=351291`
      - `2026-03-04`：`history_daily_l2=7724`、`history_5m_l2=347869`
      - `2026-03-05`：`history_daily_l2=7672`、`history_5m_l2=346077`
      - `2026-03-06`：`history_daily_l2=7644`、`history_5m_l2=343385`
      - `2026-03-09`：`history_daily_l2=5893`、`history_5m_l2=260777`
      - `2026-03-10`：`history_daily_l2=7348`、`history_5m_l2=331198`
      - `2026-03-11`：`history_daily_l2=7648`、`history_5m_l2=344439`
      - `2026-03-12`：`history_daily_l2=7630`、`history_5m_l2=344317`
      - `2026-03-13`：`history_daily_l2=7610`、`history_5m_l2=343162`
    - 当前这 10 个交易日的缺口已收敛为两类：
      1. 明确 `OrderID` 对齐失败：共 `43` 个 `symbol-day`
      2. 其余未入正式表样本：共 `105` 个 `symbol-day`，主要是当日无有效 bar / 无法形成正式 `5m+daily`
    - staging 目录已在每个交易日处理后清理，Windows `Z:\\l2_stage` 当前已回到空目录，可继续支持后续 3 月增量日包。
    - `2026-03-15` 修复进展：
      - 已放宽为“单边 0 overlap 允许回退到成交侧 parent total、双边 0 overlap 才继续失败”；
      - 已通过 `repair_20260302 ~ repair_20260313` 共 `10` 个定向 repair run，把原 `43` 个显式 `OrderID` 失败样本全部补回正式表；
      - 当前主要剩余缺口收敛为 `105` 个空结果样本，需后续继续 review。
- 遗留问题：
  1. 还未实现“自动扫描整个月目录并批量发现待回补交易日”；
  2. 还未把 Windows 现有裸日目录自动迁入月目录，只是 ETL 已兼容新旧结构输入；
  3. `Windows 本机父进程 -> 子进程` 的分片并发编排仍不稳定；当前已确认可行路径是“Mac/本地直接开多条 SSH 会话并发跑 shard”，后续需把这条稳定方案脚本化；
  4. 原 `43` 个 `symbol-day` 的显式 `OrderID` 对齐失败已在 `2026-03-15` repair run 中全部补回；但“单边 0 overlap”是现实数据形态，后续仍需持续写入 `quality_info` 并观察是否要按市场/品种细化容错规则；
  5. 当前主要剩余缺口是 `105` 个“无有效 bar / 未形成正式 5m+daily”的空结果样本；后续 run 已要求把这类样本同步记入 `l2_daily_ingest_failures`，避免静默缺口；
  6. Windows 端未来若要独立完成每日盘后正式回补，应切换到 **Task Scheduler / PowerShell / cmd 的 OS 级控制器 + 8 个独立 worker + DB 轮询验真**，而不是继续沿用当前父进程 `Popen` 版 `l2_day_sharded_backfill.py`。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
