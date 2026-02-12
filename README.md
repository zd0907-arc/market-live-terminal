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
*   当前版本: **v2.6.0**

### 更新日志 (Release Notes)

#### v2.6.0
*   **Feature**: 新增微观博弈指标监控系统，支持**冰山压单** (Iceberg)、**虚假撤单** (Spoofing)、**量价背离** (Divergence) 三大主力操盘手法的实时检测与报警。
*   **UI/UX**: 深度优化 CVD 资金博弈图表，支持在图表时间轴上直接打点显示报警信号 (🧊/👻/⚠️)，并提供详细的悬停“侦探报告”。
*   **Education**: 新增“联合研判决策矩阵”说明，帮助用户通过 CVD 与 OIB 的组合形态快速判断真突破、假支撑与吸筹行为。
*   **Fix**: 修复日线统计图中“主力净流入”图例颜色丢失问题，优化历史页面标题 UI。

#### v2.5.0
*   **UI/UX**: 实施全界面极致紧凑化重构，顶部行情栏高度减半，采用左右三段式高效布局。
*   **I18n**: 完成全站中文化 (Vol->成交, Amt->金额, etc.)，更符合中文用户使用习惯。
*   **Feature**: 新增“资金博弈分析”模块解释浮窗，为 CVD (实战博弈) 和 OIB (潜在意愿) 提供详细业务逻辑说明。
*   **Optimization**: 优化仪表盘分栏比例，图表区域更宽阔，逐笔数据区更精简。

#### v2.4.0
*   **Performance**: 实施后端实时聚合 (Server-Side Aggregation)，将数万条逐笔数据的计算压力从前端移至后端，页面加载速度提升 100倍+。
*   **Feature**: 新增全局动态配置入口 (Header区域)，支持实时调整“主力大单”和“超大单”阈值，无需重启服务。
*   **Fix**: 修复收盘后数据异常问题，增加 15:05 硬性熔断机制与脏数据过滤，确保 K 线图尾盘准确。
*   **Refactor**: 统一前后端核心算法，移除前端冗余计算逻辑，保证历史回测与实时监控数据的一致性。

#### v2.3.0
*   **Feature**: 新增“主力累计资金”趋势图，通过红绿面积图直观展示全天资金净流入/流出趋势。
*   **Feature**: 实时监控中分离“主力整体”（>20万）与“超大单”（>100万）资金流向，支持双轴联动分析。
*   **UI**: 优化图表视觉体验，支持红绿分色填充与多维度资金曲线对比。

#### v2.2.2
*   **Refactor**: 重构主力动态数据采集架构。后台每3分钟自动轮询采集全量逐笔数据并持久化到本地 SQLite 数据库。
*   **Performance**: 前端读取本地数据库实现秒级加载，彻底解决数据拉取慢、卡顿的问题。
*   **Optimization**: 增加数据自动同步机制，前端实时展示数据更新时间。

#### v2.2.1
*   **Optimization**: 优化多空情绪仪表盘的数据持久化，支持本地 SQLite 存储，防止数据断层。
*   **Backend**: 新增 `SentimentMonitor` 后台服务，实现 3秒/次 的高频数据录制。

#### v2.2.0
*   **Feature**: 新增“情绪仪表盘” (Sentiment Dashboard)，接入腾讯快照数据，实时展示内外盘（主动买卖）与委比（挂单）博弈。
*   **Optimization**: 实时页面刷新频率优化，支持 1m/5m/15m/30m 切换，默认 5m，大幅降低数据拉取压力。
*   **Fix**: 修复腾讯接口超时问题（3s -> 10s），解决部分网络环境下数据缺失的问题。

#### v2.1.0
*   **Feature**: 新增“超大单占比”指标 (Super Large Ratio)，用于捕捉主力核心动向。
*   **UI**: 优化顶部搜索框布局，增加宽度并居中显示。
*   **Logic**: 修正活跃度算法逻辑，增加对超大单的独立监控。
