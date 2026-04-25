# 市场 / 实时 / 历史 / 复盘契约

## 1. 当前正式接口
### 实时
- `GET /api/realtime/dashboard`
- `GET /api/realtime/intraday_fusion`
- `GET /api/market/sentiment`
- `GET /api/market/sentiment/history`

### 历史
- `GET /api/history/multiframe`
- `GET /api/history/local`
- `GET /api/history/trend`

### 正式复盘
- `GET /api/review/pool`
- `GET /api/review/data`

### 沙盒复盘（隔离链路）
- `GET /api/sandbox/review_data`
- `GET /api/sandbox/pool`

## 2. 契约重点
1. `intraday_fusion` 是当日分时页正式主路径。
2. `history/multiframe` 是多时间粒度正式主路径。
3. 正式复盘与沙盒复盘必须隔离，不互相回退污染。
4. 无数据必须显式返回，不允许静默假空数组冒充成功态。
5. 生产实时写入只允许 Windows crawler 调用 `/api/internal/ingest/ticks` 与 `/api/internal/ingest/snapshots`；Cloud 自身默认不外采。
6. Mac 本地按需 hydrate 只服务本机开发/研究，不代表生产 ingest。

## 3. 实时相关表
- `trade_ticks`：逐笔数据；ingest 按 `symbol + date` 覆盖写，避免重复累加。
- `history_30m`：盯盘侧 30m 聚合。
- `sentiment_snapshots`：盘口快照；唯一键为 `symbol + date + timestamp`。
- `realtime_5m_preview` / `realtime_daily_preview`：兼容预览层，非当前唯一事实源。

## 4. 运行关系
- 线上：浏览器 -> Cloud API -> Windows crawler ingest -> Cloud DB -> 浏览器。
- Mac 本地：浏览器 -> Mac backend -> Mac DB；必要时单票按需补拉。

## 5. 相关细节来源
- review / history 的更细粒度规则继续以对应变更卡与测试为准。
