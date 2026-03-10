# INV-20260310-01-prod-intraday-no-data

## 1. 基本信息
- 标题：生产环境当日分时无数据（实时状态可见但曲线为空）
- 状态：RELEASED_PENDING_SMOKE
- 负责人：后端 AI
- 关联 Task ID：CHG-20260310-01
- 关联 CAP：CAP-REALTIME-FLOW, CAP-WIN-PIPELINE
- 关联 STG：独立紧急修复

## 2. 背景与目标
- 现象：生产环境可展示交易中的状态，但 `/api/realtime/dashboard` 返回的当日分时数据为空。
- 目标：恢复 Windows -> Cloud ingest 链路，使 `trade_ticks` 在交易时段持续增长并可被前端实时展示。

## 3. 方案与边界
- 做什么：定位断链根因、修复 Windows 依赖与环境配置、加固启动脚本并完成发布。
- 不做什么：不改资金阈值口径，不改前端图表渲染逻辑，不调整历史 30m 规则。

## 4. 执行步骤（按顺序）
1. 生产排查：核对容器版本、ingest 日志、`trade_ticks` 最新交易日与行数。
2. Windows 排查：核对 `INGEST_TOKEN/CLOUD_API_URL`、采集进程、依赖安装与自启动状态。
3. 修复与验证：修正地址与脚本防护，恢复采集并验证生产 API 返回非空。
4. 发布：完成版本同步、云端部署、冒烟核验、归档变更卡。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-10 13:42 (Asia/Shanghai)` Windows 采集已恢复，When 查询生产 `trade_ticks`，Then `MAX(date)=2026-03-10` 且 `MAX(time)`随时间推进。
- Given 同一时刻，When 请求 `/api/realtime/dashboard?symbol=sz000833`，Then `chart_data` 非空且 `latest_ticks` 至少 1 条。
- Given 发布完成后，When 查看后端日志，Then `POST /api/internal/ingest/ticks` 持续返回 `200`。

## 6. 风险与回滚
- 风险：Windows 登录态任务中断或环境变量被污染会导致 ingest 再次停摆。
- 回滚：回滚到上一版本 Tag，并按 `04_OPS_AND_DEV` 使用手动探测脚本恢复一次全量回填。

## 7. 结果回填
- 实际改动：
  - 修复 Windows 侧采集依赖缺失：安装 `akshare`。
  - 修复 ingest 目标地址：`CLOUD_API_URL` 改为 `http://111.229.144.202`（不再使用 `:8000`）。
  - 加固脚本：`live_crawler_win.py` 对 `CLOUD_API_URL` 增加 `.strip().rstrip('/')` 防尾随空格污染。
  - 加固启动：更新 `start_live_crawler.bat` 默认地址与提示；创建登录触发任务 `ZhangDataLiveCrawler`。
  - 发布版本：`v4.2.10`（`package.json` / `src/version.ts` / `README.md` 已同步）。
- 验证结果：
  - 发布前后核验到生产 `trade_ticks` 已恢复当日写入：`MAX(date)=2026-03-10`。
  - 线上接口抽查：`/api/realtime/dashboard?symbol=sz000833` 返回非空分时与最新 ticks。
  - 生产冒烟四项（health/write token/ingest token）按流程由用户手动执行，当前待回填。
- 遗留问题：
  - 需等待用户完成生产冒烟并回填结果；若任一失败，按 `04_OPS_AND_DEV` 回滚流程处理。

## 8. 归档信息
- 归档时间：待定（待用户冒烟通过后归档）
- Archive ID：待定
- 归档路径：待定
