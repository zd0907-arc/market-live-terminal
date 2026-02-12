# 金融实时终端 (v2.0)

> **AI 上下文元数据**
> *   **角色**: 金融数据终端 (实时 & 历史)
> *   **技术栈**: React 19 (前端) + FastAPI (后端) + SQLite
> *   **核心逻辑**: 资金流向分析 (主力资金计算)
> *   **状态**: 生产就绪 (v2.0)

## 1. 项目概览

本项目是一个**前后端分离**的金融数据监控终端，核心功能是实时监控 A 股市场的主力资金流向，并提供历史博弈分析。

*   **前端 (Frontend)**: 提供实时逐笔交易监控、主力资金动态图表、历史数据回溯分析。
*   **后端 (Backend)**: 负责数据持久化（SQLite）、后台自动采集（AkShare/Crawler）、复杂聚合计算。

**v2.0 关键更新**:
- **前端重构**: 标准化 `src/` 目录结构。
- **后端优化**: 全面异步化 (Async/Await + HTTPX)，提升并发性能。

---

## 2. 技术架构 (Architecture)

### 目录结构

```text
market-live-terminal/
├── src/                  # 前端源代码
│   ├── components/       # React 组件
│   │   ├── common/       # 通用组件 (ConfigModal, DataSourceControl)
│   │   └── dashboard/    # 功能视图 (HistoryView, RealtimeView)
│   ├── services/         # 前端 API 服务
│   ├── utils/            # 通用工具 (calculator.ts)
│   ├── App.tsx           # 主布局
│   └── main.tsx          # 入口文件
├── backend/              # 后端应用 (Python)
│   └── app/
│       ├── main.py       # FastAPI 入口
│       ├── db/           # 数据库层 (SQLite + CRUD)
│       ├── services/     # 业务逻辑 (Async Collector, Market)
│       ├── routers/      # 异步 API 路由
│       └── models/       # Pydantic 模型
└── README.md
```

### 数据流向 (Data Flow)

1.  **实时模式 (Realtime Mode)**:
    *   前端 -> `StockService.fetchTicks()` -> 后端 `/api/ticks_full` -> AkShare/DB
    *   前端 -> `calculator.ts` -> 聚合逐笔数据 -> 渲染图表
    *   *注*: 阈值配置在加载时从后端 `/api/config` 获取。

2.  **历史模式 (History Mode)**:
    *   前端 -> `StockService.fetchHistoryAnalysis()` -> 后端 `/api/history_analysis`
    *   后端 -> `services.analysis` -> `local_history` (数据表) -> 返回 JSON

---

## 3. 核心业务逻辑 (Business Logic)

### 主力资金计算公式

**计算公式**:
*   **主力 (Main Force)**: 单笔成交额 >= `大单阈值 (Large Threshold)`
*   **净流入 (Net Inflow)**: `主力买入额` - `主力卖出额`
*   **活跃度 (Activity Ratio)**: `(主力买入额 + 主力卖出额) / 总成交额`

**阈值配置**:
*   **数据源**: 后端数据库 (`app_config` 表)。
*   **默认值**:
    *   `large_threshold`: **200,000** (20万) - 用于主力资金计算。
    *   `super_large_threshold`: **1,000,000** (100万) - 用于界面高亮显示 (紫色星号)。

---

## 4. 开发指南 (Development Guide)

### 环境要求
*   Node.js 18+
*   Python 3.9+

### 启动步骤

1.  **后端 (Backend)**:
    ```bash
    # 安装依赖
    pip install -r backend/requirements.txt
    
    # 启动服务器 (端口 8000)
    python -m backend.app.main
    ```

2.  **前端 (Frontend)**:
    ```bash
    # 安装依赖
    npm install
    
    # 启动开发服务器 (端口 3001)
    npm run dev
    ```

### 常用命令
*   `python -m backend.app.main`: 启动后端服务
*   `npm run dev`: 启动前端服务

---

## 5. API 接口参考 (API Reference)

*   `GET /api/config`: 获取前端计算用的公共阈值配置。
*   `GET /api/ticks_full?symbol=sh600519`: 获取某只股票的全天逐笔交易数据。
*   `POST /api/aggregate`: 触发某只股票的历史数据手动聚合计算。

---

## 6. 版本管理 (Version Management)

### 分支策略
*   **`main`**: 生产环境代码 (稳定版)。
*   **`develop`**: 主开发分支。
*   **`feature/*`**: 功能特性分支 (例如 `feature/v2.1-optimization`)。

### 版本规范
*   前端版本定义在 `package.json` 和 `src/version.ts` 中。
*   当前版本: **v2.2.0**

### 更新日志 (Release Notes)

#### v2.2.0
*   **Feature**: 新增“情绪仪表盘” (Sentiment Dashboard)，接入腾讯快照数据，实时展示内外盘（主动买卖）与委比（挂单）博弈。
*   **Optimization**: 实时页面刷新频率优化，支持 1m/5m/15m/30m 切换，默认 5m，大幅降低数据拉取压力。
*   **Fix**: 修复腾讯接口超时问题（3s -> 10s），解决部分网络环境下数据缺失的问题。

#### v2.1.0
*   **Feature**: 新增“超大单占比”指标 (Super Large Ratio)，用于捕捉主力核心动向。
*   **UI**: 优化顶部搜索框布局，增加宽度并居中显示。
*   **Logic**: 修正活跃度算法逻辑，增加对超大单的独立监控。
