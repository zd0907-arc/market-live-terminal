# ZhangData 智能博弈监控系统 

本项目采用 **React 前端 + Python 后端** 的混合架构，旨在突破浏览器纯前端无法获取历史资金细分数据的限制。

## 🏛 技术架构 (Architecture)

### 1. 前端 (Frontend)
- **技术栈**: React 18, TypeScript, Tailwind CSS, Recharts。
- **职责**: 
  - 界面渲染与交互。
  - **实时数据**: 直接通过 JSONP 请求腾讯/东方财富接口 (Web -> External API)。
  - **历史数据**: 调用本地 Python 后端接口 (Web -> Localhost:8000)。
  - **核心算法**: 在前端计算“主力活跃度”、“买卖占比”等衍生指标。

### 2. 后端 (Backend)
- **技术栈**: Python 3, FastAPI, Uvicorn, Requests。
- **职责**: 
  - 作为数据代理网关 (Data Proxy)。
  - 绕过浏览器跨域限制 (CORS)。
  - 调用新浪财经底层接口，获取包含 **买入/卖出分离** 的资金流向数据。
  - 数据清洗与对齐 (Merge Flow & Kline)。

---

## 🚀 快速启动 (Quick Start)

### 第一步：准备 Python 后端
后端负责提供历史数据支持。

1. 确保已安装 Python 3.8+。
2. 在项目根目录安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 启动服务：
   ```bash
   python server.py
   ```
   *服务启动后将监听 `http://127.0.0.1:8000`。*

### 第二步：启动 React 前端
前端负责展示界面。

1. 安装 Node 依赖：
   ```bash
   npm install
   ```
2. 启动开发服务器：
   ```bash
   npm run dev
   # 或者
   npm start
   ```
3. 打开浏览器访问 `http://localhost:5173` (或 3000)。

---

## 📊 数据源与核心指标说明

本系统最核心的价值在于对**主力资金活跃度**的量化监控。

### 1. 数据链路
*   **实时行情**: `fetchQuote` -> 腾讯 (GTIMG)
*   **实时逐笔**: `fetchTicks` -> 东方财富 (Level-1 Snapshots)
*   **历史博弈**: `api_history_analysis` -> Python Server -> 新浪财经

### 2. 核心指标算法 (Server -> Frontend)

我们在 Python 端获取原始的绝对金额数据，在前端计算相对比例：

#### A. 主力买入占比 (Main Buy Ratio)
衡量主力做多意愿。
```typescript
BuyRatio = (超大单买入 + 大单买入) / 当日总成交额
```

#### B. 主力卖出占比 (Main Sell Ratio)
衡量主力做空/出货意愿。
```typescript
SellRatio = (超大单卖出 + 大单卖出) / 当日总成交额
```

#### C. 主力活跃度/参与度 (Activity Ratio) - **核心指标**
衡量这只股票是否“有人管”。如果活跃度持续下降，说明主力正在撤退，散户接盘。
```typescript
Activity = (主力买入额 + 主力卖出额) / 当日总成交额
```

### 3. API 接口定义

#### GET `/api/history_analysis?symbol=sh600519`
返回包含买卖分离的历史数据。

**Response Example:**
```json
{
  "code": 200,
  "data": [
    {
      "date": "2023-10-27",
      "close": 1650.5,
      "total_amount": 5000000000,
      "main_buy_amount": 2000000000,
      "main_sell_amount": 1800000000,
      "net_inflow": 200000000,
      "super_large_in": 1000000000
    },
    ...
  ]
}
```

---

## 🛠 常见问题 (Troubleshooting)

1. **前端显示“无法连接本地Python数据服务”**
   - 检查 `server.py` 是否正在运行。
   - 检查端口是否为 `8000`。
   - 检查浏览器控制台是否有 Network Error。

2. **历史图表为空**
   - 某些冷门股票或新股可能在数据源中没有资金流向记录。
   - 尝试查询热门股（如 `sh600519` 茅台, `sz300059` 东方财富）测试。

3. **数据更新频率**
   - 历史资金数据通常在每个交易日收盘后（15:30左右）更新当日最终数据。
