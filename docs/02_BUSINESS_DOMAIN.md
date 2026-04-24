# 02_BUSINESS_DOMAIN（业务能力地图）

> 目标：只回答“这个系统当前有哪些能力、做到什么程度、详细说明去哪看”。
> 过程、长验收、长方案不再堆在本页。

## 1. 使用规则
1. 本页只保留能力地图与当前状态。
2. 新需求先定位 CAP，再进入 `docs/changes/` 建卡。
3. 如果一个能力的长期事实变了，先回写本页，再补对应子文档。

## 2. 能力目录
| CAP | 能力 | 当前状态 | 详细说明 |
|---|---|---|---|
| `CAP-MKT-TIME` | 交易日/交易时段状态机 | `LIVE` | `docs/domain/realtime-monitor.md` |
| `CAP-REALTIME-FLOW` | 实时盯盘 / 当日分时主链路 | `LIVE` | `docs/domain/realtime-monitor.md` |
| `CAP-RETAIL-SENTIMENT` | 散户一致性观察 | `LIVE_PARTIAL` | `docs/domain/retail-sentiment.md` |
| `CAP-STOCK-EVENTS` | 单票官方事件层 | `LIVE_PARTIAL` | `docs/domain/stock-events.md` |
| `CAP-HISTORY-30M` | 历史多维 / 正式复盘历史链路 | `LIVE` | `docs/domain/review-and-history.md` |
| `CAP-WIN-PIPELINE` | Windows 数据主站 / 三端协同 | `LIVE` | `docs/domain/data-pipeline.md` |
| `CAP-L2-HISTORY-FOUNDATION` | 盘后 L2 / 原子层底座 | `LIVE_PARTIAL` | `docs/domain/data-pipeline.md` |
| `CAP-SANDBOX-REVIEW` | 沙盒复盘验证闭环 | `MAINTAINED` | `docs/domain/review-and-history.md` |
| `CAP-SELECTION-RESEARCH` | 选股研究与回测闭环 | `LIVE_PARTIAL` | `docs/domain/selection-research.md` |

## 3. 当前能力判断规则
- `LIVE`：已进入当前正式主路径
- `LIVE_PARTIAL`：主路径已存在，但还有重要增强或收口未完成
- `MAINTAINED`：仍保留，但不是当前主线重点

## 4. 当前总判断
1. 当前主线是：**Windows 数据主站 + Mac 本地研究站 + Cloud 轻量盯盘**。
2. 当前最重要的长期建设方向：
   - 原子层与旧依赖继续收口
   - 选股研究底座继续补齐
   - 官方事件层继续从“事实采集”走向“事件理解”
3. 所有具体需求过程，一律进入 `docs/changes/`，不再堆到本页。

## 5. 相关入口
- 变更流程：`docs/06_CHANGE_MANAGEMENT.md`
- 契约目录：`docs/03_DATA_CONTRACTS.md`
- 运维入口：`docs/04_OPS_AND_DEV.md`
