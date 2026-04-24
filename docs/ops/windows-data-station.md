# Windows 数据主站

## 1. 作用
Windows 是当前数据主站，负责：
- 原始包保存
- 正式 L2 / 原子层 / 选股研究跑数
- 实时 crawler
- 向 Mac / Cloud 输出处理结果

## 2. 当前关键路径
- 项目目录：`D:\market-live-terminal`
- 实时 crawler 启动：`start_live_crawler.bat`
- crawler 计划任务：`ZhangDataLiveCrawler`
- 日包/跑数相关输出：由盘后总控与 Windows 跑数脚本维护

## 3. 跨机前检查
先执行：
```bash
ping -c 4 100.115.228.56
ssh -o ConnectTimeout=8 laqiyuan@100.115.228.56 "echo ok"
```
任一失败，不要继续跑大文件同步或远控命令。

## 4. 当前正式关注点
1. `ZhangDataLiveCrawler` 的跨重启稳定性
2. 盘后 L2 / atomic 的日跑稳定性
3. 处理后结果向 Mac / Cloud 的同步质量

## 5. 当前相关脚本
- `sync_to_windows.sh`
- `start_live_crawler.bat`
- `ops/win_register_live_crawler_tasks.ps1`
- `check_windows_review_v2_progress.py`（仅排查用途）

## 6. 风险边界
- Windows 是主站，但不是 Git 主开发环境
- Windows 上的长期稳定任务必须优先走 OS 级调度，不继续堆 Python 父进程编排技巧
