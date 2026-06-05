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
| `market-data/market_data.db` | Mac 正式主读轻量消费库；Windows 正式产出后同步到这里 |
| repo 内 `data/market_data.db` | 本地回退 / 兼容副本；只在外置 `market-data` 不存在时才作为 fallback |
| `atomic_compact_main` | 盘后明细底座；Windows 当前实际主写物理名仍可能是 `compact_smoke_*`，Mac 主读 `market-data/atomic_facts/market_atomic_mainboard_compact_current.db` |
| `selection_research_main` | 每日选股研究主链；Windows 主写 `selection_research_windows.db`，Mac 主读 `market-data/selection/selection_research.db` |
| `model_feature_store_main` | 模型训练与验证主链；Windows 当前实际主写物理名仍可能是 `model_feature_store_smoke_*`，Mac 主读 `market-data/selection/model_feature_store.db` |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离数据域 |
| `backend/market.db` / `backend/app/market_data.db` / `backend/app/db/market_data.db` | shadow / sample / 排障对象；不属于正式主链 |

补充：
- 当前 Mac 正式研究根目录是一份外置同步库：`/Users/dong/Desktop/AIGC/market-data`
- repo 内 `data/selection/selection_research.db`、`data/market_data.db` 不应再被理解成默认正式研究主库
- `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这些 Windows 物理名承担正式语义，但后续治理口径统一按 `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 解释
- `backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 只按 shadow / sample / 排障对象理解，不进入正式契约层
- 每日盘后完成标准不只看基础数据落表，还要求 `selection_strategy_runs` 里当天活跃选股来源完成 success 记录；当前活跃来源为 `spark_opportunity_selector`、`stable_capital_callback`、`trend_continuation_callback`、`probe_day0_watch`、`probe_d3_confirmed`

## 5. 当前正式 API 组
| 组别 | 典型接口 |
|---|---|
| 市场/实时 | `/api/realtime/dashboard`, `/api/realtime/intraday_fusion` |
| 历史/复盘 | `/api/history/multiframe`, `/api/review/pool`, `/api/review/data` |
| 散户情绪 | `/api/sentiment/*` |
| 选股研究 | `/api/selection/*` |
| 官方事件层 | `/api/stock_events/*` |
| Watchlist / Config / Ingest | `/api/watchlist`, `/api/config`, `/api/internal/ingest/*` |

## 6. 探索接口
| 组别 | 当前口径 |
|---|---|
| 市场热度研究 | `/api/market_heat/latest`, `/api/market_heat/history` 当前仅作为 `CAP-MARKET-HEAT` 探索接口；在热点能力正式化前，不并入正式策略契约。 |

## 7. 全局契约红线
1. 写接口必须走 `X-Write-Token`。
2. 空状态必须显式返回，不允许静默假空。
3. 正式主路径与沙盒/过渡链路必须隔离。
4. `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 三条正式主链独立存储，不回写旧兼容主表语义。
5. `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这些名字像实验、实际承担主链的对象，必须在文档里明确正式语义，不再把它们当临时试验件。
6. 生产实时 ingest 只接受 Windows crawler 写入；Cloud 默认不主动外采。
7. `backend/market.db`、`backend/app/market_data.db`、`backend/app/db/market_data.db` 只算 shadow / sample / 排障对象，不进入正式契约或主链解释。
