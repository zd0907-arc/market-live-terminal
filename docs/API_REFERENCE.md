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
