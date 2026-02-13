# 系统设计与架构说明

## 1. 项目概览
**ZhangData 智能博弈监控系统** 是一个混合架构的金融数据终端，旨在突破浏览器纯前端无法获取历史资金细分数据的限制。通过结合 **React 前端** 与 **Python 后端**，本系统实现了：
- **实时监控**: 对 A 股市场资金流向的逐笔监控。
- **历史回溯**: 深入分析历史资金博弈数据（主力 vs 散户）。
- **跨域数据访问**: 使用 Python 作为代理网关，访问新浪、腾讯、东方财富等多个金融数据源。

## 2. 技术架构

### 2.1 前端 (表现层)
- **核心框架**: React 19, TypeScript, Vite.
- **UI 组件库**: Tailwind CSS, Recharts.
- **主要职责**:
  - **RealtimeView (实时视图)**: 渲染实时交易逐笔和资金流向图表。在前端利用共享逻辑计算核心指标。
  - **HistoryView (历史视图)**: 可视化从后端获取的历史趋势数据。
  - **核心逻辑**: 在 `src/utils/calculator.ts` 中实现了“主力资金”计算算法，确保与后端逻辑同构。

### 2.2 后端 (数据与逻辑层)
- **核心框架**: FastAPI (Python 3.9+).
- **并发模型**: AsyncIO + HTTPX (全异步非阻塞).
- **数据库**: SQLite (通过 SQLAlchemy ORM 管理).
- **主要职责**:
  - **数据代理**: 异步转发外部 API 请求，解决浏览器跨域 (CORS) 问题。
  - **数据持久化**: 存储历史分析结果和用户配置。
  - **复杂计算**: 执行每日资金流向汇总等重计算任务。
  - **单一事实来源 (Source of Truth)**: 管理核心配置阈值（如“大单”的定义）。

### 2.3 目录结构
```text
market-live-terminal/
├── src/                  # 前端源代码
│   ├── components/       # 前端组件
│   │   ├── dashboard/    # 功能视图 (Realtime, History)
│   │   └── ...
│   ├── utils/
│   │   └── calculator.ts # 前后端共享的资金流算法
│   └── App.tsx           # 主应用入口
├── backend/              # 后端应用
│   └── app/
│       ├── main.py       # 启动入口 (Port 8000)
│       ├── routers/      # 异步 API 路由接口
│       ├── services/     # 异步业务逻辑层
│       └── models/       # Pydantic 数据模型
└── docs/                 # 项目文档
```

## 3. 数据流向 (Data Flow)

### 3.1 实时数据 (Realtime)
1.  **采集**: `backend/app/services/monitor.py` 每 3 秒轮询腾讯 API。
2.  **处理**: 解析买一/卖一与成交量，计算微观博弈信号（冰山/撤单）。
3.  **存储**: 写入 SQLite `sentiment_snapshots` 表。
4.  **分发**: 前端轮询 `/api/monitor/dashboard` 获取最新状态。

### 3.2 历史分析 (History)
1.  **归档**: 每日收盘后，`scripts/finalize_data.py` 将逐笔数据聚合并存入 `local_history`。
2.  **查询**: 前端请求 `/api/history_analysis`，后端直接从 SQLite 返回聚合结果。

### 3.3 散户情绪 (Sentiment)
1.  **爬取**: `services/sentiment_crawler.py` 抓取股吧评论。
2.  **分析**: LLM 服务生成摘要，写入 `sentiment_summaries`。

