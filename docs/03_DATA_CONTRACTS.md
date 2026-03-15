# 03_DATA_CONTRACTS (数据与接口契约)

> **核心定位**：这是消除 AI (LLM) “幻觉补全”的最核心武器。所有后端脚本对 SQLite 数据库的 CRUD 读写、第三方爬虫的原始响应 (Payload) 都有着极端死板且严酷的结构约束。**不要盲猜，查阅本文档。**
>
> **边界提醒**：本文件只定义“数据与接口契约”，不承载业务规则裁决。业务目标/时序规则/验收案例统一在 `docs/02_BUSINESS_DOMAIN.md`。

---

## 零、 数据分层契约 (Data Layer Contract)

所有表按职责分为三层，写入规则严格遵守：

| 层级 | 表 | 写入规则 | 说明 |
|------|-----|---------|------|
| **Raw（原始层）** | `trade_ticks`, `sentiment_snapshots`, `sentiment_comments` | 默认追加；`trade_ticks` 在 ingest 场景允许按 `symbol+date` 全量覆盖写入 | 逐笔/盘口/评论源数据 |
| **Derived（派生层）** | `local_history`, `history_30m`, `sentiment_summaries` | 带版本号（`config_signature`），**可重算可覆写** | 由原始层聚合/LLM 生成 |
| **Derived（生产L2历史层）** | `history_5m_l2`, `history_daily_l2`, `l2_daily_ingest_runs`, `l2_daily_ingest_failures` | 仅允许按 `symbol+trade_date` 整日覆盖重写 | 盘后L2正式结算结果（含同源 L1/L2 双派生） |
| **Derived（盘中预览层）** | `realtime_5m_preview`, `realtime_daily_preview` | 仅允许按 `symbol+trade_date` 整日覆盖重写；只存 preview，不得伪装 finalized | 盘中临时 L1 预览层，服务新版多维历史/当日衔接 |
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
| `type` | `TEXT` | `NOT NULL` | 当前实现兼容：`买盘/卖盘/中性盘`、`buy/sell/neutral`、`B/S/M`。API 对外返回前必须归一化为 `buy/sell/neutral`。 |
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

### 5. `history_5m_l2`（生产正式 L2 历史 5 分钟底座）
> **生产正式层**：该表属于 `data/market_data.db`，用于盯盘历史模式、日后复盘页正式查询、多周期聚合源。

| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL`，标准代码（如 `sz000833`） |
| `datetime` | `TEXT` | `NOT NULL`，5分钟桶起点 `%Y-%m-%d %H:%M:%S` |
| `source_date` | `TEXT` | `NOT NULL`，源交易日 `%Y-%m-%d` |
| `open/high/low/close` | `REAL` | `NOT NULL` |
| `total_amount` | `REAL` | `NOT NULL`，该股票该5分钟切片总成交额 |
| `l1_main_buy/sell` | `REAL` | `NOT NULL`，L1 主力绝对买卖（单笔阈值） |
| `l1_super_buy/sell` | `REAL` | `NOT NULL`，L1 超大单绝对买卖 |
| `l2_main_buy/sell` | `REAL` | `NOT NULL`，L2 主力绝对买卖（母单聚合） |
| `l2_super_buy/sell` | `REAL` | `NOT NULL`，L2 超大单绝对买卖 |
| `quality_info` | `TEXT` | Allow `NULL`，有问题时写一段人类可读说明 |
**主键**: `PRIMARY KEY(symbol, datetime)`
> 说明：
> - 正式历史最细粒度固定为 `5m`，不额外维护 `1m` 生产持久层；
> - `net` 字段允许查询时按 `buy-sell` 派生，避免重复存储；
> - `15m/30m/1h` 统一由本表聚合，不单独落库。
> - `quality_info` 仅服务新版历史多维轻量质量提示；无问题时保持为空。

### 6. `history_daily_l2`（生产正式 L2 历史日线底座）
> **生产正式层**：服务历史日K资金博弈分析，并为后续 L1/L2 对比提供统一日线事实表。

| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` |
| `date` | `TEXT` | `NOT NULL`，交易日 `%Y-%m-%d` |
| `open/high/low/close` | `REAL` | `NOT NULL` |
| `total_amount` | `REAL` | `NOT NULL` |
| `l1_main_buy/sell/net` | `REAL` | `NOT NULL` |
| `l1_super_buy/sell/net` | `REAL` | `NOT NULL` |
| `l2_main_buy/sell/net` | `REAL` | `NOT NULL` |
| `l2_super_buy/sell/net` | `REAL` | `NOT NULL` |
| `l1_activity_ratio` | `REAL` | `NOT NULL`，L1 `(buy+sell)/total_amount*100` |
| `l1_super_ratio` | `REAL` | `NOT NULL`，L1 超大单参与度 |
| `l2_activity_ratio` | `REAL` | `NOT NULL`，L2 `(buy+sell)/total_amount*100` |
| `l2_super_ratio` | `REAL` | `NOT NULL`，L2 超大单参与度 |
| `l1_buy_ratio` / `l1_sell_ratio` | `REAL` | `NOT NULL`，供历史日K资金博弈分析 |
| `l2_buy_ratio` / `l2_sell_ratio` | `REAL` | `NOT NULL`，供未来历史 L1/L2 对比分析 |
| `quality_info` | `TEXT` | Allow `NULL`，有问题时写一段人类可读说明 |
**主键**: `PRIMARY KEY(symbol, date)`
> 说明：
> - 当天历史模块仍可临时展示实时值，但次日及以后应以本表为正式值；
> - 本表是未来历史日K里 L1/L2 对比分析的统一来源。
> - 对整日缺失的日线，不强行写假值入本表，而在新版查询层补 placeholder。

### 7. `l2_daily_ingest_runs / l2_daily_ingest_failures`（盘后 L2 日级回补状态）
> **生产运维层**：记录每日盘后 L2 正式结算 / 重跑 / 失败信息。

- `l2_daily_ingest_runs`
  - 用途：记录某日回补任务开始/结束/状态/覆盖行数/提示信息；
  - 关键字段建议：`trade_date/status/started_at/finished_at/message/symbol_count/rows_5m/rows_daily/source_root`;
- `l2_daily_ingest_failures`
  - 用途：记录具体失败股票、失败源文件、错误原因；
  - 关键字段建议：`run_id/symbol/trade_date/source_file/error_message/created_at`;
- 写入规则：
  - 支持同一天重复回补；
  - 重跑以覆盖写为准，不允许产生重复正式记录；
  - 失败记录必须可追溯到文件级；
  - 除了解析/对齐失败，**未形成正式 `5m + daily` 的空结果样本**也必须写入本表，避免静默缺口。

### 8. `realtime_5m_preview`（盘中 5 分钟预览层）
> **盘中预览层**：服务新版“当日分时 / 历史多维”在今日场景下的临时 L1 数据，不得与 finalized 历史混用。

| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` |
| `datetime` | `TEXT` | `NOT NULL`，5 分钟桶起点 `%Y-%m-%d %H:%M:%S` |
| `trade_date` | `TEXT` | `NOT NULL`，交易日 `%Y-%m-%d` |
| `open/high/low/close` | `REAL` | `NOT NULL` |
| `total_amount` | `REAL` | `NOT NULL` |
| `l1_main_buy/sell` | `REAL` | `NOT NULL` |
| `l1_super_buy/sell` | `REAL` | `NOT NULL` |
| `source` | `TEXT` | `NOT NULL`，当前固定 `realtime_ticks` |
| `preview_level` | `TEXT` | `NOT NULL`，当前固定 `l1_only` |
| `updated_at` | `TEXT` | `NOT NULL` |
**主键**: `PRIMARY KEY(symbol, datetime)`
> 说明：
> - 当前只落 L1 preview，不伪造 L2；
> - 写入方式为同一 `symbol+trade_date` 覆盖重写；
> - 后续 `30m/1h` 统一由本表在“今日场景”下聚合。

### 9. `realtime_daily_preview`（盘中日线预览层）
> **盘中预览层**：服务新版“历史多维=日”在今日未结算场景下的 L1-only 日线。

| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` |
| `date` | `TEXT` | `NOT NULL`，交易日 `%Y-%m-%d` |
| `open/high/low/close` | `REAL` | `NOT NULL` |
| `total_amount` | `REAL` | `NOT NULL` |
| `l1_main_buy/sell/net` | `REAL` | `NOT NULL` |
| `l1_super_buy/sell/net` | `REAL` | `NOT NULL` |
| `source` | `TEXT` | `NOT NULL`，当前固定 `realtime_ticks` |
| `preview_level` | `TEXT` | `NOT NULL`，当前固定 `l1_only` |
| `updated_at` | `TEXT` | `NOT NULL` |
**主键**: `PRIMARY KEY(symbol, date)`
> 说明：
> - 盘后正式 L2 到位后，次日及以后应统一切回 `history_daily_l2`；
> - 新版前端必须通过 `is_finalized=false + preview_level=l1_only` 显式识别该层。

### 10. `sandbox_review.db::review_5m_bars` (沙盒复盘专用，非生产，V1兼容)
> **隔离红线**：该表位于独立数据库 `data/sandbox_review.db`，禁止写入 `data/market_data.db`。

| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL`，标准代码（如 `sh603629`） |
| `datetime` | `TEXT` | `NOT NULL`，5分钟桶起点 `%Y-%m-%d %H:%M:%S` |
| `open/high/low/close` | `REAL` | `NOT NULL`，5分钟 OHLC |
| `total_amount` | `REAL` | `NOT NULL`，该股票该5分钟切片总成交额（分母口径） |
| `l1_main_buy/sell/net` | `REAL` | `NOT NULL`，L1 主力绝对买卖与净流入 |
| `l1_super_buy/sell/net` | `REAL` | `NOT NULL`，L1 超大单绝对买卖与净流入 |
| `l2_main_buy/sell/net` | `REAL` | `NOT NULL`，L2 主力绝对买卖与净流入 |
| `l2_super_buy/sell/net` | `REAL` | `NOT NULL`，L2 超大单绝对买卖与净流入 |
| `source_date` | `TEXT` | `NOT NULL`，源交易日 `%Y-%m-%d` |
**主键**: `PRIMARY KEY(symbol, datetime)`

### 11. `data/sandbox/review_v2/`（沙盒复盘 V2，云端可访问但与生产库隔离）
> **隔离红线**：目录级隔离，所有 V2 数据仅允许落在 `data/sandbox/review_v2/`，不得写入 `data/market_data.db`。

#### 6.1 `meta.db::sandbox_stock_pool`
| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | 主键，`sh/sz` 六位标准代码 |
| `name` | `TEXT` | `NOT NULL` |
| `market_cap` | `REAL` | `NOT NULL`，最新总市值（元） |
| `as_of_date` | `TEXT` | `NOT NULL`，池子快照日期 `%Y-%m-%d` |
| `source` | `TEXT` | `NOT NULL`，来源（如 `akshare.stock_zh_a_spot_em` 或 `akshare.stock_individual_info_em`） |
| `updated_at` | `TEXT` | 自动时间戳 |
> 口径：仅沪深A、排除 ST、总市值 50-300亿，固定池（不日更）。

#### 6.2 `meta.db::sandbox_backfill_runs / sandbox_backfill_month_runs / sandbox_backfill_failures`
- 用途：记录 V2 批处理 run 状态、月份级 run 状态、失败清单（symbol/date/source/error）。
- 要求：
  - `sandbox_backfill_month_runs` 必须能查询某个月份最近一次 run 的 `status/rows/failed_count`，供全月份总控脚本判断是否进入下一月；
  - 失败记录可追溯到源文件，支持后续重试。
- 运维约定：全月份总控脚本还会额外写出 `data/sandbox/review_v2/logs/run_all_months_latest.json`，用于查看当前月份、已完成月份、失败月份与最终 `done/failed` 状态。

#### 6.3 `symbols/{symbol}.db::review_5m_bars`
| 字段名 | 数据类型 | 约束 / 备注 |
| :--- | :--- | :--- |
| `symbol` | `TEXT` | `NOT NULL` |
| `datetime` | `TEXT` | `NOT NULL`，5分钟桶起点 `%Y-%m-%d %H:%M:%S` |
| `open/high/low/close` | `REAL` | `NOT NULL` |
| `total_amount` | `REAL` | `NOT NULL`，该股票该5分钟总成交额 |
| `l1_main_buy/sell` | `REAL` | `NOT NULL` |
| `l1_super_buy/sell` | `REAL` | `NOT NULL` |
| `l2_main_buy/sell` | `REAL` | `NOT NULL` |
| `l2_super_buy/sell` | `REAL` | `NOT NULL` |
| `source_date` | `TEXT` | `NOT NULL`，源交易日 |
**主键**: `PRIMARY KEY(symbol, datetime)`
> `net` 字段在查询时按 `buy-sell` 计算，避免重复存储。V2 已收敛为“5m底层 + 上层聚合”，不再维护 1m 持久层。
> 新决策（2026-03-14）：sandbox V2 继续保留实验用途，但未来生产正式页面不应长期依赖该数据域。

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
*   `性质`: (String) 枚举值：买盘、卖盘、中性盘。（入库可保留原值；聚合/接口输出阶段统一归一化为 `buy/sell/neutral`，并兼容历史 `B/S/M` 记录。）

### 3. 东财股吧原始评论接口 `stock_zh_a_code_pinglun_em`
获取股民发帖流。
**典型的 DataFrame 返回形态**：
*   待充实（目前尚未在高频系统中实现基于此源的大规模入库，预留待系统后续补齐）。

---

## 三、 内部与前端 API 契约 (Internal APIs)

前后端联调必须遵循以下接口路径与结构：

### 1. 市场数据类 (Market Data)
*   **`GET /api/history_analysis?symbol=sh600519`**: 返回云端蓄水池里的资金流向历史。
*   **`GET /api/history/trend?symbol=sh600519&days=20&granularity=30m`**: 返回历史趋势；当前正式支持 `granularity=5m|15m|30m|1h|1d`，其中 `15m/30m/1h/1d` 一律由 `history_5m_l2` 聚合。
*   **`GET /api/history/multiframe?symbol=sh600519&granularity=30m&days=20`**:
    - 描述：新版“历史多维”统一接口；
    - 支持参数：`granularity=5m|15m|30m|1h|1d`（兼容 `day/daily/60m` 别名）、`days`、`start_date`、`end_date`、`include_today_preview`；
    - 数据来源：
      - 历史 finalized：`history_5m_l2 / history_daily_l2`
      - 今日 preview：`realtime_5m_preview / realtime_daily_preview`
    - 返回结构：`APIResponse.data={"symbol","granularity","days","start_date","end_date","count","items":[...]}`；
    - `items[*]` 统一字段：
      - `datetime/trade_date/granularity`
      - `open/high/low/close/total_amount`
      - `l1_main_buy/sell`, `l1_super_buy/sell`
      - `l2_main_buy/sell`, `l2_super_buy/sell`（preview 行为 `null`）
      - `source/is_finalized/preview_level/fallback_used`
      - `quality_info`（有问题时为文本说明，无问题时为空）
      - `is_placeholder`（查询层补出的缺失占位）
    - 规则：今日未结算 preview 行必须返回 `is_finalized=false`、`preview_level=l1_only`，不得伪装为正式 L2。
    - 规则：placeholder 项只允许用于新版历史多维展示缺失，不得被前端当成数值 `0`。
*   **`GET /api/realtime/dashboard?symbol=sh600519&date=YYYY-MM-DD`**: 分时仪表盘，`date` 缺省时自动使用 `MarketClock.get_display_date()`。
    - 路径规则：仅当 `query_date == 自然日当天` 且当天为交易日时，后端才走实时 ticks 聚合；若进入历史/回溯日期，则优先走 `history_1m` 静态回放；若该日 `history_1m` 缺失，则继续尝试 `history_5m_l2`；若仍缺失但 `trade_ticks` 已存在，则回退为该日 ticks 现场聚合。
    - 响应补充字段：`source`、`is_finalized`、`bucket_granularity`，供前端准确标记“实时 / 历史1m / 正式L2历史5m”。
*   **`POST /api/monitor/heartbeat?symbol=sh600519&mode=focus|warm`**:
    - 描述：登记实时页活跃心跳。
    - 规则：`mode` 仅允许 `focus/warm`；非法值按 `warm` 降级。
    - 边界：若实时页正在查看历史日期，则前端不得继续发送 heartbeat。
*   **`GET /api/monitor/active_symbols`**:
    - 描述：返回 Windows crawler 使用的活跃分层快照。
    - 返回：`APIResponse`，`data={"focus_symbols":[...],"warm_symbols":[...],"all_symbols":[...]}`。
    - 兼容：爬虫端需兼容旧版 flat list 响应，避免云端/Windows 分批发布时断链。

*   **`GET /api/history_analysis?symbol=sh600519`**（正式 L2 历史切换后补充契约）:
    - 历史日期优先读取 `history_daily_l2`；
    - 当天继续返回实时口径，且不得覆盖已正式结算的历史日期；
    - 响应补充 `source`、`is_finalized`、`fallback_used`，明确区分“正式历史值/当日实时值/兜底旧口径”；
    - 历史正式值当前默认输出 L2 主指标，同时预留同源 `l1_* / l2_*` 扩展字段供后续页面做对比分析。

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
`{"code": 200, "data": [], "message": "无数据"}`。并在后端打印 `logger.warning` 说明。前端必须展示“空状态占位图”。

---
如果有以上任何未被定义边界的字段，请抛错并拦截，拒绝脏数据入库！

---

## 五、 Windows 盘后 L2 日包目录契约（vNext 设计冻结）

正式目录规范如下：

```text
D:\MarketData\
  └── YYYYMM\
      └── YYYYMMDD\
          └── 000833.SZ\
              ├── 行情.csv
              ├── 逐笔成交.csv
              └── 逐笔委托.csv
```

规则：
- 月目录必须存在：`YYYYMM`
- 日目录必须存在：`YYYYMMDD`
- 股票目录名必须带交易所后缀：`.SZ/.SH/.BJ`
- 允许存在“旧裸日目录”作为过渡输入，但新下载数据不再允许长期裸放；
- 新日包 ETL 需优先按此结构做日期识别与归档验真。

---

## 六、 v4.0 新增/变更接口

### 1. 星标管理（Watchlist）— 新增 DELETE
*   **`GET /api/watchlist`**: 返回全部自选股列表。
*   **`POST /api/watchlist?symbol=sh600519&name=贵州茅台`**: 添加自选股，后台自动触发历史回填和情绪爬取。
*   **`DELETE /api/watchlist?symbol=sh600519`**: 移除自选股。

### 2. LLM 配置（Security-First）
*   **`GET /api/config/llm-info`**: 返回 LLM 脱敏信息（模型名、Base URL、Key 是否已配置），**不返回 API Key 明文**。
*   **`POST /api/config/test-llm`**: 使用服务端环境变量中的 Key 测试 LLM 连通性，前端无需传参。

> ⚠️ **v4.0 破坏性变更**：`POST /api/config` 不再接受 `llm_` 前缀的 Key 写入，会返回 403。LLM 配置改由服务端环境变量管理。详见 `docs/05_LLM_KEY_SECURITY.md`。

### 3. 沙盒复盘接口（v4.2.11+，非生产主链路）
* **`GET /api/sandbox/review_data?symbol=sh603629&start_date=2026-01-01&end_date=2026-02-28`**
  - 描述：查询 sandbox 5m 复盘数据（L1/L2 buy/sell/net + OHLC）。
  - 参数扩展：支持 `granularity=5m|15m|30m|60m|1d`（默认 `5m`）。
  - 返回：`APIResponse`，`data` 为按时间升序数组。
  - 空状态：返回 `{"code": 200, "data": [], "message": "无数据"}`。
  - 质量保护：若检测到“整日重复分时”异常，接口会自动剔除重复日，并在 `message` 返回类似 `检测到重复交易日数据并已剔除：2026-02-23≈2026-02-11`。
  - 红线：仅允许读取 sandbox 数据域（`sandbox_review.db` 或 `data/sandbox/review_v2/*`），不得回退到生产库。
  - 契约稳定：锚点累计、活跃度、净流比等新增展示均为前端衍生计算，本接口本轮不新增字段。
  - 运维备注：若云端已同步 symbol DB 但接口仍返回空数组，优先检查容器内 `backend/app/db/sandbox_review_v2_db.py` 是否仍是旧版 1m 逻辑，并重建 backend 容器。
* **`GET /api/sandbox/pool?keyword=&limit=`**
  - 描述：返回复盘可选股票池（symbol/name/market_cap/as_of_date）。
  - 返回：`APIResponse`，`data={total,as_of_date,items[]}`。
  - 空状态：`code=200` + 空数组，`message=股票池为空，请先执行 pool build`。
* **`POST /api/sandbox/run_etl`**
  - 描述：一键触发沙盒 ETL（支持 `pilot/full`）。
  - Body：`{mode,symbol,start_date,end_date,src_root?,output_db?}`。
  - 返回：`APIResponse`，`data` 为当前 ETL 任务状态快照（含日志尾部）。
  - 严格口径：默认要求源文件同时存在 `BuyOrderID/SaleOrderID` 列；缺失任一列应直接失败并在 `log_tail` 给出文件路径。
  - 覆盖策略：每次 ETL 会先清理该 `symbol` 的历史 `review_5m_bars`，避免混入旧月份数据。
  - 并发约束：同一时刻仅允许 1 个 ETL 任务运行；并发触发返回 `code=409`。
* **`GET /api/sandbox/etl_status`**
  - 描述：获取当前/最近一次沙盒 ETL 任务状态与日志尾部。
  - 返回：`APIResponse`，`data` 包含 `running/started_at/finished_at/exit_code/log_tail`。

> 前端展示补充（v4.2.12+）：
> - `/sandbox-review` 使用双端时间范围滑块横向拖动；
> - 可视跨度动态聚合：`1日=5m`、`3/5日=15m`、`20日=60m`、`60日/全部=1d`；
> - 提供手动粒度覆盖：`自动 | 5m | 15m | 30m | 60m | 1d`；
> - 前端采用 Fail-Closed：接口失败或空数据时不展示预置回退图，只展示错误/空状态。
> - （v4.2.13+）主图区升级为 6 图同屏（K线 + 主力绝对 + 超大绝对 + 主力净流 + 超大净流 + 净流比），并保持统一时间轴联动。
> - （v4.2.13+）主力/超大绝对图新增 L1/L2 活跃度线：`(buy+sell)/total_amount*100`，允许 >100%（理论上限 200%）。
> - （v4.2.13+）净流比图口径固定：`(main_net + super_net)/total_amount*100`，资金 tooltip 统一 `w`，比例统一 `%`。
> - （v4.2.14+）新增“锚点累计模式”前端交互：点击 K 线设定锚点时间戳，累计区拆为 `主力L2/主力L1/超大L2/超大L1` 四图独立展示。
> - （v4.2.14+）累计语义固定为“单曲线累计净流入”：每图仅一条累计曲线，正负通过面积分色表达；累计公式为从锚点开始对对应 `*_net` 的滚动求和（锚点前置空）。
> - （v4.2.14+）累计终点跟随当前可视窗口右边界；百分比轴展示整数 `%`（无小数）。

### 4. 实时盯盘二态契约（v4.2.15+）
- 实时页盯盘仅保留二态：
  - `focus`：5 秒轮询报价与实时图；
  - `warm`：30 秒轮询报价与实时图。
- 静默刷新约束：
  - 周期刷新失败时，前端必须保留上一版成功 `quote/chart_data/cumulative_data/latest_ticks`；
  - 仅在切股票或切历史日期时允许清空图表；
  - UI 可以显示“静默刷新中/连接波动”，但不得整块卸载实时区域。
- Windows crawler 口径：
  - `focus_symbols` 使用 5 秒 tick 节奏；
  - `warm_symbols` 使用 30 秒 tick 节奏；
  - watchlist 仍按 15 分钟全量兜底轮扫；
  - 本轮不支持“最近查看股票”额外中频队列。
