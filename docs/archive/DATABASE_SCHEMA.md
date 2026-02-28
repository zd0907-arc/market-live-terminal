# 数据库字典 (Database Schema)

本项目使用 SQLite 作为唯一持久化存储。以下是核心数据表的定义。

> **重要配置**: 数据库必须开启 **WAL (Write-Ahead Logging)** 模式以支持高频并发写入。

## 1. 核心交易数据

### `trade_ticks` (逐笔交易表)
存储每日的全量逐笔成交数据。数据量巨大，按日归档。

| 字段名 | 类型 | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `symbol` | TEXT | 股票代码 | `sh600519` |
| `time` | TEXT | 交易时间 | `14:30:05` |
| `price` | REAL | 成交价格 | `1800.50` |
| `volume` | INTEGER | 成交量 (手) | `100` |
| `amount` | REAL | 成交额 (元) | `180050.0` |
| `type` | TEXT | 买卖方向 | `买盘` / `卖盘` / `中性盘` |
| `date` | TEXT | 交易日期 | `2024-03-20` |

*   **索引**: `idx_ticks_symbol_date` (加速按日期查询和清理)

### `sentiment_snapshots` (博弈快照表)
存储每 3 秒一次的高频盘口快照，用于微观博弈分析（冰山/撤单）。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `symbol` | TEXT | 股票代码 |
| `timestamp` | TEXT | 时间戳 (HH:MM:SS) |
| `date` | TEXT | 日期 (YYYY-MM-DD) |
| `cvd` | REAL | 累积买卖差 (Outer - Inner) |
| `oib` | REAL | 挂单失衡度 (Bid Vol - Ask Vol) |
| `signals` | TEXT | JSON 格式的报警信号 (如 `["ICEBERG", "SPOOFING"]`) |
| `bid1_vol` | INTEGER | 买一量 |
| `ask1_vol` | INTEGER | 卖一量 |
| `tick_vol` | INTEGER | 该 3秒 内的瞬时成交量 |

*   **唯一约束**: `UNIQUE(symbol, date, timestamp)`

---

## 2. 历史与分析数据

### `local_history` (日线分析表)
存储每日收盘后的资金流向汇总数据。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `symbol` | TEXT | 股票代码 |
| `date` | TEXT | 日期 |
| `net_inflow` | REAL | 主力净流入金额 |
| `main_buy_amount` | REAL | 主力买入总额 |
| `main_sell_amount` | REAL | 主力卖出总额 |
| `activity_ratio` | REAL | 主力参与度 (%) |
| `config_signature` | TEXT | 计算该数据时使用的阈值配置签名 (用于判断是否需要重算) |

### `sentiment_comments` (舆情原始表)
存储爬取的股吧/社区评论。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | TEXT | 评论唯一ID |
| `content` | TEXT | 评论内容 |
| `sentiment_score` | INTEGER | 情感评分 (0-10) |
| `heat_score` | REAL | 热度分 (阅读+评论数加权) |

### `sentiment_summaries` (AI 摘要表)
存储 LLM 生成的每日/每小时舆情总结。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `content` | TEXT | AI 生成的摘要文本 |
| `model_used` | TEXT | 使用的模型版本 (如 `deepseek-v3`) |
| `created_at` | TIMESTAMP | 生成时间 |

---

## 3. 系统配置

### `app_config` (配置表)
KV 结构的系统配置表。

| Key | Value | 说明 |
| :--- | :--- | :--- |
| `large_threshold` | TEXT | 大单阈值 (默认 200000) |
| `super_large_threshold` | TEXT | 超大单阈值 (默认 1000000) |
