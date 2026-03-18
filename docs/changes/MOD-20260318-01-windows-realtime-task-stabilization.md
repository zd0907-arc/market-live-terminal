# MOD-20260318-01-windows-realtime-task-stabilization

## 1. 基本信息
- 标题：Windows 实时采集计划任务稳态化与单实例收口
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260318-01`
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-WIN-PIPELINE`
- 关联 STG：无

## 2. 背景与目标
- `2026-03-18` 用户反馈生产“当天实时数据没进来”，按既往经验高度怀疑 Windows 节点未正常跑数。
- 已先完成 `v4.2.20` 的紧急兜底：避免云端接口直接空白；但 Windows 侧仍存在“旧计划任务脆弱、watchdog 误判、多实例堆积”的根因。
- 目标：把 `ZhangDataLiveCrawler` 改造成正式、可自恢复、默认单实例的计划任务入口，并沉淀后续 AI 修 bug / 做需求 / 改版时的标准分支与验证流程。

## 3. 方案与边界
- 做什么：
  - `start_live_crawler.bat` 收口为唯一正式启动入口；
  - `win_register_live_crawler_tasks.ps1` 改为 XML 注册单任务：`Boot + Every 5 Minutes + IgnoreNew + SYSTEM`；
  - 同步时删除旧 watchdog 任务并清理历史重复 crawler 进程；
  - 回填 Windows 巡检 SOP、标准开分支模板、AI 快速入口；
  - 版本提升到 `4.2.21`。
- 不做什么：
  - 不改业务接口语义；
  - 不调整数据库 schema；
  - 不把“已跨 5 分钟周期单实例稳定”夸大成“已完成重启/注销全场景验证”。

## 4. 执行步骤（按顺序）
1. 本地审查 Windows 相关脚本差异，确认问题集中在计划任务模式与旧 watchdog 误判。
2. 远程同步脚本到 Windows，定位 XML 注册失败原因为 `schtasks` 引号与 `LogonType` 配置不兼容。
3. 修正注册脚本为“直接调用 `schtasks.exe` + 检查退出码 + 清理旧 crawler 进程”。
4. 再次同步到 Windows，成功重建 `ZhangDataLiveCrawler` 正式任务，并触发一次立即恢复。
5. 跨过下一个 5 分钟触发周期复检，确认 Python 进程从历史 `11` 份收敛为 `1` 份且未再次膨胀。
6. 校验生产接口与云端数据库当天数据已恢复，并把 Runbook / handoff / AI 快入口一起回填。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-18 12:47:29` Windows 重新注册正式任务；
- When 等待到 `2026-03-18 12:52` 后再次检查 Windows；
- Then `tasklist` 中仅保留 `1` 个 `python.exe` crawler 进程，未重新长出重复实例。

- Given `2026-03-18 12:54` 后检查生产接口；
- When 请求 `/api/realtime/dashboard?symbol=sz000833`；
- Then 返回 `code=200`，`chart_data` 为当日真实数据而非空数组。

- Given `2026-03-18 12:55` 后检查云端数据库；
- When 查询 `trade_ticks` 与 `sentiment_snapshots`；
- Then `2026-03-18` 当天存在真实记录，样本 symbol 至少包含 `sz000833` / `sh600556` 等盯盘股票。

## 6. 风险与回滚
- 风险：
  - 当前已验证“非交互 SYSTEM 场景 + 5 分钟重复触发 + 单实例忽略”稳定，但尚未补做“Windows 重启/注销后自动恢复”的正式演练。
  - `live_crawler_runtime.log` 以追加方式记录初始化事件，后续若需要更强验真，可继续补充 heartbeat/轮询成功日志。
- 回滚：
  1. 代码回滚到 `snapshot-20260318-pre-governance` 或对应 archive branch；
  2. Windows 重新同步旧版 `start_live_crawler.bat` / `live_crawler_win.py` / 任务注册脚本；
  3. 若本轮任务模式失效，先手动 `schtasks /Run /TN ZhangDataLiveCrawler` 应急，再按旧备份恢复。

## 7. 结果回填
- 实际改动：
  - `backend/scripts/live_crawler_win.py`：补 runtime log / pid 文件写入与 AkShare 单股超时保护；
  - `start_live_crawler.bat`：改为正式唯一启动入口，统一从 Machine env 读取参数并写 `.run/live_crawler.log`；
  - `ops/win_register_live_crawler_tasks.ps1`：改为 XML 注册单任务，带退出码校验与重复进程清理；
  - `sync_to_windows.sh`：同步并重建 Windows 正式任务；
  - `docs/04_OPS_AND_DEV.md` / `docs/07_PENDING_TODO.md` / `docs/AI_HANDOFF_LOG.md` / `docs/AI_QUICK_START.md`：同步治理结果。
- 验证结果：
  - `2026-03-18 12:45` 前 Windows 上存在 `11` 个重复 `python.exe`；
  - `2026-03-18 12:47` 修复后收敛为 `1` 个；
  - `2026-03-18 12:53` 跨 5 分钟周期复检仍保持 `1` 个；
  - `2026-03-18 12:54` 生产 `/api/health` 正常；
  - `2026-03-18 12:54` 生产 `/api/realtime/dashboard?symbol=sz000833` 返回当天真实 `chart_data`；
  - `2026-03-18 12:55` 云端 `trade_ticks/sentiment_snapshots` 均查到 `2026-03-18` 数据。
- 遗留问题：
  - 仍需补一次“重启或注销后自动恢复”的正式演练，完成后可关闭 `T-016`。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
