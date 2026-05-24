# MOD-20260425-05 realtime and postclose runtime contract

## 背景
2026-04-25 复核后确认：生产实时盯盘、Mac 本地研究站、每日盘后跑数是三条相关但独立的运行链路。此前文档容易把“实时 crawler”和“盘后总控”混在一起。

## 本次收口
1. 明确生产实时链路：浏览器 heartbeat -> Cloud active_symbols -> Windows `ZhangDataLiveCrawler` -> Cloud ingest -> Cloud DB -> 盯盘页。
2. 明确 Mac 本地链路：读取 `/Users/dong/Desktop/AIGC/market-data` 同步库；默认不长期跑后台 crawler；单票可按需 hydrate。
3. 明确每日盘后链路：继续使用 `bash ops/run_postclose_l2.sh`；Windows -> Mac 数据同步只允许 LAN HTTP relay 或 Cloud relay。
4. 修复 Windows 实时 crawler：增加交易日判断，周末/节假日不做 periodic full sweep / final sweep；增加单实例锁，避免计划任务或人工重复启动导致两个 crawler 同时运行。

## 验收口径
- Windows 上 `live_crawler_win.py` 只能保留一个有效 Python 进程。
- 周末/节假日 09:15/15:01 不应出现全量轮扫和收盘 sweep 日志。
- 每日盘后正式指令不变：

```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_postclose_l2.sh
```

## 生产清理记录
- 2026-04-25 已清理 Windows 旧实时 crawler 重复进程，并通过 `sync_to_windows.sh` 重建 `ZhangDataLiveCrawler`。
- 云端确认 `trade_ticks` / `sentiment_snapshots` 均无 2026-04-25 交易日误写，2026-04-24 无重复组。
- 已备份并删除周六误触发写入到 2026-04-24 `sentiment_snapshots` 的 7 条 09:15-09:17 快照；备份位置：Cloud `.run/cleanup/sentiment_snapshots_bad_weekend_20260425_backup.json`。
