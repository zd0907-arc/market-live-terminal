# Windows 数据主站

## 1. 作用
Windows 是当前数据主站，负责：
- 原始包保存
- 正式 L2 / 盘后明细底座 / 选股研究 / 模型特征 跑数
- 实时 crawler
- 向 Mac / NAS 在线节点输出处理结果

## 2. 当前关键路径
- 项目目录：`D:\market-live-terminal`
- 实时 crawler 启动：`start_live_crawler.bat`
- crawler 主脚本：`backend\scripts\live_crawler_win.py`
- crawler 计划任务：`ZhangDataLiveCrawler`
- 日包/跑数相关输出：正式主链由 `ops/run_daily_new_framework.sh` 维护；`ops/run_postclose_l2.sh` 只按旧 L2 / cloud 同步兼容链路理解，不再当默认日常入口

## 2.1 实时 crawler 正式语义
- Windows 是唯一生产实时外采节点。
- crawler 当前从线上后端拉 `/api/watchlist` 和 `/api/monitor/active_symbols`；默认应理解为 NAS 在线节点。
- crawler 当前向线上后端写 `/api/internal/ingest/ticks` 与 `/api/internal/ingest/snapshots`；NAS crawler 虽已跑通，但 Windows 仍是当前正式基线。
- crawler 必须使用交易日历判断；周末/节假日不得做 periodic full sweep / final sweep。
- crawler 内置单实例锁，计划任务重复触发时新实例应直接退出。

## 3. 跨机前检查
先执行：
```bash
ping -c 4 100.115.228.56
ssh -o ConnectTimeout=8 laqiyuan@100.115.228.56 "echo ok"
```
任一失败，不要继续跑大文件同步或远控命令。

## 4. 当前正式关注点
1. `ZhangDataLiveCrawler` 只能有一个有效 Python 进程。排障时不要只看 schtasks Running，必须同时看进程和日志。
2. 盘后 L2 / atomic 的日跑稳定性。
3. `atomic_compact_main`、`selection_research_main`、`model_feature_store_main` 三条正式主链向 Mac 的同步质量。
4. 实时 crawler 与每日盘后总控是两条不同链路，不能混用排障结论。

## 5. 当前相关脚本
- `sync_to_windows.sh`
- `start_live_crawler.bat`
- `ops/win_register_live_crawler_tasks.ps1`
- `ops/run_daily_new_framework.sh`
- `ops/check_windows_new_framework_months_status.sh`
- `ops/run_postclose_l2.sh`（仅旧 L2 / cloud 同步兼容排查）
- `check_windows_review_v2_progress.py`（仅排查用途）

## 6. 风险边界
- Windows 是主站，但不是 Git 主开发环境
- Windows 上的长期稳定任务必须优先走 OS 级调度，不继续堆 Python 父进程编排技巧
