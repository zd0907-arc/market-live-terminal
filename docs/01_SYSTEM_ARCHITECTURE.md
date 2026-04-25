# 01_SYSTEM_ARCHITECTURE (系统与架构基石)

> **核心定位**：定义系统的物理边界、数据流向大图、数据存储分层、以及那些绝对不能触碰的"架构红线"。所有 AI 在编写网络请求、部署脚本、架构决策前**必读**。
>
> **边界提醒**：本文件只裁决“组件职责/数据流/部署边界”；业务规则与验收标准统一在 `docs/02_BUSINESS_DOMAIN.md`，接口字段约束统一在 `docs/03_DATA_CONTRACTS.md`，执行步骤统一在 `docs/04_OPS_AND_DEV.md`。
>
> **当前真相提醒（2026-04-24）**：当前正式架构已收口为 **Windows 数据主站 / Mac 本地研究站 / Cloud 轻量盯盘**。本文件下半段仍保留少量早期演化背景，但当前判断一律先以本文件前 3 节 + `docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md` 为准。

## 一、 系统角色与物理边界

本系统部署在三个物理隔离环境中，当前职责冻结如下：

1. **司令部 (Mac 终端)**
   * **职责**：代码库唯一修改地；运行本地前后端；承接复盘、选股、策略研究、文档治理。
   * **本地正式数据**：从 Windows 同步处理后正式库到本机，主路径为：
     - `data/market_data.db`
     - `data/atomic_facts/market_atomic_mainboard_full_reverse.db`
     - `data/selection/selection_research.db`
     - `data/user_data.db`
   * **红线**：
     - 不长期跑外采爬虫；
     - 不跨网络直接查询 Windows sqlite 主库；
     - 不把 Mac 当成 cloud 生产替身。
   
2. **侦察机 / 算力节点 (家庭 Windows - 内网 IP: 100.115.228.56)**
   * **职责**：唯一外采节点与正式跑数工厂。负责：
     - 盘中实时抓取；
     - 盘后 L2 / atomic / selection 跑数；
     - 处理后正式库与日增量产出；
     - 向 Cloud 喂轻量盯盘数据、向 Mac 同步研究所需正式库。
   * **路径约定**：统一运行目录 `D:\market-live-terminal`。
   * **产出物**：
     - raw 原始包
     - `market_data.db`
     - atomic 主库
     - selection 研究库
     - Mac 所需日增量 / 全量同步产物
   * **红线**：
     - 不在 Windows 上做 Git 主仓日常开发；
     - 不把 Windows 当作文档主编辑区；
     - 不让未验真的中间产物直接替代正式库。

3. **指挥中心 (腾讯云 Ubuntu - 公网 IP: 111.229.144.202)**
   * **职责**：提供轻量盯盘 / 手机应急查看；接收 Windows 的 ingest；承接前端静态资源和轻量 API。
   * **数据库**：`data/market_data.db`（轻量盯盘链路所需数据），**不再承担 full atomic / selection 研究主查询职责**。
   * **致命红线**：
     - 云端绝对禁止直接向东财 / AkShare 等外部行情源主动外采；
     - 云端不是 full atomic 中转站；
     - 不把研究型重查询默认压到云端。

## 二、 核心数据流转架构 (Data Flow)

当前主线数据流是**双下游单主站**：外网 -> Windows -> {Cloud 轻量盯盘, Mac 本地研究站}。

### 流水线 A：盘中实时流 (The Live Pipeline)
1. **前端声明活跃**：线上 / 本地前端打开盯盘页后，通过 `/api/monitor/heartbeat` 上报当前股票和 focus/warm 状态；云端 `/api/monitor/active_symbols` 聚合活跃股票。
2. **Windows 统一外采**：Windows 计划任务 `ZhangDataLiveCrawler` 启动 `backend/scripts/live_crawler_win.py`，读取云端 `/api/watchlist` 与 `/api/monitor/active_symbols`，再从腾讯行情 / AkShare 拉盘口快照和逐笔。
3. **射向云端**：Windows 只通过 HTTP POST 写 Cloud：`/api/internal/ingest/snapshots`、`/api/internal/ingest/ticks`，必须携带 `INGEST_TOKEN`。
4. **云端被动入库**：Cloud 写入轻量 `data/market_data.db` 的 `sentiment_snapshots`、`trade_ticks`、`history_30m` 等盯盘所需表。云端默认 `ENABLE_CLOUD_COLLECTOR=false`，不主动外采。
5. **页面读取**：线上盯盘页读取 Cloud API；Mac 本地盯盘页默认读取 Mac 本地 DB，必要时单票接口可按需补拉当日 ticks，但不等同于生产后台 crawler。

> **[架构澄清] 本地 Tick 存储与容量**：
> 系统作为“精细化 Watchlist”（约 50 只核心股票）而非全市场雷达。每天产生的有效 Tick 约 20万-40万行，落入 SQLite 仅 20MB-30MB。存满一年不到 10GB。
> **【20GB 云盘预警备注】**：虽然单只股票存全量 Tick 一年不到 200MB，但考虑到腾讯云服务器总硬盘只有 20GB，未来如果自选股池大规模扩张，可能会触碰存储瓶颈。目前暂不做任何删减逻辑，后续再制定应对方案。

### 流水线 B：盘后正式跑数与研究库产出
1. **下载与解压**：人工在 Windows 上下载并解压几十上百 G 的 L2 CSV/ZIP 包到 `D:\MarketData`。
2. **正式处理**：Windows 运行盘后 L2、atomic、selection 脚本，生成：
   - 轻量盯盘所需更新；
   - `market_data.db`
   - atomic 主库；
   - selection 研究库；
   - Mac 所需日增量或整库同步产物。
3. **分发下游**：
   - 轻量结果送 Cloud；
   - 研究正式库同步到 Mac。

### 流水线 C：Mac 本地研究站消费
1. **首次全量同步**：Mac 从 Windows 同步处理后正式库，当前外置数据根目录优先使用 `/Users/dong/Desktop/AIGC/market-data`。
2. **日常增量同步**：每日盘后总控在 Windows 产生日增量后，同步到 Mac 本地正式库。Windows -> Mac 数据同步禁止 SSH/scp 直拉，只允许“局域网 HTTP relay / Cloud relay 中转”。
3. **本地服务消费**：Mac 本地后端通过 `ops/start_local_research_station.sh` 读取本机正式库，为复盘 / 选股 / 研究页面供数。
4. **本地实时语义**：Mac 本地默认不长期跑后台 crawler（`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`）；打开单票盯盘时，接口可触发按需补拉当日 ticks 并写入本地库。若要获得与线上完全一致的连续盘中体验，应以 Windows -> Cloud 生产实时链路为准。

### 流水线 D：兼容链路与过渡工具
1. `snapshot` 类工具仍可用于验证、裁剪样本或应急排查。
2. 但 `snapshot` 已不是当前正式主路径；正式主路径是 **Windows -> Mac 处理后正式库同步**。

## 三、 数据存储层级 (Data Storage Hierarchy)

当前主线不是“所有能力只围绕一个云端 SQLite 单库运行”，而是按节点分层：

| 节点 | 当前正式存储 | 用途 |
|------|------|------|
| **Windows** | raw 原始包 + `market_data.db` + atomic 主库 + selection 研究库 | 数据真相源 / 跑数主站 |
| **Mac** | `data/market_data.db` + `data/atomic_facts/...` + `data/selection/selection_research.db` + `data/user_data.db` | 本地研究站主消费 |
| **Cloud** | 轻量 `data/market_data.db` | 线上盯盘 / 应急访问 |

### 数据一致性原则
* **Windows**：当前数据主站与正式跑数真相源。
* **Mac 本地**：当前研究、复盘、选股主消费环境；读取同步后的处理后正式库。
* **Cloud**：轻量线上服务，不作为研究主查询真相源。

## 四、 环境变量与配置依赖 (.env Blueprint)
系统启动必须依赖以下环境配置（不可在代码中硬编码）：

### 基础配置
*   `DB_PATH`: SQLite 文件的绝对路径。如果不传，默认为 `data/market_data.db`。
*   `USER_DB_PATH`: 用户配置数据库路径。默认 `data/user_data.db`。
*   `MOCK_DATA_DATE`: 字符串 (如 `"2026-02-12"`)。非空时，后端所有当天数据的接口将欺骗前端，假装今天是该日期（由于开发通常在周末或晚上进行）。
*   `CLOUD_API_URL`: Windows 节点专用的环境变量，指示它往哪里发数据 (如 `http://111.229.144.202`，由 Nginx 反代到后端)。
*   `INGEST_TOKEN`: 控制云端高速穿透接口权限的秘钥，云端和 Windows 节点必须完全对齐（无默认值，未配置即拒绝写入）。
*   `WRITE_API_TOKEN`: 保护业务写接口（如 watchlist/config/sentiment 手动触发）的共享秘钥；**只允许保留在服务端环境变量中**。官方前端通过 Vite/Nginx 代理在服务端侧注入 `X-Write-Token`，浏览器端不得直接持有该值。
*   `ENABLE_CLOUD_COLLECTOR`: 是否允许云端主动外采（默认 `false`，用于遵守“云端只被动 ingest”红线）。

### LLM 大模型配置（🔴 仅通过服务端环境变量）
> **安全红线**：以下配置**绝对禁止**存入数据库、前端代码或 Git 仓库。云端通过宿主机环境变量 → Docker Compose 透传。本地通过 `.env.local` 文件（已被 `.gitignore` 和 `.cursorignore` 隔离）。

*   `LLM_BASE_URL`: 大模型 API 基地址（如 `https://dashscope.aliyuncs.com/compatible-mode/v1`）。
*   `LLM_API_KEY`: 大模型 API Key（如通义千问的 `sk-xxx`）。**绝不出现在任何代码或数据库中。**
*   `LLM_MODEL`: 模型名称（如 `qwen3-max`）。
*   `LLM_PROXY`: 代理地址，留空则直连。
