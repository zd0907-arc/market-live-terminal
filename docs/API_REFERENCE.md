# API 接口文档与端口配置

## 1. 端口配置规范
为确保开发环境的一致性，请严格遵守以下端口配置：

| 组件 | 端口 | 访问地址 | 说明 |
|-----------|------|-----|-------------|
| **前端 (Frontend)** | **3001** | `http://localhost:3001` | React/Vite 开发服务器 |
| **后端 (Backend)** | **8000** | `http://127.0.0.1:8000` | FastAPI 服务端 |

> **注意**: 请勿随意更改这些端口。前端代码中已配置为默认连接端口 8000 的后端服务。

## 2. API 接口说明

### 基础路径 (Base URL)
`http://127.0.0.1:8000`

### 2.1 系统配置 (Configuration)
- **GET /api/config/public**
    - **描述**: 获取用于前端计算的公共配置参数（如大单阈值）。
    - **响应示例**:
      ```json
      {
        "large_order_threshold": 200000,
        "super_large_order_threshold": 1000000
      }
      ```

### 2.2 市场数据 (Market Data)
- **GET /api/ticks_full**
    - **参数**: `?symbol=sh600519`
    - **描述**: 获取指定股票的当日全量逐笔交易数据。

- **GET /api/history_analysis**
    - **参数**: `?symbol=sh600519`
    - **描述**: 获取历史资金流向分析数据（主力买卖占比、净流入等）。

### 2.3 数据管理 (Management)
- **POST /api/aggregate**
    - **请求体**: `{"symbol": "sh600519"}`
    - **描述**: 手动触发指定股票的历史数据聚合计算任务。

## 3. 散户情绪 (Retail Sentiment)

### 3.1 触发抓取 (Crawl)
*   **Endpoint**: `POST /api/sentiment/crawl/{symbol}`
*   **Description**: 触发后台爬虫抓取指定股票的股吧评论。首次抓取或数据不足时自动执行 14 天深度抓取，否则执行增量更新。
*   **Response**: `{"code": 200, "data": {"new_count": 50}}`

### 3.2 获取仪表盘数据 (Dashboard)
*   **Endpoint**: `GET /api/sentiment/dashboard/{symbol}`
*   **Description**: 获取实时情绪聚合数据，包括情绪得分、多空比、AI 摘要（如有）。
*   **Response**:
    ```json
    {
      "score": 8,
      "bull_bear_ratio": 2.5,
      "summary": "...",
      "risk_warning": "高"
    }
    ```

### 3.3 获取趋势数据 (Trend)
*   **Endpoint**: `GET /api/sentiment/trend/{symbol}`
*   **Query Params**:
    *   `interval`: `72h` (按小时聚合，默认) 或 `14d` (按天聚合)。
*   **Response**: 包含 `time_bucket`, `total_heat`, `bull_bear_ratio` 的数组。

### 3.4 生成 AI 摘要 (Generate Summary)
*   **Endpoint**: `POST /api/sentiment/summary/{symbol}`
*   **Description**: 调用配置的 LLM 生成最新的舆情摘要并存库。
*   **Response**: `{"code": 200, "data": {"content": "..."}}`

### 3.5 获取历史摘要 (Summary History)
*   **Endpoint**: `GET /api/sentiment/summary/history/{symbol}`
*   **Description**: 获取该股票的历史 AI 摘要记录。

### 3.6 获取原始评论 (Comments)
*   **Endpoint**: `GET /api/sentiment/comments/{symbol}`
*   **Query Params**: `limit` (default 50)
*   **Description**: 获取最新的原始评论列表。
