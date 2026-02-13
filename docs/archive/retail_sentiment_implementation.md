# 散户情绪模块 (Retail Sentiment) 详细实现说明文档 (v2.7.0)

## 1. 模块概述
本模块旨在通过抓取和分析东方财富股吧的散户评论，提供基于非结构化文本数据的市场情绪指标。它不仅提供传统的“多空比”统计，还集成了 LLM (大语言模型) 能力，生成深度的人工智能舆情摘要，帮助用户捕捉市场中的“一致性”与“分歧”。

## 2. 系统架构

### 2.1 数据采集层 (Crawler)
*   **服务**: `backend/app/services/sentiment_crawler.py`
*   **数据源**: 东方财富股吧 (guba.eastmoney.com)
*   **核心逻辑**:
    *   **智能抓取策略 (Smart Crawl)**:
        *   **深度抓取 (Deep Crawl)**: 当数据库中该股票无数据或最早数据晚于 14 天前时触发。自动翻页抓取，直到覆盖最近 14 天的历史评论。
        *   **增量抓取 (Incremental Crawl)**: 当已有近期数据时触发。只抓取最新页面，直到遇到数据库中已存在的评论 ID 为止。
    *   **数据清洗**: 自动过滤广告贴、置顶帖和无效短评。

### 2.2 数据分析层 (Analyzer)
*   **服务**: `backend/app/services/sentiment_analyzer.py`
*   **评分算法**: 基于关键词匹配的加权打分机制。
    *   **动态词库**: 支持从数据库 (`app_config`) 热加载关键词，无需重启。
    *   **多头词 (Bullish)**: 权重 +1。包含：`涨停`, `连板`, `吃肉`, `格局`, `起飞` 等。
    *   **空头词 (Bearish)**: 权重 -1.2 (空头情绪通常更具传染性)。包含：`跌停`, `核按钮`, `跳水`, `织布`, `A杀` 等。
*   **热度计算**: 综合阅读数 (`read_count`) 和评论数 (`reply_count`) 计算单条评论的 `heat_score`。

### 2.3 AI 智能层 (LLM Service)
*   **服务**: `backend/app/services/llm_service.py`
*   **模型支持**: 兼容 OpenAI API 标准 (支持 DeepSeek, OpenAI, Moonshot 等)。
*   **工作流**:
    1.  提取最近 24 小时内热度最高的 20 条评论。
    2.  结合当前的情绪得分 (Score) 和多空比 (Ratio)。
    3.  构建 Prompt，要求 AI 以“A股游资风格”生成 50 字以内的犀利点评。
    4.  生成结果存入 `sentiment_summaries` 表，支持历史回溯。

### 2.4 API 接口层 (FastAPI)
*   **路由**: `backend/app/routers/sentiment.py`
*   **核心接口**:
    *   `POST /crawl/{symbol}`: 触发爬虫任务。
    *   `GET /dashboard/{symbol}`: 获取实时仪表盘聚合数据。
    *   `GET /trend/{symbol}?interval=72h|14d`: 获取多维度趋势数据。
    *   `POST /summary/{symbol}`: 触发 AI 摘要生成。
    *   `GET /summary/history/{symbol}`: 获取摘要历史记录。

### 2.5 前端展示层 (React)
*   **组件**: `src/components/sentiment/SentimentDashboard.tsx`
*   **UI 特性**:
    *   **左右布局**: 左侧展示核心指标与趋势图，右侧展示实时评论流。
    *   **交互式 AI 面板**: 支持手动生成摘要、查看历史记录。
    *   **多维趋势**: 支持 72小时 (小时级) 和 14天 (天级) 视图切换。
    *   **配置化**: 支持在前端直接修改 API Key 和情绪词库。

## 3. 数据库设计 (SQLite)

### 表结构: `sentiment_comments`
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | TEXT (PK) | 评论唯一ID (源自股吧) |
| `stock_code` | TEXT | 股票代码 |
| `content` | TEXT | 评论内容 |
| `pub_time` | DATETIME | 发布时间 |
| `read_count` | INT | 阅读量 |
| `reply_count` | INT | 回复量 |
| `sentiment_score` | FLOAT | 情绪得分 |
| `heat_score` | FLOAT | 热度得分 |

### 表结构: `sentiment_summaries`
| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INT (PK) | 自增主键 |
| `stock_code` | TEXT | 股票代码 |
| `content` | TEXT | AI 生成的摘要内容 |
| `created_at` | DATETIME | 生成时间 |
| `model_used` | TEXT | 使用的模型名称 |

## 4. 配置项 (`app_config`)
*   `sentiment_bull_words`: 多头关键词列表 (逗号分隔)。
*   `sentiment_bear_words`: 空头关键词列表。
*   `llm_base_url`: LLM API 地址。
*   `llm_api_key`: LLM 认证密钥。
*   `llm_model`: 模型名称 (e.g. `gpt-3.5-turbo`, `deepseek-chat`)。
