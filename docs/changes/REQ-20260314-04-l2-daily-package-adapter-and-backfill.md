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
    - `2026-03-11 / 600519.SH`：成功落库 `48` 条 `history_5m_l2` + `1` 条 `history_daily_l2`。
- 遗留问题：
  1. 还未实现“自动扫描整个月目录并批量发现待回补交易日”；
  2. 还未把 Windows 现有裸日目录自动迁入月目录，只是 ETL 已兼容新旧结构输入；
  3. 上证样本存在“部分母单号无法在委托文件完全对齐”的现实情况，当前已改为兼容性回补策略，但仍需继续观察是否要针对上交所样本细化规则。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
