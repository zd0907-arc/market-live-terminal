# ZhangData 系统架构与数据流全景图

> 📖 这份文档面向**人类读者**，用可视化方式展示系统的物理拓扑和数据流向。  
> AI 开发请查阅 `docs/01_SYSTEM_ARCHITECTURE.md`（严格规则版）和 `docs/03_DATA_CONTRACTS.md`（表结构契约版）。

---

## 🗺️ 物理拓扑

```mermaid
flowchart LR
    subgraph Internet["🌐 互联网 (数据源)"]
        AK["AkShare<br/>腾讯行情 API"]
        DF["东方财富<br/>L2 历史数据包"]
    end

    subgraph Win["🖥️ Windows 算力节点<br/>192.168.3.108 / 100.115.228.56"]
        LC["live_crawler_win.py<br/>实时爬虫 (3s/3min)"]
        ETL["etl_worker_win.py<br/>历史 ETL (多核)"]
        HDB[("market_data_history.db<br/>ETL 产出")]
    end

    subgraph Cloud["☁️ 腾讯云 Ubuntu<br/>111.229.144.202"]
        API["FastAPI 后端<br/>Docker 容器"]
        CDB[("data/market_data.db<br/>1.67GB 生产全量库<br/>✅ 唯一权威源")]
        WEB["React 前端<br/>Nginx 静态托管"]
    end

    subgraph Mac["💻 Mac 司令部<br/>开发机 + SSH 总控"]
        DEV["代码开发<br/>Git Push"]
        MDB[("data/market_data.db<br/>只读副本")]
    end

    AK -- "盘口快照 + 逐笔" --> LC
    DF -- "GB级 ZIP 包" --> ETL
    ETL --> HDB
    LC -- "HTTP POST<br/>/ingest/{ticks,snapshots}" --> API
    HDB -- "SCP via Mac<br/>merge_historical_db.py" --> CDB
    API --> CDB
    CDB --> WEB
    CDB -- "sync_cloud_db.sh<br/>rsync 增量同步" --> MDB
    DEV -- "deploy_to_cloud.sh<br/>Git + Docker Rebuild" --> Cloud
    DEV -- "sync_to_windows.sh<br/>SCP 覆写代码" --> Win
```

---

## 📊 数据库三层结构

```mermaid
block-beta
    columns 3
    
    block:raw:3
        columns 3
        r["🟢 Raw 原始层 — 只追加，永不删改"]
        trade_ticks["trade_ticks<br/>逐笔交易 (十亿级)"]
        sentiment_snapshots["sentiment_snapshots<br/>3秒盘口快照"]
        sentiment_comments["sentiment_comments<br/>股吧评论"]
    end

    block:derived:3
        columns 3
        d["🔵 Derived 派生层 — 可重算，带版本号"]
        local_history["local_history<br/>日级主力资金<br/>(config_signature)"]
        history_30m["history_30m<br/>30分钟K线聚合"]
        sentiment_summaries["sentiment_summaries<br/>AI 情绪摘要"]
    end

    block:config:3
        columns 2
        c["⚙️ Config 配置层 — 用户直接操作"]
        watchlist["watchlist<br/>自选股列表"]
        app_config["app_config<br/>阈值配置<br/>(LLM配置已迁至环境变量)"]
    end
```

---

## 🔄 两条数据流水线

### 流水线 A：盘中实时流（每个交易日 9:15 ~ 15:05）

```mermaid
sequenceDiagram
    participant AK as AkShare / 腾讯API
    participant Win as Windows 爬虫
    participant Cloud as 云端 FastAPI
    participant DB as market_data.db
    participant User as 手机/浏览器

    loop 每 3 秒
        Win->>AK: 拉盘口快照
        Win->>Cloud: POST /ingest/snapshots
        Cloud->>DB: INSERT sentiment_snapshots
    end
    
    loop 每 3 分钟
        Win->>AK: 拉逐笔交易
        Win->>Cloud: POST /ingest/ticks
        Cloud->>DB: INSERT trade_ticks + history_30m
    end

    User->>Cloud: 刷新页面
    Cloud->>DB: SELECT 聚合查询
    Cloud->>User: 返回实时 K 线 + 资金流
```

### 流水线 B：历史离线 ETL（不定期批处理）

```mermaid
sequenceDiagram
    participant Human as 操作人员
    participant Win as Windows
    participant Mac as Mac 总控
    participant Cloud as 云端

    Human->>Win: 下载 L2 数据包到 D:\MarketData
    Human->>Win: 启动 etl_autorun.bat
    Win->>Win: 多核 ETL → market_data_history.db
    
    Mac->>Win: SCP 拉取 history.db
    Mac->>Cloud: SCP 上传 history.db + merge 脚本
    Mac->>Cloud: 执行 merge (delete-then-insert)
    Cloud->>Cloud: market_data.db 更新完成
```

---

## 🔑 关键脚本速查

| 脚本 | 在哪运行 | 做什么 |
|------|---------|--------|
| `live_crawler_win.py` | Windows | 盘中实时抓取，POST 到云端 |
| `etl_worker_win.py` | Windows | L2 历史数据 ETL，产出 history.db |
| `etl_autorun.bat` | Windows | ETL 自动重试运行容器 |
| `merge_historical_db.py` | 云端 | 将 history.db 合并到生产库 |
| `sync_cloud_db.sh` | Mac | rsync 增量同步云端生产库到本地 |
| `sync_to_windows.sh` | Mac | 将代码 SCP 到 Windows |
| `deploy_to_cloud.sh` | Mac | Git pull + Docker 重建部署 |

---

## ⚠️ 三条致命红线

1. **云端不能外网抓数据** — IP 已被东财永久封禁，只能被动接收 Windows 喂的数据
2. **Windows 不跑 Git** — 代码靠 Mac `sync_to_windows.sh` 覆写，不要在 Win 上 pull/push
3. **Mac 不长期跑爬虫** — 仅用于开发和 SSH 总控，数据全靠 `sync_cloud_db.sh` 从云端拉

---

## 🔐 安全配置

| 文件 | 用途 | 注意事项 |
|------|------|----------|
| `deploy/.env` | 云端 LLM Key | 手动创建，不入 Git |
| `.env.local` | 本地开发 Key | `.gitignore` + `.cursorignore` 双重屏蔽 |
| `.cursorignore` | AI 工具屏蔽 | 阻止 Cursor 等扫描敏感文件 |

> 详细 Key 维护指南见 `docs/05_LLM_KEY_SECURITY.md`

---

*最后更新：2026-03-06*
