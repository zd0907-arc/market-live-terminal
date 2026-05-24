# REQ-20260429-03 AI 研究工作台的板块数据层设计

## 背景

后续研究主入口不是复杂后台，而是 Codex 与本地数据协作：

- 系统每天落行情、L2、选股、事件、板块数据。
- Codex 读取这些数据，完成研究、复盘、解释、可视化。
- 页面只做轻量辅助展示，不做复杂运营后台。

因此“股票-板块-主题”数据要作为长期数据资产维护，而不是临时脚本结果。

## 目标

建立三层板块数据：

1. 原始层：保留外部数据源原貌，便于追溯。
2. 清洗层：过滤指数、融资融券、昨日涨停等非主题标签。
3. 交易主题层：把相似板块合并成可研究、可回测、可解释的主题。

## 数据分层

### 1. Raw 原始层

数据库：

```text
/Users/dong/Desktop/AIGC/market-data/market_heat/stock_sector_map.db
```

表：

```text
sector_boards
stock_sector_memberships
```

职责：

- 保存东方财富返回的行业、概念、地域、标签类板块。
- 不做删除，不做主观合并。
- 每次刷新全量覆盖当前快照。

用途：

- 追溯“某只股票为什么被认为属于某个板块”。
- 后续补规则时不用重新联网抓取。

### 2. Clean 清洗层

配置文件：

```text
data/market_heat/sector_clean_rules.json
```

职责：

- 定义哪些板块不能直接作为市场主线。
- 给板块打标签，而不是物理删除。

规则类型：

```text
exclude:
  - 指数成分：HS300、上证50、中证、深成、国证
  - 交易属性：融资融券、沪股通、深股通
  - 持仓属性：机构重仓、基金重仓、QFII、证金持股
  - 风格属性：大盘股、小盘股、低价股、百元股
  - 短线状态：昨日涨停、昨日连板、昨日高换手、近期新高、历史新高
  - 财报标签：季报预增、年报预增、扭亏、预减

downrank:
  - 地域板块：浙江板块、上海板块、广东板块
  - 泛概念：央国企改革、华为概念、国产替代
```

产物：

```text
clean_sector_boards
clean_stock_sector_memberships
```

### 3. Tradable Theme 交易主题层

配置文件：

```text
data/market_heat/tradable_theme_rules.json
```

职责：

- 把多个原始板块合成一个可交易主题。
- 给 Codex 和页面提供“真正可研究”的主题口径。

例子：

```text
液冷/温控:
  include:
    - 液冷概念
    - 液冷服务器
    - 温控设备
    - 数据中心

创新药/CXO:
  include:
    - 创新药
    - CRO
    - CXO
    - 医疗研发外包
    - CAR-T细胞疗法

快递物流:
  include:
    - 快递
    - 快递概念
    - 物流
    - 交通运输

稀土/小金属:
  include:
    - 稀土
    - 稀土永磁
    - 小金属
    - 钨
    - 锂
    - 钼
```

产物：

```text
tradable_themes
tradable_theme_memberships
```

## 每日更新机制

### 每日数据跑完后

顺序：

```text
1. 刷新股票-板块原始映射
2. 应用清洗规则
3. 生成交易主题映射
4. 基于主题映射计算当日主题热度
5. 跑选股候选与主题热度对齐验证
6. Codex 读取结果做研究/复盘
```

建议命令：

```bash
python3 backend/scripts/build_stock_sector_map.py --source stock-plate --types concept,industry --sleep 0.01
python3 backend/scripts/build_tradable_theme_map.py
python3 backend/scripts/dump_market_hot_sectors.py --theme-source tradable-theme
python3 backend/scripts/analyze_market_heat_selection_alignment.py --theme-source tradable-theme
```

频率：

```text
stock_sector_map：每天或每周刷新
tradable_theme_map：规则变化后重建
market_heat：每天刷新
alignment/backtest：研究时按需跑
```

## Codex 使用方式

Codex 后续回答“今天看什么票”时，默认读取：

```text
1. selection_signal_daily
2. atomic_trade_daily / L2
3. tradable_theme_memberships
4. market_heat latest/history
5. selection_alignment report
```

输出重点：

- 这只票属于哪些可交易主题。
- 这些主题今天/近 5 日/近 20 日是否升温。
- 它是主题核心股、容量股、补涨股，还是孤立异动。
- 原策略信号与板块热度是否共振。
- 如果不是热门板块，是否降低优先级。

## 页面轻量展示

页面只展示三类东西：

1. 今日热门主题排行。
2. 某只候选票所属交易主题与主题热度。
3. 主题趋势图和代表票。

不做：

- 后台规则管理。
- 手工维护界面。
- 复杂权限和流程。

规则调整通过 Codex 修改 JSON 文件完成。

## 第一版落地任务

1. 新增 `sector_clean_rules.json`。
2. 新增 `tradable_theme_rules.json`。
3. 新增 `build_tradable_theme_map.py`。
4. 生成 `tradable_theme_map.db`。
5. 让 market heat 和 alignment 脚本支持 `--theme-source tradable-theme`。
6. 用近 3 个月数据验证：
   - 选股候选主题覆盖率
   - 高热主题候选后续收益
   - 大涨股是否来自高热主题
   - 低热/退潮主题是否应降权
