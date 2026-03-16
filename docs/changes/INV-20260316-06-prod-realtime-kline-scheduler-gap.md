# INV-20260316-06-prod-realtime-kline-scheduler-gap

## 1. 基本信息
- 标题：生产实时 K 线缺失（Windows 实时采集任务未自动拉起）
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260316-06`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 关联 STG：独立线上故障排查

## 2. 背景与目标
- 现象：`2026-03-16` 盘中生产盯盘页无实时 K 线，用户在生产环境查看粤桂股份等标的时只能看到空白实时区。
- 目标：快速确认问题位于“Windows 实时采集链路”而不是前端展示或云端聚合逻辑，恢复当日实时数据写入，并把后续稳态化工作纳入待办。

## 3. 方案与边界
- 做什么：
  - 核对生产 `/api/realtime/dashboard` 与 `trade_ticks` 是否停更；
  - 排查 Windows 计划任务 `ZhangDataLiveCrawler` 的触发方式、最近运行时间与退出状态；
  - 手动拉起任务，验证生产接口恢复；
  - 文档化根因与后续稳态化待办。
- 不做什么：
  - 本卡不改前端实时图表；
  - 本卡不重构 Windows 长驻控制器，只做恢复与治理登记。

## 4. 执行步骤（按顺序）
1. 确认生产实时接口无当日有效数据，排除前端单点渲染问题。
2. 登录 Windows，检查 `ZhangDataLiveCrawler` 的计划任务配置、上次运行时间与结果码。
3. 手动执行 `schtasks /Run /TN ZhangDataLiveCrawler` 恢复实时采集。
4. 验证新 Python 进程已拉起，且生产 `/api/realtime/dashboard` 恢复返回当日数据。
5. 回填 `04/07/AI_HANDOFF_LOG`，把“计划任务稳态化”转为显式待办。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-16 09:30 (Asia/Shanghai)` 生产盯盘页实时区为空，When 排查生产接口与 Windows 采集任务，Then 可明确定位为“Windows 实时采集未运行”而非前端问题。
- Given `2026-03-16 09:36 (Asia/Shanghai)` 手动执行 `schtasks /Run /TN ZhangDataLiveCrawler`，When 再次请求 `/api/realtime/dashboard?symbol=sz000833`，Then 返回包含当日实时图数据与最新 ticks。
- Given 同一时刻，When 检查 Windows 进程，Then 可看到 `python backend\\scripts\\live_crawler_win.py` 正在运行。

## 6. 风险与回滚
- 风险：
  - 当前计划任务仍是“登录触发 + 交互式运行”，周末后、重启后、注销后都可能再次出现盘中未自动拉起。
  - 结果码 `-1073741510` 说明这条任务本身仍存在不稳定性，不能把本次手动恢复视为永久修复。
- 回滚：
  - 若新版采集脚本有问题，可回退到上一个已知可运行的 Windows 启动脚本版本；
  - 但无论是否回滚，盘中恢复都可先通过 `schtasks /Run /TN ZhangDataLiveCrawler` 执行临时拉起。

## 7. 结果回填
- 实际改动：
  - 本轮未改业务代码，完成的是线上故障定位、手动恢复与文档治理。
- 验证结果：
  - Windows 任务 `ZhangDataLiveCrawler` 的上次运行时间停在 `2026-03-14 14:05:32`；
  - 任务上次结果为 `-1073741510`，且触发方式仍为“登录时 / 仅交互方式”；
  - 手动执行 `schtasks /Run /TN ZhangDataLiveCrawler` 后，Windows 新 Python 进程已恢复；
  - 生产 `/api/realtime/dashboard?symbol=sz000833` 已恢复返回 `2026-03-16` 盘中实时数据。
- 遗留问题：
  - 已转入 `docs/07_PENDING_TODO.md::T-016`：需要把 Windows 实时采集计划任务改造成可跨重启/注销稳定运行的正式方案；
  - 在该任务完成前，盘中若再出现实时 K 线空白，优先排查计划任务状态而不是先改前端。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
