# INV-20260309-01-intraday-flow-type-normalization

## 1. 基本信息
- 标题：当日分时资金流仅显示股价线（主力线为0）
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：CHG-20260309-09
- 关联 CAP：CAP-REALTIME-FLOW
- 关联 STG：独立紧急修复

## 2. 背景与目标
- 现象：前端当日分时图只有股价线，主力买卖与净流入线缺失。
- 目标：恢复 `/api/realtime/dashboard` 中资金流字段的正确计算与展示。

## 3. 方案与边界
- 做什么：统一成交方向识别，兼容 `B/S/M`、`buy/sell/neutral`、`买盘/卖盘/中性盘`。
- 不做什么：不改阈值策略，不改前端图表逻辑，不改历史口径。

## 4. 执行步骤（按顺序）
1. 本地复现并核查 `trade_ticks.type` 实际值。
2. 定位后端聚合仅识别 `买盘/卖盘` 与 `buy/sell` 的逻辑缺口。
3. 新增统一归一化工具并接入 realtime/30m/daily 聚合路径。
4. 重启后端并验证 `/api/realtime/dashboard?symbol=sz000833`。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-09 23:31` 本地库存在 `type=B/S/M` 的当日 ticks，When 请求 `/api/realtime/dashboard?symbol=sz000833`，Then `chart_data` 应包含非零主力资金数据。
- Given 同一请求，When 检查 `latest_ticks`，Then `type` 应标准化为 `buy/sell/neutral`。

## 6. 风险与回滚
- 风险：若上游新增未识别类型，仍可能被归为 `neutral`。
- 回滚：回退本次 3 个后端文件改动，恢复旧识别逻辑。

## 7. 结果回填
- 实际改动：新增 `trade_side` 归一化模块，并在 realtime/history 聚合链路统一调用。
- 验证结果：`code=200, chart=241, nonzero=237, latest_types=[buy,neutral,sell]`。
- 遗留问题：建议后续增加类型枚举告警（未知值采样日志）。

## 8. 归档信息
- 归档时间：2026-03-09
- Archive ID：ARC-CHG-20260309-intraday-flow-side-normalization
- 归档路径：docs/archive/changes/ARC-CHG-20260309-intraday-flow-side-normalization.md
