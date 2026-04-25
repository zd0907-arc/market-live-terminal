# MOD-20260425-06 local monitor data source fix

## 背景
2026-04-25 本地 Mac 盯盘出现两类异常：
1. 周六查看利通电子时，当日分时页未展示上一交易日 `2026-04-24` 数据。
2. 历史多维页面最新数据只到 `2026-04-10`。

排查确认是两个问题叠加：
- 运行时问题：本地后端若直接用 `python -m backend.app.main` 手工启动，会默认读取项目内 `data/market_data.db`，而不是当前正式外置库 `/Users/dong/Desktop/AIGC/market-data/market_data.db`。
- 逻辑问题：`/api/realtime/dashboard` 与 `/api/realtime/intraday_fusion` 之前只会对“自然日当天”做按需补拉；周末“默认上一交易日”视图在本地缺票时会直接空白。

## 本次收口
1. 修复本地盯盘接口：
   - 当 `date` 未手动指定，且当前视图是默认上一交易日时，若本地缺该股票分时数据，允许按需补最近交易日一次。
   - 覆盖接口：
     - `/api/realtime/dashboard`
     - `/api/realtime/intraday_fusion`
2. 明确本地启动纪律：
   - Mac 本地后端必须通过 `bash ops/start_local_research_station.sh` 启动。
   - 禁止再直接手工 `python -m backend.app.main`，否则会绕过外置 `DB_PATH` 注入，导致读错库。
3. 验证结果：
   - 本地 `8000` 后端已按正式脚本重启，实际运行环境已带：
     - `DB_PATH=/Users/dong/Desktop/AIGC/market-data/market_data.db`
     - `SELECTION_DB_PATH=/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db`
     - `ATOMIC_MAINBOARD_DB_PATH=/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
   - 实测：
     - `GET /api/realtime/dashboard?symbol=sh603629` 返回 `display_date=2026-04-24`，`chart_len=49`
     - `GET /api/realtime/intraday_fusion?symbol=sh603629` 返回 `trade_date=2026-04-24`，`bars_len=49`
     - `GET /api/history/multiframe?symbol=sh603629&granularity=1d&days=30` 最新日期恢复到 `2026-04-24`

## 风险与边界
- 这次修的是“默认上一交易日”自动补拉，不包含“用户手动回溯任意历史日期”自动补拉；手动历史日期仍保持只读。
- 前端显示 `v5.0.0` 仅代表前端版本，不代表本地后端一定是正确进程或正确数据源。
