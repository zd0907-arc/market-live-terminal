# 实时盯盘与交易时段能力

## 覆盖 CAP
- `CAP-MKT-TIME`
- `CAP-REALTIME-FLOW`

## 当前正式结论
1. 当日分时页正式主路径是 `/api/realtime/intraday_fusion`。
2. 交易日状态机已经收口到明确的盘前 / 盘中 / 午间 / 盘后 / 休盘语义。
3. Cloud 盯盘仍是轻量能力，不等于本地研究站完整能力。

## 当前仍需继续做的
- Windows 实时 crawler 的跨重启稳态化
- tick 多源 fallback 与自愈进一步完善
