# AI 双核协作交接控制台 (Handoff Log)
> 这是给另一个 AI 看的。无论是修改了前端还是后端逻辑，只要动作会影响大局或需要协作，随时在此报备。新报备在最上面。

---

## 2026-03-07 17:05 - [后端 AI] - v4.2.8 已发生产（30m 8桶口径修复上线）

**1. 完成了什么？**
- 发布 `v4.2.8` 到生产（commit: `24a81b7`，tag: `v4.2.8`）。
- 口径修复已上线：
  - 统一 30m 为 8 个标准桶；
  - API 层过滤 `11:30/15:00` 非标准桶；
  - 禁用 backfill 的历史K线零流入占位写入默认路径；
  - ETL 与后端实时聚合使用同一桶映射。

**2. 线上冒烟**
- `/api/health` = 200
- `2026-02-13` 对 `sz000833`、`sh600206` 的 `/api/history/trend` 均已从 10 bars 收敛为 8 bars（`09:30~14:30`）。

**3. 未完成（待 Windows ETL 重建）**
- 历史污染窗口的“资金流数值偏差”仍需 Windows 离线 L2 重建后 merge 才能彻底修复。
- 当前自动化阻塞：Windows SSH 仍未免密可用（Agent 端仍 `Permission denied`）。

## 2026-03-07 13:20 - [后端 AI] - 30m口径收敛补丁（8桶标准化）+ Windows自动执行阻塞更新

**1. 完成了什么？**
- 新增统一时间桶工具 `backend/app/core/time_buckets.py`，固定 30m 为 8 个标准桶。
- 聚合链路统一到同一桶逻辑：
  - `backend/app/services/analysis.py::aggregate_intraday_30m`
  - `backend/app/routers/analysis.py` 实时拼接分支
  - `backend/scripts/etl_worker_win.py` 离线 ETL 30m 聚合
- `backend/app/db/crud.py::get_history_30m` 增加标准时间过滤，API 层不再返回 `11:30/15:00` 非标准桶数据。
- `backend/app/services/backfill.py` 禁用“历史K线占位0流入写入 history_30m”的默认行为，避免继续污染。
- `backend/scripts/fetch_local_data.py` 补 canonical 映射，兼容 10bar 源转 8bar。
- 新增测试 `backend/tests/test_time_buckets.py`；全量后端测试通过 `14 passed`，前端构建通过。
- 契约文档补充 `history_30m.start_time` 的 8 桶约束。(`docs/03_DATA_CONTRACTS.md`)

**2. 当前阻塞**
- 用户已反馈 Windows 可操作，但当前 Agent 到 `100.115.228.56` 仍无法免密登录（`Permission denied`），导致无法在本会话内直接自动执行 Windows ETL 重建。
- 已确认这不影响云端代码发布；但会影响“历史污染窗口数据重建”最后一步。

**3. 接下来动作**
- 等 Windows SSH 免密真正生效后，立即执行：Windows ETL 重建 -> 上传 history DB -> 云端 merge -> 生产复核。

## 2026-03-07 12:55 - [后端 AI] - 30分钟线专项诊断（粤桂股份）+ 修复方案出具（待确认执行）

**1. 完成了什么？**
- 对生产环境 `sz000833`（粤桂股份）执行了“日线 vs 30m”核查：`2026-02-13` 确认存在显著偏差（用户反馈成立）。
- 扩展核查 watchlist 后确认该问题并非单票，而是特定日期窗口的系统性问题：出现 `10 bars/day` + 大量“资金流=0但OHLC非0”的占位bar。
- 输出专项文档 `09_30M_DIAGNOSIS_PLAN_2026-03-07.md`，包含事实证据、根因判断、分阶段修复方案（Phase A~D）和验收标准。
- 文档治理补充：将 Windows 统一运行路径 `D:\market-live-terminal` 写入 `04_OPS_AND_DEV.md` 与 `REMOTE_CONTROL_GUIDE.md`。

**2. 阻塞与说明**
- 当前 Agent 无法代输 Windows SSH 密码（非免密），全自动远程执行仍受限。
- 已给出两种解除方式：手动执行一次 `./sync_to_windows.sh` 或配置 Windows SSH 公钥。

**3. 接下来需要另一个 AI（前端）做什么？**
- 暂无前端改动要求；等待后端完成数据重建后再联调 30m 展示。

## 2026-03-07 12:10 - [后端 AI] - 审计文档回填 + 全局文档治理 + 版本管理（v4.2.7）

**1. 完成了什么？**
- 按“规划文档末尾回填执行结果”的要求，已在 `06_TECH_AUDIT_2026-03-07.md` 新增第 6 章，逐项给出 P0/P1/P2（F-001~F-014）实际完成状态、验证结果、阻塞项。(`docs/06_TECH_AUDIT_2026-03-07.md`)
- 完成一轮文档治理：新增 `08_DOCS_GOVERNANCE.md`，明确 Active 文档集、归档规则、更新触发条件和最小闭环流程。(`docs/08_DOCS_GOVERNANCE.md`)
- README 文档入口同步补齐“文档治理与索引”链接，作为统一入口之一。(`README.md`)
- 版本管理完成到 `v4.2.7`：
  - `package.json` version = `4.2.7`
  - `src/version.ts` `APP_VERSION` 与 `RELEASE_NOTES` 首条更新
  - `backend/app/main.py` FastAPI version = `4.2.7`

**2. 测试情况**
- `python3 -m pytest -q backend/tests`：`11 passed`
- `npm run build`：成功（产物体积维持在既定目标范围）

**3. 当前发布状态**
- 已完成“文档、版本、测试”三项发版前收口；当前可进入生产发布步骤。
- Windows 离线阻塞仍保留在 `docs/07_PENDING_TODO.md`，本次发布不依赖 Windows 在线即可进行。

## 2026-03-07 11:40 - [后端 AI] - P1收口完成（情绪接口契约统一）+ P2收尾确认

**1. 完成了什么？**
- P1/F-010 代码侧收口：`/api/sentiment/summary/history/{symbol}`、`/api/sentiment/trend/{symbol}`、`/api/sentiment/comments/{symbol}` 全部统一为 `APIResponse`，空状态返回 `{"code":200,"data":[],"message":"No data found"}`，不再裸返回数组。(`backend/app/routers/sentiment.py`)
- `POST /api/sentiment/crawl/{symbol}` 也统一为 `APIResponse`，并保持写鉴权。(`backend/app/routers/sentiment.py`)
- 前端兼容适配：`sentimentService` 增加 `unwrapArrayData`，同时兼容“老的裸数组”和“新的 APIResponse 包装”，避免联调断裂。(`src/services/sentimentService.ts`)
- 新增回归测试 `backend/tests/test_sentiment_response_shape.py`，覆盖情绪接口空状态/错误状态响应形状。
- 契约文档同步：补齐 sentiment 三个 GET 接口的返回约束，移除“仍有裸数组遗留”的说明。(`docs/03_DATA_CONTRACTS.md`)

**2. 测试情况**
- `python3 -m pytest -q backend/tests`：`11 passed`
- `npm run build`：成功，且无 chunk>500KB 告警（P2 目标维持）
- FastAPI 本地冒烟（TestClient）：`/api/sentiment/summary/history`、`/api/sentiment/trend`、`/api/sentiment/comments` 均返回 `200` 且 `code=200`、`data` 为数组。

**3. 当前状态**
- P1 已完成（含此前 F-007/008/009/011），P2 已收尾（F-012/F-014 完成，F-013 采用“忽略防误改”降风险方案并落地）。
- Windows 离线阻塞项仍在：见 `docs/07_PENDING_TODO.md`。后续一旦改 Windows 采集链路，必须先提醒用户执行同步。

## 2026-03-07 11:08 - [后端 AI] - P2第三批收敛（图表包二次拆分，清除构建超大包告警）

**1. 完成了什么？**
- 在 `vite.config.ts` 将 `manualChunks` 升级为函数拆分策略：`vendor-echarts`、`vendor-zrender`、`vendor-recharts`、`vendor-ui` 分离，避免单一超大图表包。(`vite.config.ts`)
- 构建结果：
  - `index` 约 `210KB`
  - `vendor-echarts` 约 `354KB`
  - `vendor-zrender` 约 `186KB`
  - `vendor-recharts` 约 `394KB`
  - 已不再出现 `chunk > 500KB` 的 Vite 警告。

**2. 测试情况**
- `npm run build`：成功，且无大包告警
- `python3 -m pytest -q backend/tests`：`7 passed`

**3. 备注**
- 本轮仍未发生产，属于本地可发布状态收敛。

## 2026-03-07 10:55 - [后端 AI] - P2第二批收敛（图表按需加载 + ECharts 按需引入）

**1. 完成了什么？**
- `App` 层改为 `React.lazy + Suspense` 按需加载 `RealtimeView/HistoryView/SentimentDashboard`，避免首次加载把全部图表依赖一次打包进主入口。(`src/App.tsx`)
- `HistoryView` 内部把 `HistoryCandleChart` 继续拆成懒加载，30 分钟线页面仅在实际打开时再拉 ECharts 模块。(`src/components/dashboard/HistoryView.tsx`)
- `HistoryCandleChart` 从 `echarts-for-react` 全量模式切换为 `echarts/core` 按需注册（Line/Candlestick/Grid/Tooltip/Legend/Canvas），显著缩减该模块体积。(`src/components/dashboard/HistoryCandleChart.tsx`)
- Vite 拆包策略保留最小 `vendor-ui`，不再强制把全部图表库塞进同一个 `vendor-chart`。(`vite.config.ts`)

**2. 结果（本地构建）**
- 主入口包降到约 `214KB`（gzip `66KB`），图表包改为按需拉取。
- 仍有一个 `HistoryCandleChart` chunk 约 `551KB` 的体积告警（较之前 ~`1.14MB` 已明显下降），后续可再做路由级功能裁剪。

**3. 测试情况**
- `python3 -m pytest -q backend/tests`：`7 passed`
- `npm run build`：成功（仅剩大 chunk 告警）

## 2026-03-07 10:32 - [后端 AI] - 冒烟通过 + P2第一批收敛（入口清理/README校准/旧副本防误改）

**1. 完成了什么？**
- 本地冒烟通过（未发生产）：
  - `GET /api/health`=200
  - `GET /api/verify_realtime`=200
  - `POST /api/config` 无 token=401，有 token=200
  - `POST /api/internal/ingest/ticks` 错 token=401
  - `GET /api/realtime/dashboard`=200
- P2/F-012：清理前端入口历史残留，移除 `index.html` 中无效 `importmap` 与不存在的 `/index.css` 引用，消除构建时该告警。(`index.html`)
- P2/F-014：重写 `README.md` 为当前可执行版本（本地启动命令、真实文档入口、发布与同步脚本、遗留目录提醒）。(`README.md`)
- P2/F-013（降风险版）：先不删旧目录，新增忽略规则避免 AI/开发误扫误改：`market-live-terminal/` 加入 `.cursorignore` 与 `.gitignore`。(`.cursorignore`, `.gitignore`)
- P2/F-012（补充）：在 `vite.config.ts` 增加 `manualChunks`，把图表库拆出 `vendor-chart`，主包显著下降（约 `1.86MB -> 302KB`），但图表 vendor 仍超 500KB 告警，后续需路由级动态加载。(`vite.config.ts`)

**2. 变更了契约吗？**
- 否。仅入口治理与文档校准。

**3. 当前遗留**
- 仍有打包体积告警（chunk > 500k），需后续做路由级拆包/manualChunks（P2后续项）。
- Windows 节点离线待恢复：见 `docs/07_PENDING_TODO.md`。

## 2026-03-07 10:05 - [后端 AI] - v4.2.6 P1第一批改造（节假日判定收敛 + 背景任务治理 + 实时缓存）

**1. 完成了什么？**
- P1/F-007：交易日历改为“保守判定（fail-closed）”，移除“按工作日补齐到今天”的高风险逻辑；当请求日期超出缓存日历时会先尝试刷新，仍未知则按非交易日处理。(`backend/app/core/calendar.py`)
- P1/F-009：移除 `/api/watchlist` 里的裸 `threading.Thread`，引入共享线程池执行器 `submit_background`（限流到固定 worker，统一日志与异常收口）。(`backend/app/core/task_runner.py`, `backend/app/routers/watchlist.py`)
- P1/F-008：`calculate_realtime_aggregation` 新增短 TTL 签名缓存（按 `symbol+date+ticks签名+阈值`），降低同秒重复请求下的全量 pandas 重算开销。(`backend/app/services/analysis.py`)
- P1/F-010：契约文档对齐当前实现（trade_ticks ingest 覆盖写、`type` 兼容值、核心市场接口补充说明）。(`docs/03_DATA_CONTRACTS.md`)
- 新增人工阻塞待办板：记录“Windows 离线导致无法同步脚本”的长期提醒，并约定后续凡涉及 Windows 采集脚本改动必须先提醒用户同步。(`docs/07_PENDING_TODO.md`)

**2. 变更了契约吗？**
- 文档层有更新（`03_DATA_CONTRACTS.md`），接口字段结构未破坏。

**3. 测试情况**
- `python3 -m pytest -q backend/tests`：`7 passed`
- `npm run build`：成功（仍有历史大包告警与 `/index.css` 提示）

**4. 接下来需要另一个 AI（前端）做什么？**
- 无强制 UI 改动。仅需继续遵守写接口带 `X-Write-Token`，并在出现 401 时给出明确提示。

## 2026-03-07 09:36 - [后端 AI] - v4.2.5 生产实操修复（已上线）

**1. 完成了什么？**
- 已将本地 P0 修复代码同步到生产机并重建容器（backend + frontend），关键点已生效：
  - `verify_realtime` 响应模型恢复正确；
  - 写接口鉴权生效（无 token 返回 401）；
  - ingest 无效 token 返回 401；
  - realtime 默认展示日回退到 `2026-03-06`，`2026-03-07` 查询返回 404（不再复制）。
- 直接在生产环境执行离线补数：运行 `sync_local_to_cloud.sh` 对 7 只自选股注入 30m 历史，已补齐 `2026-03-03` 与 `2026-03-05` 缺失日期（每个交易日 8 根 30m）。
- 已清理生产库非交易日脏数据（watchlist 范围）：
  - 删除 `trade_ticks` 中 `2026-03-01` 9710 行、`2026-03-07` 27013 行；
  - 同步删除 `history_1m` 中 `2026-03-01` 768 行；
  - 当前 watchlist 范围内 `2026-03-01/2026-03-07` 的 `trade_ticks` 均为 0。
- 追加防线：`backend/app/routers/ingest.py` 新增 `normalize_ingest_date`，对非交易日日期自动回退到 `MarketClock.get_display_date()`，降低旧爬虫再次写错日的风险。

**2. 变更了契约吗？**
- 否。接口结构未改，属于运行逻辑与数据修复。

**3. 接下来需要另一个 AI（前端）做什么？**
- 无强制 UI 改动。建议刷新缓存后联调一次写接口（watchlist/config/sentiment）确认 401 提示文案对用户友好。

**4. 仍需人工配合（运维）**
- Windows 节点脚本远程同步失败（`Connection closed by 100.115.228.56 port 22`）。需人工在可交互终端执行一次：
  - `./sync_to_windows.sh`
- 当前生产 `INGEST_TOKEN/WRITE_API_TOKEN` 先用兼容值临时保业务（便于旧节点不中断）。待 Windows 新脚本上线后，建议立即统一轮换为强随机 token。

## 2026-03-07 03:15 - [后端 AI] - v4.2.4 发布收口（INGEST透传补丁 + 上线冒烟SOP）

**1. 完成了什么？**
- 修复了部署透传缺口：`deploy/docker-compose.yml` 为 backend 补充 `INGEST_TOKEN=${INGEST_TOKEN}`，避免服务端因未注入 token 一直 503 拒收 ingest。  
- 补充了发布必检与冒烟步骤：`docs/04_OPS_AND_DEV.md` 新增 v4.2.3+ 必填变量清单与上线后 4 条 curl 验证。  
- 更新安全运维样例：`docs/05_LLM_KEY_SECURITY.md` 的云端 `.env` 模板新增 `INGEST_TOKEN/WRITE_API_TOKEN/ENABLE_CLOUD_COLLECTOR`。

**2. 变更了契约吗？**
- 否。接口入参/出参未变化，仍遵循 `03_DATA_CONTRACTS.md` 既有定义。

**3. 接下来需要另一个 AI（前端）做什么？**
- 无代码改动要求。保持构建注入 `VITE_WRITE_API_TOKEN`，并在联调时关注写请求 401（token 缺失）提示文案是否易懂。

## 2026-03-07 02:35 - [后端 AI] - v4.2.3 P0止血修复（写鉴权 + 回填链路 + 云端禁外采默认）

**1. 完成了什么？**
- 修复了自选股回填断链：补充 `perform_historical_fetch` 同步包装函数，`watchlist` 新增后不再因为函数缺失直接失败。(`backend/app/services/backfill.py`)
- 修复了 backfill tick 入库字段顺序错位风险：`save_trade_ticks` 入参顺序改为 `(symbol,time,price,volume,amount,type,date)`，并同步修正快照生成索引。(`backend/app/services/backfill.py`)
- 修复 `/api/verify_realtime` 响应模型错误导致的运行时校验异常。(`backend/app/routers/market.py`)
- 安全收敛：
  - ingest 不再允许默认 token，未配置 `INGEST_TOKEN` 直接拒绝写入。(`backend/app/routers/ingest.py`)
  - Windows 启动脚本去掉明文 token，要求环境变量注入。(`start_live_crawler.bat`, `backend/scripts/live_crawler_win.py`)
  - 新增写接口鉴权中间层 `require_write_access`，并落到 watchlist/config/sentiment 手动触发 POST/DELETE。(`backend/app/core/security.py` + 对应 routers)
- 架构护栏：
  - 云端 `collector` 默认关闭，需显式 `ENABLE_CLOUD_COLLECTOR=true` 才会主动外采；默认遵守“云端仅被动 ingest”。(`backend/app/services/collector.py`, `deploy/docker-compose.yml`)
- 前端联调支持：业务写请求自动带 `X-Write-Token`（读取 `VITE_WRITE_API_TOKEN`）。(`src/config.ts`, `src/services/stockService.ts`, `src/services/sentimentService.ts`, `deploy/frontend.Dockerfile`)
- 顺手修复一条已红单测：补齐 `check_spoof_buy`。(`backend/app/services/monitor.py`)

**2. 变更了契约吗？**
- 是。补充了“写接口需 `X-Write-Token`”和 ingest token 无默认值约束。(`docs/03_DATA_CONTRACTS.md`)
- 环境变量蓝图新增 `WRITE_API_TOKEN` 与 `ENABLE_CLOUD_COLLECTOR`。(`docs/01_SYSTEM_ARCHITECTURE.md`)

**3. 接下来需要另一个 AI（前端）做什么？**
- 不需要额外 UI 改动。仅需确认部署时注入 `VITE_WRITE_API_TOKEN`，否则写操作会被后端拒绝（401/503）。

## 2026-03-07 01:35 - [后端 AI] - v4.2.2 30分钟线落数保障 & 跨日错标修复

**1. 完成了什么？**
- 修复了“凌晨/周末把上一交易日 Tick 误写成今天日期”的后端逻辑：`backend/app/services/collector.py` 启动时不再无条件首轮拉取，且只在交易时段轮询。
- 修复了 30 分钟趋势接口的日期判定：`/api/history/trend` 改为使用 `MarketClock.get_display_date()`，避免非交易时段误把自然日当交易日。
- 强化 Windows 爬虫“无人查看也要落数”的保障链路：`backend/scripts/live_crawler_win.py` 新增交易时段周期性全量轮扫（默认 15 分钟）、收盘窗口失败重试、单股重试机制，减少“当天未打开页面导致缺日”的概率。
- 调整云端 ingest 写入策略：`backend/app/routers/ingest.py` 的 ticks 改为按 `symbol+date` 覆盖写入，避免全量快照重复累加；同时修复 snapshots 入库参数错误（原逻辑实际未正确落库）。

**2. 变更了契约吗？**
- 否。接口入参/出参保持不变，未修改 `03_DATA_CONTRACTS.md`。

**3. 接下来需要另一个 AI（前端）做什么？**
- 无强制改动。建议仅做一次联调验证：
  - 周末/凌晨打开「30分钟线」时，最后一个交易日应保持为真实交易日（不再出现“复制成今天”）。
  - 某只当天未打开页面的星标股，次日应仍有完整当日 30m 数据（若有空洞，请反馈具体 symbol+date 方便追日志）。

## 2026-03-07 00:15 - [全栈前端 AI] - v4.2.1 安全重构定档与交接准备

**1. 完成了什么？**
- 全面修复并重构了系统的 API Key 隔离安全逻辑。数据库已彻底区分为 `market_data.db`（行情层）和 `user_data.db`（用户配置层）。
- 已完成历史星标数据的横向萃取迁移。
- 对冗余文档进行了归档（移入 `docs/archive/`），确立了最新的 00 到 05 序号核心文档结构。
- Bump 版本号升级到了 `v4.2.1`。

**2. 变更了契约吗？**
- 是的，`03_DATA_CONTRACTS.md` 中针对 `app_config` 的内容进行了更新，LLM Api Key 不再进裤。新增了 `/api/watchlist` 的 DELETE 接口。

**3. 接下来需要另一个 AI（后端处理集群）做什么？**
- 人类开发者准备引入你，来接手更专业、深度的后端数据处理与 AI 脱机巡检总结等重构。
- 请你在接到下一次需求时，**务必先阅读 `docs/00_AI_HANDOFF_PROTOCOL.md`（我们的约法三章）**，并依据 `AI_HANDOFF_LOG.md` 继续开发。
- 有任何接口新增或底层数据字段修改，请**首先同步在 `03_DATA_CONTRACTS.md` 中**，让我（前端 AI）能看着契约改界面。期待与您的合作！
