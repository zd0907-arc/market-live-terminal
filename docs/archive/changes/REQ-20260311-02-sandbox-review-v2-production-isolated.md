# REQ-20260311-02-sandbox-review-v2-production-isolated

## 1. 基本信息
- 标题：复盘模块 V2（云端可用 + 生产隔离）
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260311-09`
- 关联 CAP：`CAP-SANDBOX-REVIEW`

## 2. 目标
- 将复盘模块升级为常驻功能：可选股、可选时间、点击执行查询。
- 保持生产隔离：仅使用 `/api/sandbox/*` 与 `data/sandbox/review_v2/*`。
- 数据范围固定：`2025-01-01 ~ 2026-02-28`。
- 最新口径（2026-03-12）：放弃实时L2预研路径，V2 底层统一为 5 分钟，不再落 1 分钟持久层。

## 3. 本轮实现
- 新增 V2 数据域：`data/sandbox/review_v2/`（`meta.db` + `symbols/{symbol}.db`）。
- 新增池子构建脚本：`backend/scripts/sandbox_review_v2_pool.py`（50-300亿、沪深A、排除ST、固定池）。
- 新增 5m 回放脚本：`backend/scripts/sandbox_review_v2_backfill.py`（支持 run 记录、月份级状态与失败清单）。
- 新增容量审计脚本：`backend/scripts/sandbox_storage_audit.py`。
- 回放脚本升级：支持自动分片（默认1000只/片）+ `--resume` 续跑 + Windows 内存阈值动态并发（默认 `workers=8/min-workers=6`）。
- API 扩展：
  - `GET /api/sandbox/pool`
  - `GET /api/sandbox/review_data` 增加 `granularity` 参数。
- 前端改造：`/sandbox-review` 顶部支持股票池选股 + 日期范围 + 执行查询。

## 4. 验证记录
- `2026-03-11 20:20`：`python3 -m pytest backend/tests/test_sandbox_review.py backend/tests/test_sandbox_review_v2.py -q` 通过（11/11）。
- `2026-03-11 20:22`：`npm run build` 通过。
- `2026-03-11 21:32`（Windows）：`sandbox_review_v2_pool.py --retries 2 --fallback-workers 6` 成功，股票池固化为 **2788**（50-300亿、沪深A、排除ST）。
- `2026-03-11 21:56`（Windows）：`sandbox_review_v2_backfill.py D:\\MarketData --workers 4 --max-symbols 20 --replace` 成功，`run_id=1`，`total_rows=1,317,759`，`failed_count=0`。
- `2026-03-11 21:57`（Windows）：`sandbox_storage_audit.py` 输出审计，当前 `data/sandbox` 占用约 `231.25MB`（20只样本回放后）。
- `2026-03-11 22:12`（云端）：后端已部署 sandbox 路由，`/api/sandbox/pool` 与 `/api/sandbox/review_data` 均返回 `200`（空态，不再 404）。
- `2026-03-12 12:24`（Windows）：已通过计划任务 `SandboxBackfill5m` 拉起全量5m长任务（参数：`workers=8/min-workers=6/mem=75/symbols-per-shard=1000/resume`）。
- `2026-03-12 13:16`（Windows）：任务仍在运行，日志推进到 `shard=1/3 2025-02-11 sh600113`，`err.log` 为 `0`。
- `2026-03-14 02:30`（Windows）：`sandbox_review_v2_run_all_months.py` 全月份总控完成，覆盖 `2026-02 -> 2025-01` 共 14 个月，`failed_months=[]`。
- `2026-03-14 09:54`（云端）：`data/sandbox/review_v2/` 首轮全量同步完成，`symbols/*.db=2789`，目录占用约 `7.9G`；其中股票池仍固定为 `2788`，额外包含人工补跑样本 `sz000759` 供验数使用。
- `2026-03-14 10:00`（云端）：定位并修复“接口 200 但空数据”问题——根因是云端容器仍在运行旧版 `sandbox_review_v2_db.py`（1m 逻辑）；同步最新 5m 代码并重建前后端容器后，`/api/sandbox/review_data` 对 `sz000833/sz000759` 均可正常返回数据。

## 5. 风险与阻塞
- 行情源偶发断连（`RemoteDisconnected`）仍会影响未来增量补数；当前通过重试与断点续跑缓解。
- 少数日期与第三方终端存在口径差异（如集合竞价是否纳入日高低），当前沙盒以 `D:\\MarketData` 原始逐笔为准。
- 云端容量中 `data/market_data.db.bak` 约 1.6GB（与主库并存）仍需纳入备份保留策略。

## 6. 下一步
1. 维持 V2 sandbox 为“云端可访问、生产隔离”的常驻模块，等待后续与生产盯盘改造一起进入正式发布窗口。
2. 若后续补充更多验数标的，可沿用 `symbols/{symbol}.db` 独立补跑并增量同步，不必重刷全池。
3. 对 `market_data.db.bak` 执行“保留策略 + 压缩或迁移”，并形成审计记录。
