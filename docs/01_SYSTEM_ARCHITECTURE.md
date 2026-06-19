# 01_SYSTEM_ARCHITECTURE (系统与架构基石)

> **核心定位**：定义系统的物理边界、数据流向大图、数据存储分层、以及那些绝对不能触碰的"架构红线"。所有 AI 在编写网络请求、部署脚本、架构决策前**必读**。
>
> **边界提醒**：本文件只裁决“组件职责/数据流/部署边界”；业务规则与验收标准统一在 `docs/02_BUSINESS_DOMAIN.md`，接口字段约束统一在 `docs/03_DATA_CONTRACTS.md`，执行步骤统一在 `docs/04_OPS_AND_DEV.md`。
>
> **当前真相提醒（2026-06-06）**：当前正式架构已收口为 **Windows 数据主站 / Mac 开发与本地研究控制台 / NAS 在线运行节点**。旧 `Cloud` 叙事只按历史阶段理解；当前在线服务、`research/current` 发布与公网收口都以 NAS 线为准。本文件下半段仍保留少量早期演化背景，但当前判断一律先以本文件前 3 节 + `docs/archive/changes/MOD-20260606-02-project-governance-master-plan.md` 为准。

## 一、 系统角色与物理边界

本系统部署在三个物理隔离环境中，当前职责冻结如下：

1. **司令部 (Mac 终端)**
   * **职责**：代码库唯一修改地；运行本地前后端；承接复盘、选股、策略研究、文档治理。
   * **本地正式数据**：从 Windows 同步处理后正式库到本机，主路径为：
     - `market-data/live/market_data.db`（轻量盯盘消费库）
     - `market-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db`（盘后明细底座，Mac 主读正式名）
     - `market-data/research/current/selection/selection_research.db`（每日选股研究库，Mac 主读正式名）
     - `market-data/research/current/selection/model_feature_store.db`（模型训练特征库，Mac 主读正式名）
     - `market-data/live/user_data.db`
   * **补充说明**：当前 `market-data` 根目录旧兼容入口已经删除；默认口径直接固定为 `live/` 与 `research/current/`。
   * **红线**：
     - 不长期跑外采爬虫；
     - 不跨网络直接查询 Windows sqlite 主库；
     - 不把 Mac 当成 cloud 生产替身。
   
2. **侦察机 / 算力节点 (家庭 Windows - 内网 IP: 100.115.228.56)**
   * **职责**：唯一外采节点与正式跑数工厂。负责：
     - 盘中实时抓取；
     - 盘后 L2 / 明细底座 / 选股研究 / 模型特征 跑数；
     - 处理后正式库与日增量产出；
     - 向 Cloud 喂轻量盯盘数据、向 Mac 同步研究所需正式库。
   * **路径约定**：统一运行目录 `D:\market-live-terminal`。
   * **产出物**：
     - raw 原始包
     - `market_data.db`
     - `atomic_compact_main`（当前按 `data/atomic_facts/market_atomic_mainboard_compact_current.db` 理解；旧 `compact_smoke_*` 已退休）
     - `selection_research_main`（当前按 `data/selection/selection_research.db` 理解；旧 `selection_research_windows.db` 已退休）
     - `model_feature_store_main`（当前按 `data/selection/model_feature_store.db` 理解；旧 `model_feature_store_smoke_*` 已退休）
     - Mac 所需日增量 / 全量同步产物
   * **红线**：
     - 不在 Windows 上做 Git 主仓日常开发；
     - 不把 Windows 当作文档主编辑区；
     - 不让未验真的中间产物直接替代正式库。

3. **在线服务节点 (家庭 NAS - `dxp4800pro`)**
   * **职责**：承接当前线上前后端、NAS `research/current` 正式查询口径、发布/回滚链，以及后续公网域名收口。
   * **数据库与目录口径**：
     - `live/market_data.db`（在线轻量盯盘库）
     - `research/current/atomic_facts/*`
     - `research/current/selection/*`
     - `research/current/market_heat/*`
   * **当前事实**：
     - NAS 查询主链已经切到 `LIVE_DATA_ROOT=/runtime-data/live` 与 `RESEARCH_CURRENT_ROOT=/runtime-data/research/current`
     - NAS crawler 容器已跑通 ingest 验证，但 Windows `ZhangDataLiveCrawler` 还未正式下线；当前处于观察期
   * **致命红线**：
     - 不把 repo 内 `data/*` 误当 NAS 正式数据根；
     - 不把 bootstrap current 误记成“已长期追平本地正式库”的最终状态；
     - 不在未完成观察期前下线 Windows 盘中 crawler。

4. **影子 / 样本对象的边界说明**
   * `backend/sample_data/shadow/market.db`、`backend/sample_data/shadow/market_data.db`、`backend/sample_data/examples/market_data_sample.db` 只作为 shadow / sample / 排障对象存在，不承担正式主链职责。
   * 这类对象的存在只用于排障、样本验证和局部兼容，不代表它们是正式架构中的主存储层。

## 二、 核心数据流转架构 (Data Flow)

当前主线数据流是**双下游单主站**：外网 -> Windows -> {NAS 在线轻量盯盘, Mac 本地研究站}。

### 流水线 A：盘中实时流 (The Live Pipeline)
1. **前端声明活跃**：线上 / 本地前端打开盯盘页后，通过 `/api/monitor/heartbeat` 上报当前股票和 focus/warm 状态；线上 `active_symbols` 当前由 NAS 后端聚合。
2. **统一外采主源**：正式生产外采仍以 Windows `ZhangDataLiveCrawler` 为基线；NAS crawler 容器已完成在线跑通验证，但在连续观察期通过前，Windows 盘中 crawler 暂不下线。
3. **写入在线节点**：生产 ingest 目标当前应理解为 NAS 在线后端的 `/api/internal/ingest/snapshots`、`/api/internal/ingest/ticks`，必须携带 `INGEST_TOKEN`。
4. **在线节点被动入库**：NAS 写入 `live/market_data.db` 的 `sentiment_snapshots`、`trade_ticks`、`history_30m` 等盯盘所需表。默认 `ENABLE_CLOUD_COLLECTOR=false`，不主动外采。
5. **页面读取**：线上盯盘页读取 NAS API；Mac 本地盯盘页默认读取 Mac 本地 DB，必要时单票接口可按需补拉当日 ticks，但不等同于生产后台 crawler。

> **[架构澄清] 本地 Tick 存储与容量**：
> 系统作为“精细化 Watchlist”（约 50 只核心股票）而非全市场雷达。每天产生的有效 Tick 约 20万-40万行，落入 SQLite 仅 20MB-30MB。存满一年不到 10GB。
> **【20GB 云盘预警备注】**：虽然单只股票存全量 Tick 一年不到 200MB，但考虑到腾讯云服务器总硬盘只有 20GB，未来如果自选股池大规模扩张，可能会触碰存储瓶颈。目前暂不做任何删减逻辑，后续再制定应对方案。

### 流水线 B：盘后正式跑数与研究库产出
1. **下载与解压**：人工在 Windows 上下载并解压几十上百 G 的 L2 CSV/ZIP 包到 `D:\MarketData`。
2. **正式处理**：Windows 运行盘后正式主链，生成：
   - 轻量盯盘所需更新；
   - `market_data.db`（轻量盯盘消费库 / 旧兼容主链对象）
   - `atomic_compact_main`（盘后明细底座）
   - `selection_research_main`（每日选股研究库）
   - `model_feature_store_main`（模型训练特征库）
   - Mac 所需日增量或整库同步产物。
3. **分发下游**：
   - 轻量结果送 NAS `live/`；
   - 研究正式库同步到 Mac。

### 流水线 C：Mac 本地研究站消费
1. **首次全量同步**：Mac 从 Windows 同步处理后正式库，当前外置数据根目录优先使用 `/Users/dong/ZhangData/market-data`。
2. **日常增量同步**：每日盘后总控在 Windows 产生日增量后，同步到 Mac 本地正式库。当前正式入口是 `ops/run_daily_new_framework.sh --json --sync-nas`；该口径会在 Mac 校验通过后同步 NAS 生产 `live` 增量和市场水位目录。整套 `research/current` 大体量发布和 NAS 数据库快照都保留为单独动作。
3. **本地服务消费**：Mac 本地后端通过 `ops/start_local_research_station.sh` 读取本机正式库，为复盘 / 选股 / 研究页面供数。
4. **本地实时语义**：Mac 本地默认不长期跑后台 crawler（`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`）；打开单票盯盘时，接口可触发按需补拉当日 ticks 并写入本地库。若要获得与线上完全一致的连续盘中体验，应以 Windows/NAS 线上 realtime 链路为准。

### 流水线 D：兼容链路与过渡工具
1. `snapshot` 类工具仍可用于验证、裁剪样本或应急排查。
2. 但 `snapshot` 已不是当前正式主路径；正式主路径是 **Windows -> Mac 处理后正式库同步**。

## 三、 数据存储层级 (Data Storage Hierarchy)

当前主线不是“所有能力只围绕一个云端 SQLite 单库运行”，而是按节点分层：

| 节点 | 当前正式存储 | 用途 |
|------|------|------|
| **Windows** | raw 原始包 + `market_data.db` + `atomic_compact_main` + `selection_research_main` + `model_feature_store_main` | 数据真相源 / 跑数主站 |
| **Mac** | `market-data/live/market_data.db` + `market-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db` + `market-data/research/current/selection/selection_research.db` + `market-data/research/current/selection/model_feature_store.db` + `market-data/live/user_data.db` | 本地研究站主消费 |
| **NAS** | `live/market_data.db` + `research/current/*` | 线上盯盘 / 在线查询 / 正式发布节点 |

### 数据一致性原则
* **Windows**：当前数据主站与正式跑数真相源。
* **Mac 本地**：当前研究、复盘、选股主消费环境；读取同步后的处理后正式库。
* **NAS**：当前在线运行节点；线上查询和 `research/current` 发布都以它为准，但它不是盘后重跑真相源。
* **一致性的含义**：三端一致不是目录镜像一致，而是同一业务功能能读到同一套正式结果。某一端多出来的目录，通常表示该端承担了额外职责，例如线上模型推理、发布产物、训练全量数据或历史兼容。
* **解释优先级**：讨论目录差异时，先说“它服务哪个业务功能、删掉会影响什么”，再给具体路径。
* **研究产物边界**：新研究、新模型、新回测的机器产物默认进入 `market-data/artifacts` 或 `market-data/runs`；代码仓只承接源代码、人读结论、说明文档、小型配置和必要样例。

## 四、 环境变量与配置依赖 (.env Blueprint)
系统启动必须依赖以下环境配置（不可在代码中硬编码）：

### 基础配置
*   `FORMAL_MARKET_DATA_ROOT`: 当前正式数据根；默认 `/Users/dong/ZhangData/market-data`（Mac）或 `/runtime-data`（NAS）。
*   `LIVE_DATA_ROOT`: 在线轻量库根目录；默认从 `FORMAL_MARKET_DATA_ROOT/live` 推导。
*   `RESEARCH_CURRENT_ROOT`: 正式研究库根目录；默认从 `FORMAL_MARKET_DATA_ROOT/research/current` 推导。
*   `ARTIFACTS_ROOT`: 模型、研究产物和页面 payload 的根目录；默认从 `FORMAL_MARKET_DATA_ROOT/artifacts` 推导。
*   `SELECTION_ARTIFACTS_ROOT`: 选股模型、策略和长期趋势产物目录；默认从 `ARTIFACTS_ROOT/selection` 推导。
*   `RESEARCH_PAYLOADS_ROOT`: 研究页静态 payload 的源产物目录；默认从 `ARTIFACTS_ROOT/research_payloads` 推导。
*   `RUNS_ROOT`: 跑数现场和中间包目录；默认从 `FORMAL_MARKET_DATA_ROOT/runs` 推导。
*   `DB_PATH`: SQLite 文件的绝对路径。如果不传，默认按 `LIVE_DATA_ROOT/market_data.db` 解释；repo `data/market_data.db` 只按兼容副本理解。
*   `USER_DB_PATH`: 用户配置数据库路径。默认按 `LIVE_DATA_ROOT/user_data.db` 解释；repo `data/user_data.db` 只按兼容副本理解。
*   `MOCK_DATA_DATE`: 字符串 (如 `"2026-02-12"`)。非空时，后端所有当天数据的接口将欺骗前端，假装今天是该日期（由于开发通常在周末或晚上进行）。
*   `CLOUD_API_URL`: Windows 节点专用的历史环境变量名，用于指示它往哪里发数据；当前正式默认 ingest 目标应理解为 NAS 后端 (如 `http://dxp4800pro:8080`)。
*   `INGEST_TOKEN`: 控制在线 ingest 接口权限的秘钥，目标后端与 Windows 节点必须完全对齐（无默认值，未配置即拒绝写入）。
*   `WRITE_API_TOKEN`: 保护业务写接口（如 watchlist/config/sentiment 手动触发）的共享秘钥；**只允许保留在服务端环境变量中**。官方前端通过 Vite/Nginx 代理在服务端侧注入 `X-Write-Token`，浏览器端不得直接持有该值。
*   `ENABLE_CLOUD_COLLECTOR`: 是否允许旧 Cloud 兼容环境主动外采（默认 `false`，用于遵守“兼容环境只被动 ingest”红线）。

### LLM 大模型配置（🔴 仅通过服务端环境变量）
> **安全红线**：以下配置**绝对禁止**存入数据库、前端代码或 Git 仓库。云端通过宿主机环境变量 → Docker Compose 透传。本地通过 `.env.local` 文件（已被 `.gitignore` 和 `.cursorignore` 隔离）。

*   `LLM_BASE_URL`: 大模型 API 基地址（如 `https://dashscope.aliyuncs.com/compatible-mode/v1`）。
*   `LLM_API_KEY`: 大模型 API Key（如通义千问的 `sk-xxx`）。**绝不出现在任何代码或数据库中。**
*   `LLM_MODEL`: 模型名称（如 `qwen3-max`）。
*   `LLM_PROXY`: 代理地址，留空则直连。
