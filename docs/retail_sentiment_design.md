# 散户情绪模块 (Retail Sentiment) 需求设计文档

## 1. 业务背景
散户情绪是影响A股短期走势的关键因素之一。传统的资金流向指标往往滞后，而论坛（如东方财富股吧）的评论数据能更早地反映散户的心理状态（贪婪或恐慌）。
本模块旨在通过爬取、清洗、分析股吧评论数据，构建一套独立于资金流的“情绪指标体系”，辅助用户判断市场热度和潜在拐点。

## 2. 系统架构
本模块采用前后端分离架构，后端负责数据采集与分析，前端负责数据可视化。

### 2.1 后端架构 (Python/FastAPI)
- **数据源**: 东方财富股吧 (Eastmoney Guba)。
- **存储**: SQLite (`sentiment_comments` 表)。
- **服务层**:
    - `SentimentCrawler`: 负责增量抓取评论。
    - `SentimentAnalyzer`: 负责数据清洗、情感打分 (Dict-based)、热度计算。
    - `LLMAnalyst` (Mock/API): 负责生成定性总结。
- **API**: 提供触发抓取、获取仪表盘数据、获取趋势数据的接口。

### 2.2 前端架构 (React/TypeScript)
- **Dashboard**: 展示核心指标 (Score, Status, Ratio) 和 AI 总结。
- **TrendChart**: 展示情绪热度和多空比的历史趋势。

## 3. 详细设计

### 3.1 数据库设计 (`sentiment_comments`)
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | TEXT | 主键 (格式: `code_timestamp_index`) |
| `stock_code` | TEXT | 股票代码 (如 `000833`) |
| `content` | TEXT | 评论内容 |
| `pub_time` | DATETIME | 发布时间 |
| `read_count` | INTEGER | 阅读量 |
| `reply_count` | INTEGER | 回复量 |
| `sentiment_score` | INTEGER | 情感分 (-1: 空, 0: 中, 1: 多) |
| `heat_score` | REAL | 热度分 (Log(Read) + Reply*20) |
| `crawl_time` | DATETIME | 抓取入库时间 |

### 3.2 核心算法

#### 3.2.1 情感打分 (Dict-based)
- **多头词库 (+1)**: 涨停, 连板, 跨年, 龙头, 满仓, 梭哈, 起飞, 大肉, 接力, 格局, 封死, 抢筹, 牛逼, yyds
- **空头词库 (-1)**: 跌停, 核按钮, 大面, 割肉, 出货, 垃圾, 骗炮, 快跑, 崩盘, A杀, 埋了, 套牢, 退市, 绿
- **计算公式**: `Score = (BullHits) - (BearHits * 1.2)`
- **归一化**: Score > 0 -> 1; Score < 0 -> -1; Else -> 0

#### 3.2.2 热度计算
- **公式**: `Heat = log10(ReadCount + 1) + (ReplyCount * 20)`

#### 3.2.3 LLM 分析 (Prompt Logic)
- **输入**: 历史趋势 (近10天热度/多空比变化) + 今日精选评论 (Top Heat / Newest / Risk)。
- **输出**: JSON `{ score, status, summary, risk_warning }`。

### 3.3 API 接口定义

#### `POST /api/sentiment/crawl/{symbol}`
- **功能**: 触发指定股票的增量抓取。
- **参数**: `symbol` (股票代码)。
- **返回**: `{ "new_count": 50, "message": "Success" }`。

#### `GET /api/sentiment/dashboard/{symbol}`
- **功能**: 获取仪表盘数据。
- **返回**:
```json
{
  "score": 8,
  "status": "极度狂热",
  "bull_bear_ratio": 3.5,
  "summary": "散户一致看多，都在幻想连板...",
  "risk_warning": "高 (一致性过强，提防大面)",
  "details": { "bull_count": 120, "bear_count": 30 }
}
```

#### `GET /api/sentiment/trend/{symbol}`
- **功能**: 获取趋势图数据。
- **返回**:
```json
[
  { "time": "2023-10-01 10:00", "heat": 500, "ratio": 1.2 },
  { "time": "2023-10-01 11:00", "heat": 800, "ratio": 2.5 }
]
```

## 4. 前端展示
- **位置**: 股票详情页顶部，作为独立模块。
- **交互**: 输入股票代码 -> 自动调用 `crawl` -> 刷新 Dashboard 和 Chart。
