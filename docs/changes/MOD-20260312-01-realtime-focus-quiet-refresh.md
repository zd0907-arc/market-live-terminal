# MOD-20260312-01-realtime-focus-quiet-refresh

## 1. 基本信息
- 标题：生产实时页盯盘二态化与静默刷新加固
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260312-02`
- 关联 CAP：`CAP-REALTIME-FLOW`

## 2. 背景与目标
- 当前生产“盯盘/观望/标准”三态与真实频率语义不一致：标准 5s、盯盘 15s、观望 60s，用户感知与实际行为相反。
- 前端实时页在周期刷新时需要保持旧数据可见，避免“整块先消失、稍后再重新出现”的跳闪体验。
- Windows 实时爬虫需要配合心跳模式分层：只对当前正在看的股票提速，不把其他自选股或最近浏览股票拉入高频 tick 队列。

## 3. 方案与边界
- 做什么：
  - 前端把三态收敛为二态：`盯盘开=5s`、`盯盘关=30s`。
  - 实时页轮询改为静默刷新：周期刷新失败时保留上一版成功数据，仅展示轻量状态提示。
  - `heartbeat` 增加 `mode=focus|warm`，云端返回 `focus_symbols/warm_symbols/all_symbols` 分层快照。
  - Windows 爬虫分层抓取：`focus` tick 5s、`warm` tick 30s、watchlist 继续 15 分钟保底轮扫。
- 不做什么：
  - 不引入“最近查看股票”中频队列。
  - 不改 sandbox 回放链路，不打断当前 `SandboxBackfill5m` 长跑任务。
  - 不在本轮直接发布生产，仅完成代码与文档收口。

## 4. 执行步骤（按顺序）
1. 前端改造 `App.tsx` 与 `RealtimeView.tsx`：切换为盯盘二态，并保持周期刷新时旧数据常驻。
2. 扩展 `/api/monitor/heartbeat` 与 `/api/monitor/active_symbols` 契约，新增 `focus/warm` 分层。
3. 调整 `live_crawler_win.py`：focus/warm 双层 tick 节奏与快照节奏分开。
4. 回填 `02/03/07/AI_HANDOFF_LOG`，并补自动化测试。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-12 18:30`，When 打开实时页并关闭盯盘，Then 前端报价与实时图按 30 秒静默刷新，界面不应先清空再回显。
- Given `2026-03-12 18:35`，When 打开盯盘开关，Then 前端报价与实时图轮询切换为 5 秒，按钮文案明确显示“盯盘中 5s”。
- Given `2026-03-12 18:40`，When 前端发送 `POST /api/monitor/heartbeat?symbol=sh600519&mode=focus`，Then `/api/monitor/active_symbols` 返回的 `data.focus_symbols` 包含该标的，且 `warm_symbols` 不重复收录。
- Given `2026-03-12 18:45`，When Windows 爬虫读取活跃快照，Then 仅对 `focus_symbols` 使用 5 秒 tick 节奏，对 `warm_symbols` 使用 30 秒 tick 节奏，watchlist 仍保留 15 分钟兜底轮扫。

## 6. 风险与回滚
- 风险：
  - 若云端后端先于 Windows 爬虫发布，老版 crawler 需依赖兼容解析；本轮已在爬虫端兼容“旧 list / 新 dict”两种响应。
  - 5 秒 tick 高频本质仍是“整日覆盖写”，若同时有大量 focus 用户，会增加 Windows 侧 AkShare 压力。
- 回滚：
  1. 前端回退到旧版三态按钮；
  2. 后端 `active_symbols` 保持 flat list 结构；
  3. Windows 爬虫恢复单层 `ACTIVE_TICK_INTERVAL_SECONDS=20`。

## 7. 结果回填
- 实际改动：
  - `src/App.tsx`：三态按钮改为二态“盯盘开关”，刷新节奏改为 5s/30s。
  - `src/components/dashboard/RealtimeView.tsx`：心跳带 `mode`，历史日期不再注册活跃心跳，周期刷新保留旧数据并引入请求序号防串写。
  - `backend/app/services/monitor.py`、`backend/app/routers/monitor.py`：活跃心跳升级为 `focus/warm` 分层。
  - `backend/scripts/live_crawler_win.py`：focus/warm 分层抓取，且兼容旧版 active_symbols list 响应。
  - `backend/tests/test_monitor_heartbeat.py`：新增 monitor 分层测试。
- 验证结果：
  - `2026-03-12 18:26`：`python3 -m pytest backend/tests/test_monitor_heartbeat.py backend/tests/test_sandbox_review.py backend/tests/test_sandbox_review_v2.py -q` 通过（13/13）。
  - `2026-03-12 18:27`：`npm run build` 通过。
- 遗留问题：
  - 当前按你的要求暂不单独发布，需等待复盘模块数据与联调完成后与 sandbox 相关改动一并发布。
  - Windows 线上 crawler 参数切换需与云端前后端同批次部署。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
