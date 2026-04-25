# 实时盯盘与交易时段能力

## 覆盖 CAP
- `CAP-MKT-TIME`
- `CAP-REALTIME-FLOW`

## 当前正式结论
1. 当日分时页正式主路径是 `/api/realtime/intraday_fusion`。
2. 交易日状态机已经收口到明确的盘前 / 盘中 / 午间 / 盘后 / 休盘语义。
3. Cloud 盯盘是轻量线上能力：云端只被动接收 Windows ingest，不主动外采。
4. Mac 本地盯盘默认读取本机同步库；单票接口允许按需补拉当日 ticks，但不默认启动生产级后台 crawler。

## 生产实时链路
```text
浏览器盯盘页
  -> /api/monitor/heartbeat
  -> Cloud active_symbols
  -> Windows ZhangDataLiveCrawler
  -> 腾讯行情 / AkShare
  -> /api/internal/ingest/snapshots, /api/internal/ingest/ticks
  -> Cloud data/market_data.db
  -> /api/realtime/dashboard, /api/realtime/intraday_fusion
```

关键约束：
- `INGEST_TOKEN` 必须在 Windows 与 Cloud 对齐。
- `ENABLE_CLOUD_COLLECTOR=false` 是云端默认红线。
- Windows crawler 必须只在真实交易日交易时段抓取；周末/节假日不跑全量轮扫和收盘 sweep。
- `ZhangDataLiveCrawler` 只能保留一个有效 Python crawler 进程，重复进程会造成重复抓取和云端反复覆盖。

## Mac 本地实时现状
- 本地启动脚本：`ops/start_local_research_station.sh`。
- 默认后台：`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`。
- 本地历史 / 复盘 / 选股读取 `/Users/dong/Desktop/AIGC/market-data` 下同步后的正式库。
- 当日单票盯盘如发现本地 ticks 陈旧，可由 `backend/app/routers/market.py` 的按需 hydrate 逻辑调用 `fetch_live_ticks` 补齐该股票当天数据。

## 当前仍需继续做的
- tick 多源 fallback 与自愈进一步完善
- 如需要“Mac 本地也完全等同生产连续盯盘”，应显式新增本地实时模式，而不是让本地研究站默认长期外采。
