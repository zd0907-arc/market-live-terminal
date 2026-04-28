# REQ-20260427-03-selection-news-event-research-context

## 1. 基本信息

- 标题：选股模块接入消息事件重估与公司研究上下文
- 状态：RELEASED
- 负责人：AI / Dong
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-STOCK-EVENTS`
- 关联策略：`docs/strategy-rework/strategies/S03-news-event-revaluation/README.md`

## 2. 结论

本需求不是把 LLM 总结塞进页面，也不是做全市场新闻自动选股。

核心目标是：

```text
平台负责沉淀数据和展示轻量结论；
Codex 负责在本地数据库上做深入追问和研究分析；
页面看到的信息，Codex 必须能通过统一上下文接口/脚本拿到同一份数据。
```

第一版优先做：

```text
候选票公司研究上下文包
+ 候选票事件解释卡
+ Codex 可查询的本地上下文接口/脚本
```

第二版再做：

```text
消息触发快速研判卡
```

## 3. 用户场景

### 3.1 页面轻量决策

用户每天盘后打开选股页：

```text
选择日期
→ 查看每日复盘决策候选
→ 点某只票
→ 页面展示量化信号、事件覆盖、公司研究摘要、关键风险
```

页面只展示必要信息，不能变成大段研报。

### 3.2 Codex 深入追问

用户看到页面上的某只票后，可能来 Codex 追问：

```text
为什么这只票可买？
它的消息面是不是真的强？
这家公司到底靠什么赚钱？
有没有类似利通电子那种业务转型和估值弹性？
今天这个公告会不会只是一日游？
资金行为和事件逻辑是否一致？
```

Codex 必须能顺利拿到：

```text
当前选中股票
当前页面日期
当前策略
页面右侧展示的 profile / trade_plan / timeline / event feed / coverage
最近价格和 L2 资金序列
公司基础研究卡
事件原文和链接
```

### 3.3 利通电子式公司理解

用户真正敢持有一只中期波段票，依赖的不只是“今天资金流入”，还包括对公司的核心逻辑理解。

公司研究卡必须能沉淀类似：

```text
公司原主营是什么
现在市场关注的新业务是什么
新业务是否改变利润结构
核心资源/产能/订单/租赁规模是什么
利润弹性能否粗算
财报或公告是否验证了这个逻辑
当前市值是否已透支这个逻辑
关键证伪点是什么
```

利通电子案例对应的目标表达：

```text
原来偏消费电子/电视背板等低利润业务；
后续转型算力租赁；
算力资源规模约 33000 匹；
出租率和单匹租金决定季度利润弹性；
财报验证扣非净利润增长后，市场可能重估；
持有信心来自“资金 + 业务转型 + 利润兑现”的一致性。
```

## 4. 现有能力盘点

### 4.1 已有后端事件层

已有表：

```text
stock_events
stock_event_entities
stock_event_ingest_runs
stock_event_daily_rollup
stock_symbol_aliases
sentiment_events
sentiment_daily_scores
```

已有接口：

```text
GET  /api/stock_events/capabilities
GET  /api/stock_events/feed/{symbol}
GET  /api/stock_events/coverage/{symbol}
GET  /api/stock_events/audit/{symbol}
POST /api/stock_events/bundle/{symbol}
POST /api/stock_events/hydrate/{symbol}
```

已有数据源能力：

```text
公告 / 财报 / 监管：Tushare + 公共 fallback
互动问答：Tushare + 新浪董秘问答 fallback
财经资讯：Tushare + 新浪个股资讯 fallback
股吧舆情：sentiment_events / sentiment_daily_scores
```

当前真实状态：

```text
schema、接口、fallback 代码已存在；
本地正式库当前 stock_events 仍可能为空，需要按候选票触发 hydrate/bundle 后才有内容；
事件理解层还没做；
公司研究卡还没做；
页面和 Codex 还没有统一上下文包。
```

### 4.2 已有选股画像

已有接口：

```text
GET /api/selection/profile/{symbol}?date=YYYY-MM-DD&strategy=...
```

已有内容包括：

```text
策略状态
买入/卖出计划
资金与价格指标
风险标签
事件时间线 event_timeline
策略解释 research.strategy_explanation
```

已有前端展示：

```text
事件时间线
事件依据 / 信息来源
事件覆盖摘要
原文/PDF链接
```

### 4.3 已有早期研究卡雏形

`backend/app/services/selection_strategy_v2.py` 里已有 `build_research_card_v2`，但它是早期雏形：

```text
能读公司名 / 市值 / 事件 timeline / 舆情 snapshot / 主题标签；
只能做弱规则判断；
不能形成利通式公司认知；
没有成为当前每日复盘决策的统一接口。
```

## 5. 当前缺口

1. **缺公司研究卡**
   - 现在只有公司名、市值和事件标题，不知道主营、利润来源、业务转型、产能/订单、估值弹性。

2. **缺事件理解层**
   - 现在能展示事件，但不能稳定判断利好/利空、强弱、持续性、是否能支撑中期逻辑。

3. **缺统一上下文包**
   - 页面能看到一部分信息，但 Codex 没有一个固定入口拿到“页面同款 + 深入分析所需”的完整上下文。

4. **缺历史时点约束的研究口径**
   - 候选票历史回放时，必须只使用当时可见的事件和公司信息。

5. **缺持久化研究记忆**
   - 单次 LLM 总结不能长期复用；需要把公司研究卡、事件判断、人工修正沉淀下来。

## 6. 方案设计

### 6.1 新增公司研究卡

建议新增结构化产物：`stock_research_cards`。

字段建议：

```text
symbol
as_of_date
company_name
business_profile        # 公司一句话画像
main_business           # 原主营和收入来源
profit_drivers          # 利润来源/弹性因子
new_business_logic      # 新业务/转型/订单/产能/资源
theme_tags              # 题材/板块
valuation_logic         # 粗估值逻辑和假设
key_metrics             # 产能、订单、出租率、价格、毛利率等结构化线索
evidence_event_ids      # 支撑该认知的公告/问答/新闻
risk_points             # 证伪点和风险
confidence
source_coverage         # 数据覆盖状态
created_at
updated_at
raw_payload
```

第一版不要求自动完美生成，可以允许：

```text
规则提取 + LLM 结构化生成 + 用户后续人工修正
```

### 6.2 新增候选票研究上下文包

建议新增后端接口：

```text
GET /api/selection/research-context/{symbol}?date=YYYY-MM-DD&strategy=xxx
```

返回统一结构：

```text
symbol / name / trade_date / strategy
selection_profile        # 当前页面右侧用的同款 profile
price_l2_series          # 右侧图表需要的最近价格和 L2 指标
trade_plan               # 买入确认、次日买入、卖出信号、卖出
stock_event_coverage     # 事件覆盖状态
stock_event_feed         # 截至当时可见事件
sentiment_snapshot       # 舆情日评和热度
company_research_card    # 公司研究卡
event_interpretation     # 事件解释结果
source_audit             # 哪些源可用、哪些源缺失
```

用途：

```text
页面读取它，展示轻量信息；
Codex 读取它，回答用户深入问题；
后续批量回测也可以复用它。
```

同时提供本地脚本，方便 Codex 不走浏览器也能查：

```text
python backend/scripts/dump_selection_research_context.py \
  --symbol sh603629 \
  --date 2026-04-21 \
  --strategy stable_capital_callback
```

### 6.3 候选票事件解释卡

页面轻量展示：

```text
公司一句话画像
最新关键事件
事件强度：弱/中/强
持续性：一日游 / 1~2周 / 中期逻辑
资金一致性：confirmed / funds_only / logic_only / conflict / unknown
操作节奏：可继续研究 / 等洗盘 / 等资金回补 / 谨慎 / 不参与
```

详细内容放浮层或折叠区，不占页面。

### 6.4 消息触发快速研判卡

第二阶段做。

输入：

```text
用户粘贴消息文本
或从 stock_events 中选择一条事件
```

输出：

```text
关联股票 / 板块 / 题材
事件类型 / 强度 / 持续性 / 方向
相关股票当前价格和 L2 资金状态
是否已有资金确认
后续跟踪条件
```

交易边界：

```text
强事件 + 无资金确认：观察
强事件 + 当天爆拉：不追，等分歧/洗盘
强事件 + 分歧后资金回补：进入买入确认
弱事件 + 资金强：按资金策略，但提示一日游风险
利空/逻辑证伪：降低持有信心或退出观察
```

## 7. 实施步骤

### Phase 1：上下文打通

1. 新增 `selection research context` service。
2. 新增 `/api/selection/research-context/{symbol}`。
3. 新增 `dump_selection_research_context.py`，供 Codex 本地查询。
4. 保证返回内容与页面当前可见信息一致。

### Phase 2：公司研究卡

1. 新增 `stock_research_cards` schema。
2. 从现有 `stock_events / stock_symbol_aliases / stock_universe_meta` 生成第一版卡。
3. 支持 LLM 按固定 JSON 模板生成。
4. 支持缓存和更新时间。
5. 明确数据源缺失状态。

### Phase 3：候选票事件解释卡

1. 在每日复盘页右侧接入轻量展示。
2. 页面只露出关键结论，详细依据折叠。
3. 给 Codex 查询保留完整原始依据。

### Phase 4：消息触发快速研判卡

1. 新增消息输入/事件选择入口。
2. 做股票/板块/题材识别。
3. 拉关联股票资金状态。
4. 输出观察/等待/不参与等节奏建议。

## 8. 验收标准

### 8.1 Codex 上下文一致性

- Given 用户在页面选中 `sh603629`、日期 `2026-04-21`、策略 `stable_capital_callback`
- When Codex 调用 `dump_selection_research_context.py` 或接口
- Then 返回内容必须包含页面同款 selection profile、事件 feed、coverage、交易计划、最近 L2 序列和公司研究卡。

### 8.2 公司研究卡

- Given 一只候选票已有公告/问答/新闻事件
- When 生成公司研究卡
- Then 必须回答：主营、利润来源、新业务/转型、题材、估值弹性、证伪点、支撑证据。

### 8.3 历史时点正确

- Given 查询历史日期 `2026-03-02`
- When 返回事件和公司研究上下文
- Then 不允许包含 `published_at > 2026-03-02 23:59:59` 的事件作为判断依据。

### 8.4 源缺失透明

- Given 某只票没有 stock_events
- When 页面或 Codex 查询
- Then 必须区分：真没事件、未触发采集、源不可用、当前库为空。

### 8.5 页面不膨胀

- Given 页面右侧展示事件解释卡
- When 候选票有很多事件
- Then 首屏只展示结论和 1~3 条关键依据，其余进入折叠/浮层。

## 9. 不做什么

第一版不做：

```text
全市场新闻自动选股
盘中抢新闻
让 LLM 直接给买卖指令
复杂精确估值模型
无限长研报展示
```

## 10. 风险

1. 当前本地正式库 `stock_events` 可能为空，需要先跑候选票 hydrate。
2. 公共新闻 fallback 偏标题级，深度不如 Tushare 正文。
3. 公司研究卡可能需要人工修正机制，否则 LLM 容易误读业务。
4. 历史研究必须严格防未来函数。
5. 页面和 Codex 如果走不同数据接口，后续会出现解释不一致，所以必须优先做统一上下文包。

## 11. 结果回填（2026-04-28 / v5.0.19）

### 11.1 已发布能力

1. **统一研究上下文包**
   - 新增 `GET /api/selection/research-context/{symbol}`。
   - 新增 `POST /api/selection/research-context/{symbol}/prepare`。
   - 新增 `POST /api/selection/research-context/prewarm`。
   - 新增 `backend/scripts/dump_selection_research_context.py`，Codex 可直接从本地查询页面同口径上下文。

2. **公司概况 / 决策解释持久化**
   - 新增公司概况、财务快照、公司研究卡、事件解释、决策解释、研究依据等持久化表。
   - 页面展示改为两段人话：`公司概况`、`决策解释`，并显示生成时间。
   - 有旧内容时重新生成不再用加载态覆盖旧内容，生成完成后再替换。

3. **事件依据 / 信息来源落地**
   - 研究依据包会持久化策略/L2、财务快照、公告、问答、新闻等高价值证据。
   - 已过滤低价值制度类/独董类/泛会议类材料。
   - 页面 `研究依据` 可直接显示来源、发布时间、摘要、标签和原文链接。

4. **查询触发预热机制**
   - 点击 `查询候选` 时触发候选票研究预热：买入候选 + 前 5 个观察候选，最多 12 只。
   - 切换候选只读缓存，不再每次切票都重新生成 LLM 摘要。
   - 初次无缓存时允许短暂等待；已有缓存时保持旧内容可读。

5. **选股页稳定性修复**
   - 日期选择只改待查询日期，不再边选边自动刷新。
   - 首次进入自动落到最近有候选的日期，避免落到无候选空日期。
   - 查询时不清空候选和右侧旧内容，减少页面跳动。
   - 选股页波段复盘禁用当日 preview 写入 fallback，避免反复触发 `history_analysis` 和 SQLite 写锁。

6. **波段复盘日涨跌口径修复**
   - `/api/selection/history/multiframe` 返回 `prev_close / change_pct`。
   - 前端日线显示 `日涨跌`，按昨收计算；分钟线显示 `区间涨跌`。

### 11.2 已验证样例

- 日期：`2026-04-24`
- 策略：`trend_continuation_callback`
- 股票：`sz002468 申通快递`

验证结果：

```text
页面可看到 2026-04-24 候选列表；
申通快递为明日可操作候选；
右侧展示公司概况、决策解释、研究依据；
研究依据含策略/L2、财务快照、财报新闻和原文链接；
刷新/查询后已有内容保持可读，更新完成后替换。
```

### 11.3 发布提交

```text
39138a0 docs: define news event research context requirement
 d6d740b feat: generate selection research decision briefs
 e24a56b fix: prewarm selection research summaries on query
 8366f92 feat: persist selection research evidence
 614073a fix: stabilize selection research page loading
 58f8d39 fix: calculate multiframe daily change pct
```

### 11.4 当前边界

- 公司概况和决策解释仍依赖本地 LLM 接口；无 LLM 时会退化为规则解释。
- 新闻公共源以标题级为主，不等于完整正文研报。
- 历史时点按 `published_at <= as_of_cutoff` 截断，但公司基础资料本身仍可能来自当前可查资料，后续如要严格回放需要做版本化公司档案。

