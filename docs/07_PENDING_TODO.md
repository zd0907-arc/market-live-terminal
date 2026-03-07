# 07_PENDING_TODO（人工待办与阻塞项）

## T-001 Windows 节点离线待恢复（高优先级）
- 状态：`BLOCKED`（用户当前无法操作 Windows 机器）
- 现象：`100.115.228.56` 在 Tailscale 离线（last seen 6d ago），`sync_to_windows.sh` 超时。
- 影响：Windows 侧脚本暂未同步到最新版本；尽管云端已加 date 纠偏兜底，但建议尽快同步以彻底闭环。
- 人工恢复后执行：
  1. `cd /Users/dong/Desktop/AIGC/market-live-terminal`
  2. `./sync_to_windows.sh`
- 验收标准：
  - 脚本传输成功，无 `Operation timed out`
  - Windows 上 `backend/scripts/live_crawler_win.py` 为最新版本
  - 次日不再出现非交易日（如周六）写入 `trade_ticks` 的新记录

## 协作约定（后端 AI -> 用户）
- 只要后续任务涉及以下任一动作，必须先提醒用户确认 Windows 同步状态：
  - 修改 `backend/scripts/live_crawler_win.py`
  - 修改 `start_live_crawler.bat`
  - 修改 Windows 采集调度或 ingest 上报逻辑
