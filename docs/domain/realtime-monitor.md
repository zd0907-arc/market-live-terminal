# 实时盯盘与交易时段能力

## 覆盖 CAP
- `CAP-MKT-TIME`
- `CAP-REALTIME-FLOW`

## 当前正式结论
1. 当日分时页正式主路径是 `/api/realtime/intraday_fusion`。
2. 交易日状态机已经收口到明确的盘前 / 盘中 / 午间 / 盘后 / 休盘语义。
3. 当前线上盯盘节点是 NAS `live/market_data.db`：线上后端只被动接收 ingest，不主动外采。
4. Mac 本地盯盘默认读取本机同步库；单票接口允许按需补拉当日 ticks，但不默认启动生产级后台 crawler。
5. 首页 `realtime/dashboard` 盘后首次打开时，默认先看今天；如果该票今天分时尚未就绪且用户没有手动指定日期，必须自动回退到上一交易日，不能空白。

## 生产实时链路
```text
浏览器盯盘页
  -> /api/monitor/heartbeat
  -> NAS active_symbols
  -> Windows `ZhangDataLiveCrawler` / NAS crawler(观察期)
  -> 腾讯行情 / AkShare
  -> /api/internal/ingest/snapshots, /api/internal/ingest/ticks
  -> NAS live/market_data.db
  -> /api/realtime/dashboard, /api/realtime/intraday_fusion
```

关键约束：
- `INGEST_TOKEN` 必须在 Windows / NAS 线上后端对齐。
- `ENABLE_CLOUD_COLLECTOR=false` 仍是线上默认红线。
- Windows crawler 仍是当前正式基线；NAS crawler 已跑通但还在观察期，Windows 暂未下线。
- `ZhangDataLiveCrawler` 只能保留一个有效 Python crawler 进程，重复进程会造成重复抓取和线上反复覆盖。

## Mac 本地实时现状
- 本地启动脚本：`ops/start_local_research_station.sh`。
- 默认后台：`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`。
- 本地历史 / 复盘 / 选股读取 `/Users/dong/Desktop/AIGC/market-data` 下同步后的正式库。
- 当日单票盯盘如发现本地 ticks 陈旧，可由 `backend/app/routers/market.py` 的按需 hydrate 逻辑调用 `fetch_live_ticks` 补齐该股票当天数据。

## 当前仍需继续做的
- tick 多源 fallback 与自愈进一步完善
- 如需要“Mac 本地也完全等同生产连续盯盘”，应显式新增本地实时模式，而不是让本地研究站默认长期外采。
