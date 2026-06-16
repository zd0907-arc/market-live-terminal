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
| `market-data/live/market_data.db` | Mac 正式主读轻量消费库；Windows 正式产出后同步到这里 |
| `market-data/live/user_data.db` | Mac 正式主读用户态配置库 |
| repo 内 `data/market_data.db` | 当前默认不存在；只有旧兼容链显式重建时才允许出现 |
| repo 内 `data/user_data.db` | 当前默认不存在；只有旧 lite / 兼容链显式重建时才允许出现 |
| `atomic_compact_main` | 盘后明细底座；Windows 现役物理名是 `market_atomic_mainboard_compact_current.db`；Mac 主读 `market-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db` |
| `selection_research_main` | 每日选股研究主链；Windows 现役物理名是 `selection_research.db`；Mac 主读 `market-data/research/current/selection/selection_research.db` |
| `model_feature_store_main` | 模型训练与验证主链；Windows 现役物理名是 `model_feature_store.db`；Mac 主读 `market-data/research/current/selection/model_feature_store.db` |
| repo 内 `data/selection/selection_research.db` | 当前默认不存在；只有显式兼容链重建时才允许出现 |
| `data/sandbox/review_v2/*` | 沙盒复盘隔离数据域 |

补充：
- 当前 Mac 正式研究根目录是一份外置同步库：`/Users/dong/ZhangData/market-data`
- `market-data/live/market_data.db` 同时承接全市场历史/回退消费；`research/current` 发布成功不代表这份 `live` 历史底座已经同步到 NAS
- repo 内 `data/selection/selection_research.db`、`data/market_data.db`、`data/user_data.db` 不应再被理解成默认正式主库
- `selection_research_windows.db`、`compact_smoke_*`、`model_feature_store_smoke_*` 这些 Windows 旧物理名已退休到冷备区；默认口径统一按 `selection_research_main`、`atomic_compact_main`、`model_feature_store_main` 的 canonical 名解释
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
5. Windows 侧不再允许旧实验式物理名和正式主链并列；旧名一律进入冷备退休区。
6. 生产实时 ingest 只接受 Windows crawler 写入；Cloud 默认不主动外采。
7. `backend/sample_data/shadow/market.db`、`backend/sample_data/shadow/market_data.db`、`backend/sample_data/examples/market_data_sample.db` 只算 shadow / sample / 排障对象，不进入正式契约或主链解释。
