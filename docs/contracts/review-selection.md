# 复盘 / 选股研究契约

## 1. 正式复盘接口
- `GET /api/review/pool`
- `GET /api/review/data`

## 2. 选股研究接口
- `GET /api/selection/health`
- `GET /api/selection/candidates`
- `GET /api/selection/trade-dates`
- `GET /api/selection/daily-candidates`
- `GET /api/selection/daily-trade-dates`
- `GET /api/selection/daily-profile/{symbol}`
- `GET /api/selection/market-environment`
- `GET /api/selection/market-environment/backtest-summary`
- `GET /api/selection/market-environment/source-regime-summary`
- `GET /api/selection/profile/{symbol}`
- `GET /api/selection/research-context/{symbol}`
- `POST /api/selection/research-context/{symbol}/prepare`
- `POST /api/selection/research-context/prewarm`
- `POST /api/selection/quick-event-judge`
- `GET /api/selection/history/multiframe`
- `GET /api/selection/backtests`
- `GET /api/selection/backtests/{run_id}`
- `GET /api/selection/v2/evaluate`
- `GET /api/selection/stable-callback/evaluate`
- `GET /api/selection/trend-continuation/evaluate`
- `POST /api/selection/backtests/run`
- `POST /api/selection/refresh`
- `POST /api/selection/daily-refresh`

## 3. 契约重点
1. 选股派生结果的正式主链语义是 `selection_research_main`：Windows 现役物理名就是 `selection_research.db`；旧 `selection_research_windows.db` 已退休；Mac 主读外置 `market-data/research/current/selection/selection_research.db`；repo 内 `data/selection/selection_research.db` 只按本地回退 / 兼容副本理解。
2. 选股右侧历史图允许专用 fallback，但不改变主业务历史契约。
3. 复盘页股票池当前以正式历史覆盖为准，不再靠早期旧页面口径。
4. 研究上下文包是页面和 Codex 的共同入口，包含 selection profile、trade plan、price/L2 series、event feed/coverage/audit、company profile、financial snapshot、decision brief、research evidence。
5. `prepare/prewarm/quick-event-judge` 为写/生成类接口，必须走写权限。
6. `strategy` 当前支持 `stable_capital_callback`、`trend_continuation_callback`、`v2` 以及旧兼容策略名；默认入口应优先使用稳定回调策略。
7. 策略评估接口是研究工具，不能直接当生产交易 API。
8. 每日候选接口是选股工作台主入口，返回统一候选、来源明细、退出观察池和市场环境辅助判断；市场环境只用于辅助“是否参与/是否防守”，不改变候选源原始结论。
9. 市场环境门控接口读取研究产物与当前候选上下文，提供水位、分型、来源表现和回测摘要；它是决策辅助，不是自动交易风控指令。
