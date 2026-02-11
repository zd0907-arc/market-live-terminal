# Market Live Terminal (v2.0)

> **AI Context Metadata**
> *   **Role**: Financial Data Terminal (Realtime & History)
> *   **Stack**: React 19 (Frontend) + FastAPI (Backend) + SQLite
> *   **Key Logic**: Capital Flow Analysis (Main Force Calculation)
> *   **Status**: Production Ready (v2.0)

## 1. Project Overview (项目概览)

本项目是一个**前后端分离**的金融数据监控终端，核心功能是实时监控 A 股市场的主力资金流向，并提供历史博弈分析。

*   **Frontend**: 提供实时逐笔交易监控、主力资金动态图表、历史数据回溯分析。
*   **Backend**: 负责数据持久化（SQLite）、后台自动采集（AkShare/Crawler）、复杂聚合计算。

**v2.0 关键更新**:
- **前端重构**: 标准化 `src/` 目录结构。
- **后端优化**: 全面异步化 (Async/Await + HTTPX)，提升并发性能。

---

## 2. Architecture (架构地图)

### Directory Structure

```text
market-live-terminal/
├── src/                  # Frontend Source Code
│   ├── components/       # React Components
│   │   ├── common/       # Shared UI (ConfigModal, DataSourceControl)
│   │   └── dashboard/    # Feature Views
│   ├── services/         # Frontend API Services
│   ├── utils/            # Shared Utilities (calculator.ts)
│   ├── App.tsx           # Main Layout
│   └── main.tsx          # Entry Point
├── backend/              # Backend Application (Python)
│   └── app/
│       ├── main.py       # FastAPI Entry Point
│       ├── db/           # Database Layer (SQLite + CRUD)
│       ├── services/     # Business Logic (Async Collector, Market)
│       ├── routers/      # Async API Routes
│       └── models/       # Pydantic Schemas
└── README.md
```

### Data Flow (数据流)

1.  **Realtime Mode**:
    *   Frontend -> `StockService.fetchTicks()` -> Backend `/api/ticks_full` -> AkShare/DB
    *   Frontend -> `calculator.ts` -> Aggregate Ticks -> Render Charts
    *   *Note*: Thresholds are loaded from Backend `/api/config` on mount.

2.  **History Mode**:
    *   Frontend -> `StockService.fetchHistoryAnalysis()` -> Backend `/api/history_analysis`
    *   Backend -> `services.analysis` -> `local_history` (Table) -> Return JSON

---

## 3. Business Logic (核心业务逻辑)

### Capital Flow Calculation (主力资金计算)

**Formula**:
*   **Main Force (主力)**: Transaction Amount >= `Large Threshold`
*   **Net Inflow**: `Main Buy Amount` - `Main Sell Amount`
*   **Activity Ratio**: `(Main Buy + Main Sell) / Total Volume`

**Thresholds (阈值配置)**:
*   **Source of Truth**: Backend Database (`app_config` table).
*   **Defaults**:
    *   `large_threshold`: **200,000** (20万) - Used for Main Force calculation.
    *   `super_large_threshold`: **1,000,000** (100万) - Used for UI highlighting (Purple Star).

---

## 4. Development Guide (开发指南)

### Prerequisites
*   Node.js 18+
*   Python 3.9+

### Startup

1.  **Backend**:
    ```bash
    # Install dependencies
    pip install -r backend/requirements.txt
    
    # Start Server (Port 8000)
    python -m backend.app.main
    ```

2.  **Frontend**:
    ```bash
    # Install dependencies
    npm install
    
    # Start Dev Server (Port 3001)
    npm run dev
    ```

### Key Commands
*   `python -m backend.app.main`: Start Backend
*   `npm run dev`: Start Frontend

---

## 5. API Reference (部分核心接口)

*   `GET /api/config`: Get public thresholds for frontend calculation.
*   `GET /api/ticks_full?symbol=sh600519`: Get full day trade ticks.
*   `POST /api/aggregate`: Trigger manual history aggregation for a stock.

---

## 6. Version Management (版本管理)

### Branch Strategy
*   **`main`**: Production ready code.
*   **`develop`**: Main development branch.
*   **`feature/*`**: Feature specific branches (e.g., `feature/v2.1-optimization`).

### Versioning
*   Frontend version is defined in `package.json` and `src/version.ts`.
*   Current Version: **v2.1.0**

### Release Notes (v2.1.0)
*   **Feature**: 新增“超大单占比”指标 (Super Large Ratio)，用于捕捉主力核心动向。
*   **UI**: 优化顶部搜索框布局，增加宽度并居中显示。
*   **Logic**: 修正活跃度算法逻辑，增加对超大单的独立监控。


