# 03_DATA_CONTRACTS（数据与接口契约入口）

> 目标：只回答“当前正式有哪些数据层、哪些接口是正式契约、详细字段去哪看”。
> 表结构细节与长 payload 不再堆在本页。

## 1. 契约使用规则
1. 本页只记录当前正式契约目录。
2. 详细字段、示例 payload、特殊兼容说明下沉到 `docs/contracts/`。
3. 若接口或表已经不是当前正式主路径，不再在本页正文展开。

## 2. 当前契约分层
| 层级 | 说明 |
|---|---|
| Raw / Fact | 原始或事实层，承接 ticks / snapshots / events / official events |
| Derived | 聚合层、研究层、正式消费层 |
| API Contract | 前后端正式接口、写接口权限、空状态语义 |

## 3. 先看哪个契约文档
| 主题 | 文档 |
|---|---|
| 主要数据表与数据库边界 | `docs/contracts/storage.md` |
| 市场数据 / 实时 / 历史 / review 契约 | `docs/contracts/market-realtime.md` |
| 散户情绪契约 | `docs/contracts/sentiment.md` |
| 选股研究契约 | `docs/contracts/review-selection.md` |
| 单票官方事件层契约 | `docs/contracts/stock-events.md` |

## 4. 当前正式数据库/目录
| 载体 | 角色 |
|---|---|
| `data/market_data.db` | 主业务消费库（Mac 本地研究站主读） |
| `data/atomic_facts/*` | 原子事实层 / 治理层结果 |
| `data/selection/selection_research.db` | 选股研究独立库 |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离数据域 |

## 5. 当前正式 API 组
| 组别 | 典型接口 |
|---|---|
| 市场/实时 | `/api/realtime/dashboard`, `/api/realtime/intraday_fusion` |
| 历史/复盘 | `/api/history/multiframe`, `/api/review/pool`, `/api/review/data` |
| 散户情绪 | `/api/sentiment/*` |
| 选股研究 | `/api/selection/*` |
| 官方事件层 | `/api/stock_events/*` |
| Watchlist / Config / Ingest | `/api/watchlist`, `/api/config`, `/api/ingest/*` |

## 6. 全局契约红线
1. 写接口必须走 `X-Write-Token`。
2. 空状态必须显式返回，不允许静默假空。
3. 正式主路径与沙盒/过渡链路必须隔离。
4. 事件层、选股层、原子层尽量独立库或独立表域，不回写旧兼容主表语义。
