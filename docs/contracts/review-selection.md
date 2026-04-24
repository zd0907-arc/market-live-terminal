# 复盘 / 选股研究契约

## 1. 正式复盘接口
- `GET /api/review/pool`
- `GET /api/review/data`

## 2. 选股研究接口
- `GET /api/selection/health`
- `GET /api/selection/candidates`
- `GET /api/selection/profile/{symbol}`
- `GET /api/selection/history/multiframe`
- `GET /api/selection/backtests`
- `GET /api/selection/backtests/{run_id}`
- `POST /api/selection/backtests/run`
- `POST /api/selection/refresh`

## 3. 契约重点
1. 选股派生结果写入 `data/selection/selection_research.db`。
2. 选股右侧历史图允许专用 fallback，但不改变主业务历史契约。
3. 复盘页股票池当前以正式历史覆盖为准，不再靠早期旧页面口径。
