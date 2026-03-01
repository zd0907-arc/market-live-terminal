# 01_SYSTEM_ARCHITECTURE (系统与架构基石)

> **核心定位**：定义系统的物理边界、数据流向大图、数据存储分层、以及那些绝对不能触碰的"架构红线"。所有 AI 在编写网络请求、部署脚本、架构决策前**必读**。

## 一、 系统角色与物理边界

本系统部署在三个物理隔离的环境中，分工明确，绝不可越界：

1. **司令部 (Mac 终端)**
   * **职责**：代码库的唯一修改地 (Push 节点)。开发前端页面、后端接口、调试爬虫都在此进行。
   * **数据**：通过 `sync_cloud_db.sh` 从云端整库下载 `data/market_data.db`，**只读不写**。
   * **红线**：决不允许长期后台跑爬虫任务，仅用作开发机和 SSH 主控机。
   
2. **侦察机 / 算力节点 (家庭 Windows - 内网 IP: 100.115.228.56)**
   * **职责**：唯一具备从外部（东方财富/AkShare）高频抓取数据资格的节点。负责实时数据抓取（白天的雷达）、历史海量数据 ETL 清洗，并负责将洗净的数据 **单向 POST/SCP 发送** 到云端。
   * **产出物**：`market_data_history.db`（ETL 历史聚合库，仅含 `local_history` + `history_30m`）
   * **红线**：**不要在 Windows 节点配置完整的 Git 仓库环境去执行 Pull**。它的代码完全是由 Mac 节点通过 `sync_to_windows.sh` 覆写进去的。

3. **指挥中心 (腾讯云 Ubuntu - 公网 IP: 111.229.144.202)**
   * **职责**：运行 FastAPI 后端和 SQLite 数据库，承担前端界面的数据下发（`npm run build` 资产和 API 服务）。是所有数据的 **唯一权威源 (Single Source of Truth)**。
   * **数据库**：`data/market_data.db`（Docker 挂载 `../data:/app/data`），包含全量生产数据。
   * **致命红线**：**云端绝对禁止向东方财富、AkShare 等外部行情接口发出一丝一毫的 HTTP 请求**。它的 IP 已被东财永久封禁，一旦代码让云端去外网拉数据，系统直接罢工。云端只能被动提供 `/api/internal/ingest` 高清接口供 Windows 喂养数据。

## 二、 核心数据流转架构 (Data Flow)

整个项目的数据是**单向流动**的（从外网 -> Windows -> 腾讯云 -> 前端视图）。

### 流水线 A：盘中实时流 (The Live Pipeline)
1. **获取源头**：Windows `live_crawler_win.py` 每 3 秒从 AkShare 拉取一次盘口快照，每 3 分钟拉取一次最新交易逐笔。
2. **射向云端**：Windows 把原始的 List/Dict 转为 JSON，通过 HTTP POST 传给腾讯云服务器 (`/api/internal/ingest/*` 接口，带 `INGEST_TOKEN` 鉴权)。
3. **入库展示**：腾讯云 FastAPI 接到数据，验证 Token 后直接 Insert/Replace 到云端的 `data/market_data.db` 中。前端用户刷手机，瞬间看到最新 K 线。

> **[架构澄清] 本地 Tick 存储与容量**：
> 系统作为“精细化 Watchlist”（约 50 只核心股票）而非全市场雷达。每天产生的有效 Tick 约 20万-40万行，落入 SQLite 仅 20MB-30MB。存满一年不到 10GB。
> **【20GB 云盘预警备注】**：虽然单只股票存全量 Tick 一年不到 200MB，但考虑到腾讯云服务器总硬盘只有 20GB，未来如果自选股池大规模扩张，可能会触碰存储瓶颈。目前暂不做任何删减逻辑，后续再制定应对方案。

### 流水线 B：历史数据的离线大一统 (The Historical ETL)
1. **下载与解压**：人工在 Windows 上下载并解压几十上百 G 的 L2 CSV/ZIP 包到 `D:\MarketData`。
2. **多核聚合清洗**：Windows `etl_worker_win.py` 利用多核计算，把 GB 级别的大单数据过滤求和，仅抽取出包含"大单、超大单买卖金额"的高浓度 SQLite 数据表，产出 `market_data_history.db`。
3. **隔空注射**：Mac 作为总控，通过 SCP 把洗完的 `.db` 文件传到腾讯云，并使用 `merge_historical_db.py`（delete-then-insert 策略）合并到云端生产库。

### 流水线 C：历史日线聚合与无级拼接 (The Historical & Realtime Splicing)
1. **历史回补能力**：当一档新股票加入星标时，**不需要**从零补齐它过去几个月的全量 Ticks。后端 (`get_sina_money_flow`) 直接调用新浪隐藏 API (`MoneyFlow.ssl_qsfx_lscjfb`)，瞬间获取过去 100 个交易日已算好的全套资金流向指标 (大单/超大单/净流入等)。
2. **今日数据热插拔拼接**：新浪历史接口在盘中是**滞后**的（不含“今天”）。因此，在 `/api/analysis/history_analysis` 中，系统会先拉取 100 天历史底表，然后**当场从云端 `trade_ticks` (ODS) 将今日已发生的 Ticks 聚合为一根完整日线**，硬接在 100 天最后面，实现对前端的“无缝拼接”。

### 流水线 D：本地开发同步 (Dev Sync)
1. Mac 执行 `sync_cloud_db.sh`，通过 SCP 将云端 `data/market_data.db` 完整下载到本地 `data/` 目录。
2. 本地 backend 启动后自动读取 `data/market_data.db`，获得与云端一致的完整数据。

## 三、 数据存储层级 (Data Storage Hierarchy)

所有数据存储在单一 SQLite 数据库 `data/market_data.db` 中，按职责分为三层（详见 `03_DATA_CONTRACTS.md`）：

| 层级 | 表 | 特征 |
|------|-----|------|
| **Raw（原始层）** | `trade_ticks`, `sentiment_snapshots`, `sentiment_comments` | 只追加永不删，源数据 |
| **Derived（派生层）** | `local_history`, `history_30m`, `sentiment_summaries` | 可重算可覆写，带版本号 |
| **Config（配置层）** | `watchlist`, `app_config` | 用户直接操作 |

### 数据一致性原则
* **云端**：唯一权威源。Windows 实时 POST + ETL merge 写入。
* **Mac 本地**：`sync_cloud_db.sh` 整库下载的只读副本。
* **Windows**：只产出 `market_data_history.db`，不持有完整服务库。

## 四、 环境变量与配置依赖 (.env Blueprint)
系统启动必须依赖以下环境配置（不可在代码中硬编码）：

*   `DB_PATH`: SQLite 文件的绝对路径。如果不传，默认为 `data/market_data.db`。
*   `MOCK_DATA_DATE`: 字符串 (如 `"2026-02-12"`)。非空时，后端所有当天数据的接口将欺骗前端，假装今天是该日期（由于开发通常在周末或晚上进行）。
*   `CLOUD_API_URL`: Windows 节点专用的环境变量，指示它往哪里发数据 (如 `http://111.229.144.202:8000`)。
*   `INGEST_TOKEN`: 控制云端高速穿透接口权限的秘钥，云端和 Windows 节点必须完全对齐。
