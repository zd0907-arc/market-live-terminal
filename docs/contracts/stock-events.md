# 单票官方事件层契约

## 1. 主要表
- `stock_events`
- `stock_event_entities`
- `stock_symbol_aliases`
- `stock_event_ingest_runs`
- `stock_event_daily_rollup`

## 2. 读接口
- `GET /api/stock_events/capabilities`
- `GET /api/stock_events/feed/{symbol}`
- `GET /api/stock_events/coverage/{symbol}`
- `GET /api/stock_events/audit/{symbol}`

## 3. 写接口
- `POST /api/stock_events/announcements/{symbol}`
- `POST /api/stock_events/qa/shenzhen/{symbol}`
- `POST /api/stock_events/qa/shanghai/{symbol}`
- `POST /api/stock_events/news/short/{symbol}`
- `POST /api/stock_events/news/major/{symbol}`
- `POST /api/stock_events/bundle/{symbol}`
- `POST /api/stock_events/hydrate/{symbol}`
- `POST /api/stock_events/internal/*`

## 4. 契约重点
1. 事件层承接公告 / 问答 / 资讯等官方事件事实。
2. 当前无 token 模式下也允许公共 fallback。
3. 当前已实现事实采集，后续仍需补事件理解层。
