# 03_DATA_CONTRACTS (数据与接口契约)

> **核心定位**：这是消除 AI (LLM) “幻觉补全”的最核心武器。所有后端脚本对 SQLite 数据库的 CRUD 读写、第三方爬虫的原始响应 (Payload) 都有着极端死板且严酷的结构约束。**不要盲猜，查阅本文档。**

---

## 零、 数据分层契约 (Data Layer Contract)

所有表按职责分为三层，写入规则严格遵守：

| 层级 | 表 | 写入规则 | 说明 |
|------|-----|---------|------|
| **Raw（原始层）** | `trade_ticks`, `sentiment_snapshots`, `sentiment_comments` | 默认追加；`trade_ticks` 在 ingest 场景允许按 `symbol+date` 全量覆盖写入 | 逐笔/盘口/评论源数据 |
| **Derived（派生层）** | `local_history`, `history_30m`, `sentiment_summaries` | 带版本号（`config_signature`），**可重算可覆写** | 由原始层聚合/LLM 生成 |
| **Config（配置层）** | `watchlist`, `app_config` | 用户直接操作 | 自选股、阈值等（⚠️ v4.0 起 LLM 配置已迁移至环境变量） |

> **数据一致性原则**：云端 `data/market_data.db` 是唯一权威源（Single Source of Truth）。Mac 本地通过 `sync_cloud_db.sh` 整库下载保持一致。Windows 只负责向云端写入，不保留服务副本。

---

## 一、 核心存储引擎 (SQLite 3) Schema

数据库路径：`data/market_data.db`（本地和 Docker 容器内均统一到 `data/` 子目录）。采用 `WAL` (Write-Ahead Logging) 模式开启高并发。

### 1. `local_history` (日级主力沉淀大表 / 历史核心表)
定义该股票在某日的主力增量资金结算数据。
| 字段名 | 数据类型 | 约束 / 空值规则 | 备注说明 |
| :--- | :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` | 标准六位无前缀，如 `000001` 或带前后缀如 `sz000001`。由具体数据源清洗结果决定。 |
| `date` | `TEXT` | `NOT NULL` | 零点标准时间字符串。格式严格为 `%Y-%m-%d` (如 `2026-02-12`) |
| `net_inflow` | `REAL` | `NOT NULL` | 当日主力所有大单与超大单买入金额减去卖出金额 (负数为净流出)。 |
| `main_buy_amount` | `REAL` | `NOT NULL` | 当日累计的主力买单总额。 |
| `main_sell_amount` | `REAL` | `NOT NULL` | 当日累计的主力卖单总额。 |
| `close` | `REAL` | `NOT NULL` | 必须为当日历史收盘价。 |
| `change_pct` | `REAL` | Allow `NULL` | 当日张跌幅百分比（比如 9.9 表示涨停）。 |
| `activity_ratio` | `REAL` | Allow `NULL` | 当日主力资金参与度 (主力买单+主力卖单总额 / 当日全市场总成交额)。为空代表不统计该日全市场量。 |
| `config_signature` | `TEXT` | `NOT NULL` | 必须填当前系统判定大单的资金阈值签名（例如 `200k_1m`）。以防止改了阈值导致历史混乱。 |
**唯一约束**: `UNIQUE(symbol, date, config_signature)`

### 2. `trade_ticks` (逐笔明细源表 / 万物之母)
保存所有的毫秒级最原始第三方明细流，作为所有重算系统的源头。**这张表的数据量以十亿计**，注意不要全表查。
| 字段名 | 数据类型 | 约束 / 空值规则 | 备注说明 |
| :--- | :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` | 标的股票代码。 |
| `time` | `TEXT` | `NOT NULL` | 时间格式 `%H:%M:%S` 或 `%H:%M:%S.%f`。 |
| `price` | `REAL` | `NOT NULL` | 当前成交实价。 |
| `volume` | `INTEGER` | `NOT NULL` | 当前成交手数（注意不同数据源的转化）。 |
| `amount` | `REAL` | Allow `NULL` | 当前明细产生的资金额 (`price * volume * 100` 或源提供)。 |
| `type` | `TEXT` | `NOT NULL` | 当前实现兼容：`买盘/卖盘/中性盘` 或 `buy/sell/neutral`。建议统一落库为 `buy/sell/neutral`。 |
| `date` | `TEXT` | `NOT NULL` | 关联查询用的主键前缀：%Y-%m-%d |
**索引**: 必须有联合索引 `idx_ticks_symbol_date (symbol, date)`。

### 3. `history_30m` (半小时主力资金聚合线)
| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` |
| `start_time` | `TEXT` | `NOT NULL`。格式 `%Y-%m-%d %H:%M:%S`，只允许 8 个标准桶起点：`09:30/10:00/10:30/11:00/13:00/13:30/14:00/14:30`。 |
| `net_inflow` | `REAL` | `NOT NULL` 净流入 |
| `main_buy` / `main_sell` | `REAL` | 主力(不含超大单) |
| `super_net` | `REAL` | 纯粹超大单流入差额 |
| `super_buy` / `super_sell` | `REAL` | 纯粹超大单 |
| `open` / `high` / `low` / `close` | `REAL` | 30 分钟 K 线数据，不能传空 |
**唯一约束**: `UNIQUE(symbol, start_time)`

### 4. `sentiment_snapshots` (3 秒级情绪快照流)
| 字段名 | 数据类型 | 约束 | 序列化说明 |
| :--- | :--- | :--- | :--- |
| `timestamp` / `date` | `TEXT` | 时分秒 / 年月日 | 分开存储，加速天级查询 |
| `cvd` / `oib` | `REAL` | 绝对不可为 `NULL` | |
| `outer_vol` / `inner_vol` | `INTEGER` | 绝对买盘 / 绝对卖盘 | |
| `signals` | `TEXT` | **重点：只允许存 JSON Array** | 比如 `'["Iceberg Allowed"]'`。哪怕没信号也要存 `'[]'` 字符串，绝不可以存 `NULL`。读取时必须 `json.loads`！ |
| `bid1_vol` / `ask1_vol` | `INTEGER` | 买一卖一挂单量 | 用于冰山探测 |

---

## 二、 业务外部 API 的真实 Payload 契约

编写爬虫时，绝对禁止靠想象力猜测下列接口的 JSON 返回格式。必须依照此契约。

### 1. AkShare 股票分笔接口 `stock_zh_a_tick_tx_js`
该接口获取的是腾讯接口代理的盘中逐笔数据。
**典型的 DataFrame 返回形态 (Pandas Columns)**：
*   `成交时间`: (String) 例如 `"09:30:03"`，不带日期！
*   `成交价格`: (Float) 实盘成交价，绝对精确无复权。
*   `价格变动`: (Float) 与上一笔的波动，可正可负可为 0。
*   `成交量(手)`: (Int) **这是手数！！！不要当成股数！！！1手=100股。算资金流入时必须 x100！**
*   `成交额(元)`: (Float) 已经算好的这笔金额，直接用。
*   `性质`: (String) 枚举值：买盘、卖盘、中性盘。（不要把它和上述库里的 `B`, `S` 搞混，业务上需做条件替换 `['买盘'=>'B', '卖盘'=>'S']`）。

### 3. 东财股吧原始评论接口 `stock_zh_a_code_pinglun_em`
获取股民发帖流。
**典型的 DataFrame 返回形态**：
*   待充实（目前尚未在高频系统中实现基于此源的大规模入库，预留待系统后续补齐）。

---

## 三、 内部与前端 API 契约 (Internal APIs)

前后端联调必须遵循以下接口路径与结构：

### 1. 市场数据类 (Market Data)
*   **`GET /api/history_analysis?symbol=sh600519`**: 返回云端蓄水池里的资金流向历史。
*   **`GET /api/history/trend?symbol=sh600519&days=20`**: 返回 30 分钟级资金趋势（历史 + 当天动态拼接）。
*   **`GET /api/realtime/dashboard?symbol=sh600519&date=YYYY-MM-DD`**: 分时仪表盘，`date` 缺省时自动使用 `MarketClock.get_display_date()`。

> 写接口鉴权约束（v4.2.3+）：
> - 业务写接口（如 `/api/watchlist` 的 POST/DELETE、`/api/config` POST、`/api/sentiment/crawl/*` POST）必须携带请求头 `X-Write-Token`，并与服务端 `WRITE_API_TOKEN` 一致。
> - 内部高速 ingest 接口继续使用 `INGEST_TOKEN`，且服务端不再提供默认 token。

### 2. 散户情绪类 (Retail Sentiment)
*   **`POST /api/sentiment/crawl/{symbol}`**: 触发云端无头请求，抓取股吧增量数据。返回 `{"code": 200, "data": {"new_count": 50}}`。
*   **`GET /api/sentiment/dashboard/{symbol}`**: 返回情绪全息版。结构: `{"score": 8, "bull_bear_ratio": 2.5, "risk_warning": "高"}`
*   **`POST /api/sentiment/summary/{symbol}`**: 召唤 LLM 生成摘要。
*   **`GET /api/sentiment/summary/history/{symbol}`**: 返回 `APIResponse`，`data` 为摘要数组。
*   **`GET /api/sentiment/trend/{symbol}?interval=72h|14d`**: 返回 `APIResponse`，`data` 为趋势数组。
*   **`GET /api/sentiment/comments/{symbol}`**: 返回 `APIResponse`，`data` 为评论数组。

### 3. 空状态法则 (No Silent Empty States)
**绝对执行命令**：如果后端查询数据库得到空数组 `[]`，严禁直接 `return []` 让前端去猜！必须标准化返回：
`{"code": 200, "data": [], "message": "No data found"}`。并在后端打印 `logger.warning` 说明。前端必须展示“空状态占位图”。

---
如果有以上任何未被定义边界的字段，请抛错并拦截，拒绝脏数据入库！

---

## 四、 v4.0 新增/变更接口

### 1. 星标管理（Watchlist）— 新增 DELETE
*   **`GET /api/watchlist`**: 返回全部自选股列表。
*   **`POST /api/watchlist?symbol=sh600519&name=贵州茅台`**: 添加自选股，后台自动触发历史回填和情绪爬取。
*   **`DELETE /api/watchlist?symbol=sh600519`**: 移除自选股。

### 2. LLM 配置（Security-First）
*   **`GET /api/config/llm-info`**: 返回 LLM 脱敏信息（模型名、Base URL、Key 是否已配置），**不返回 API Key 明文**。
*   **`POST /api/config/test-llm`**: 使用服务端环境变量中的 Key 测试 LLM 连通性，前端无需传参。

> ⚠️ **v4.0 破坏性变更**：`POST /api/config` 不再接受 `llm_` 前缀的 Key 写入，会返回 403。LLM 配置改由服务端环境变量管理。详见 `docs/05_LLM_KEY_SECURITY.md`。
