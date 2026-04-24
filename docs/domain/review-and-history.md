# 历史多维 / 正式复盘 / 沙盒复盘

## 覆盖 CAP
- `CAP-HISTORY-30M`
- `CAP-SANDBOX-REVIEW`

## 当前正式结论
1. 历史多维正式主路径是 `/api/history/multiframe`。
2. 正式复盘读 `/api/review/pool + /api/review/data`。
3. 沙盒复盘继续保留，但与正式链路隔离。

## 当前仍需继续做的
- 本地正式历史覆盖继续补齐
- 旧兼容链路继续收口
