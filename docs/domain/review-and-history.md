# 历史多维 / 正式复盘 / 沙盒复盘

## 覆盖 CAP
- `CAP-HISTORY-30M`
- `CAP-SANDBOX-REVIEW`

## 当前正式结论
1. 历史多维正式主路径是 `/api/history/multiframe`。
2. 正式复盘读 `/api/review/pool + /api/review/data`。
3. 正式复盘 canonical 路由是 `/review`；`/sandbox-review` 只保留为兼容跳转。
4. 沙盒复盘继续保留，但与正式链路隔离。

## 当前实现边界
- `GET /api/review/pool` 返回正式复盘股票池，空池时必须显式提示。
- `GET /api/review/data` 支持 `5m / 15m / 30m / 60m / 1d`，其中 `60m` 在内部按 `1h` 聚合。
- `1d` 读取 `history_daily_l2`，分钟级读取 `history_5m_l2` 后按粒度聚合。
- 正式复盘不依赖选股库；选股页右侧历史图有自己的 `/api/selection/history/multiframe` fallback，不改变复盘主契约。

## 当前仍需继续做的
- 本地正式历史覆盖继续补齐
- 旧兼容链路继续收口
