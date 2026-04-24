# 散户情绪契约

## 1. 当前正式接口
- `GET /api/sentiment/dashboard/{symbol}`
- `GET /api/sentiment/overview/{symbol}`
- `GET /api/sentiment/heat_trend/{symbol}`
- `GET /api/sentiment/feed/{symbol}`
- `GET /api/sentiment/daily_scores/{symbol}`
- `GET /api/sentiment/summary/history/{symbol}`
- `GET /api/sentiment/trend/{symbol}`
- `GET /api/sentiment/comments/{symbol}`
- `GET /api/sentiment/keywords/{symbol}`

## 2. 写接口
- `POST /api/sentiment/crawl/{symbol}`
- `POST /api/sentiment/summary/{symbol}`
- `POST /api/sentiment/internal/*`

## 3. 契约重点
1. 当前正式源以股吧单源为主。
2. 结构化结果优先通过 overview / heat_trend / feed / daily_scores 暴露。
3. 旧多源设计不再默认视为当前正式能力。
