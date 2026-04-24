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

## 3. 相关细节来源
- review / history 的更细粒度规则继续以对应变更卡与测试为准。
