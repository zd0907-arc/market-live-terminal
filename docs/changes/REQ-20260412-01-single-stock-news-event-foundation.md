# REQ-20260412-01-single-stock-news-event-foundation

## 1. 基本信息
- 标题：单票新闻 / 公告 / 互动问答事件层基础方案
- 状态：ACTIVE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260412-01`
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260411-02-market-data-processing-master`

## 2. 背景与目标
- 当前系统已经有：
  - `history_daily_l2 / history_5m_l2` 的价格与 L1/L2 资金行为；
  - `sentiment_events` 的股吧单源舆情；
  - 选股 / 复盘页已有事件位与画像位。
- 当前系统缺的不是“价格怎么走”，而是**为什么这一天主力敢这么走**：
  - 年报 / 季报 / 快报 / 预告；
  - 临时公告 / 董事会决议 / 问询函 / 监管措施；
  - 深交所互动易 / 上证e互动问答；
  - 盘后可用的财经资讯。
- 本期目标冻结为：**先把单票事件层做成稳定的盘后研究底座**，服务复盘和选股，不追求秒级实时，不追求盘中抢新闻。
- 强约束：
  1. 事件层必须独立于现有 `sentiment_events`，不能把“官方公告 / 媒体新闻 / 问答”硬塞进股吧事件表；
  2. 第一优先级是“稳定 + 可追溯 + 时间正确 + URL 可回看”，不是 fancy NLP；
  3. 先做单票 / watchlist / focus pool，可后续再扩全市场。

## 3. 调研结论：数据源分层与推荐路线

### 3.1 一级源（必须先接）——官方公告 / 财报 / 监管文书
**推荐度：最高**

#### A. 巨潮资讯（官方披露主入口）
- 站点：[`https://www.cninfo.com.cn/`](https://www.cninfo.com.cn/)
- 当前页面明确提供：`公告`、`预约披露`、`深市/沪市/北交所`、`深市问询函 / 沪市问询函`、以及 `数据API` 入口。
- 适合拿：
  - 年报 / 季报 / 半年报 / 快报 / 预告；
  - 临时公告；
  - 问询函 / 监管措施链接；
  - PDF 原文链接。
- 稳定性判断：**高**。原因：这是官方披露入口，盘后研究最需要的“真相源”基本都在这里。

#### B. Tushare `anns_d`（公告结构化接入层）
- 文档：[`anns_d`](https://tushare.pro/document/2?doc_id=176)
- 当前文档明确说明：
  - 接口为 `anns_d`；
  - “获取全量公告数据，提供 pdf 下载 URL”；
  - 单次最大 `2000` 条，可按日期循环；
  - 输出至少包含 `ann_date / ts_code / name / title / url / rec_time`。
- 推荐作用：
  - **优先作为程序化接入层**，替代直接爬官方前端页面；
  - 官方巨潮作为回查与审计源。
- 稳定性判断：**高于自行抓前端页面**。原因：接口口径清楚、历史范围长、字段稳定。

> 结论：年报 / 季报 / 临时公告 / PDF，第一期就应以 `巨潮官方真相 + Tushare 结构化接入` 为主链路。

### 3.2 二级源（必须先接）——董秘问答 / 投资者互动
**推荐度：高**

#### A. 深交所互动易
- 官方入口：[`https://irm.cninfo.com.cn/newircs/index`](https://irm.cninfo.com.cn/newircs/index)
- Tushare 文档：[`irm_qa_sz`](https://tushare.pro/document/2?doc_id=367)
- 当前文档明确说明：
  - 接口为 `irm_qa_sz`；
  - 历史从 `2010-10` 开始；
  - 描述为“互动易是由深交所官方推出，供投资者与上市公司直接沟通的平台”；
  - 输出包含 `ts_code / name / q / a / pub_time / industry`。
- 适合拿：
  - 董秘答复；
  - 投资者提问；
  - 某些尚未形成正式公告、但会显著影响预期的公司表态。

#### B. 上证e互动
- 官方说明页：[`https://sns.sseinfo.com/agreement.do`](https://sns.sseinfo.com/agreement.do)
- Tushare 文档检索结果：[`irm_qa_sh`](https://tushare.pro/document/2)（站内说明为“上证e互动问答”）
- 当前公开说明明确：
  - “上证e互动”是为促进投资者与上市公司交流搭建的互动沟通平台；
  - Tushare 检索结果说明其接口为 `irm_qa_sh`，历史从 `2023-06` 开始。
- 适合拿：
  - 上交所公司董秘答复；
  - 对题材、订单、合作、澄清类问题的表态。

> 结论：互动问答不是“新闻替代品”，但对你这种盘后中短线研究非常有价值，应该作为公告后的第二优先级事实层。

### 3.3 三级源（建议接）——财经资讯 / 快讯 / 长文
**推荐度：中高**

#### A. Tushare `news`（快讯）
- 文档检索结果：[`news`](https://www.tushare.pro/document/41?doc_id=143)
- 当前文档明确说明：
  - 接口为 `news`；
  - 提供 `6年以上` 历史；
  - 支持来源：`新浪财经 / 华尔街见闻 / 同花顺 / 东方财富 / 财联社 / 第一财经` 等；
  - 输出包含 `datetime / content / title / channels`。
- 适合拿：
  - 盘后快讯；
  - 财联社 / 东财 / 同花顺的简短事件播报；
  - 当晚是否有突发或补充催化。

#### B. Tushare `major_news`（长篇新闻）
- 文档检索结果：[`major_news`](https://tushare.pro/document/2?doc_id=195)
- 当前文档明确说明：
  - 接口为 `major_news`；
  - 覆盖 `8年以上` 历史；
  - 来源包括 `新华网 / 凤凰财经 / 同花顺 / 新浪财经 / 华尔街见闻 / 中证网 / 财新 / 第一财经 / 财联社`；
  - 输出包含 `title / content / pub_time / src`。
- 适合拿：
  - 长文资讯；
  - 深度稿、专题稿；
  - 作为公告后的舆论补充与主题解释。

> 结论：新闻层适合做“补充催化解释”，但不应压过官方公告和互动问答。

### 3.4 四级补充（第二阶段再接）——结构化财务与披露节奏
**推荐度：中**
- Tushare 文档索引当前明确列出：`业绩预告 / 业绩快报 / 财报披露日期表 / 利润表 / 资产负债表 / 现金流量表`。
- 适合第二阶段补充：
  - 让系统知道“今晚这份公告究竟是正式年报、业绩预告，还是快报”；
  - 让事件层和你已有的量价 / 净流入 / L2 信号做结构化联动。

## 4. 推荐实施路线（冻结）

### 路线 A：优先推荐（稳定优先）
- **接入层**：Tushare
- **审计 / 回查层**：巨潮资讯 / 上证e互动 / 深交所互动易官方页面
- **原因**：
  1. 你现在要的是“能稳定跑起来”，不是研究前端页面逆向；
  2. 公告 / 问答 / 新闻三类源，Tushare 已有明确接口与权限边界；
  3. 后续更容易做增量拉取、单票回补、失败重试和字段冻结。

### 路线 B：低预算备选（但稳定性次一档）
- 公告 / 问答尽量直接抓官方前端页面；
- 新闻抓东财 / 财联社 / 同花顺公开页面；
- 问题：
  - JS / 反爬 / 参数变更概率高；
  - 新闻全文结构变化更频繁；
  - 维护成本明显高于路线 A。

> 当前建议：**先按路线 A 设计系统**。如果你后面不想新增新闻权限，再退到 B，而不是反过来。

## 5. 事件层数据模型建议（第一期已落 schema）

### 5.1 新表建议
1. `stock_events`
   - 单条事件事实表，统一承接公告 / 问答 / 新闻。
2. `stock_event_entities`
   - 用于一条新闻关联多只股票时的多对多关系。
3. `stock_event_ingest_runs`
   - 记录每次抓取 / 回补 / 失败原因。
4. `stock_event_daily_rollup`
   - 给选股 / 复盘 / 时间轴快速读取的日级摘要表。

### 5.2 `stock_events` 建议字段
- `event_id`
- `source`：`cninfo | sse_einteractive | szse_irm | tushare_news | tushare_major_news | ...`
- `source_type`：`announcement | report | qa | news | regulatory`
- `symbol`：标准前缀码，如 `sz000833`
- `ts_code`：如 `000833.SZ`
- `title`
- `content_text`
- `question_text`
- `answer_text`
- `raw_url`
- `pdf_url`
- `published_at`
- `ingested_at`
- `importance`
- `is_official`
- `event_subtype`：如 `annual_report / q1_report / board_resolution / inquiry_letter / qa_reply`
- `source_event_id`
- `hash_digest`
- `extra_json`

### 5.3 关键建模规则
1. **官方公告 / 问答**：天然按单票归属，可直接写 `symbol`。
2. **新闻**：
   - 不要只按标题字符串粗暴匹配；
   - 必须做 `股票代码 + 公司名 + 曾用名 + 简称 alias` 的实体识别；
   - 允许一条新闻关联多只票，并记录 `match_method + confidence`。
3. **全文展示**：
   - 公告优先展示 `title + pdf_url`；
   - 新闻和问答全文是否前端直出，后面再看合规与版权边界；
   - 第一阶段不要求全文都上前端，先把底层事实和链接打通。
4. **与现有 `sentiment_events` 关系**：
   - `sentiment_events` 保持“散户舆情流”；
   - `stock_events` 作为“官方/新闻事件流”；
   - 前端时间轴再做融合，不在存储层强行混表。

## 6. 执行步骤（按顺序）
1. 冻结事件层 schema 与 source taxonomy：先把 `announcement / qa / news / regulatory` 四大类定死。
2. 先做 **公告链路**：
   - 单票增量拉取；
   - 标题、pdf、发布时间、公告类型落库；
   - 支持 `过去 2~3 年` 单票回补。
3. 再做 **互动问答链路**：
   - 深证互动易优先；
   - 上证e互动同步接；
   - question/answer 分字段保存。
4. 最后做 **资讯链路**：
   - 先接 `news` 快讯；
   - 再接 `major_news`；
   - 做单票归属与去重。
5. 做 **日级聚合与产品接入**：
   - 选股画像卡：最近 `20D/60D` 事件时间轴；
   - 复盘页：把事件点打到日线 / 阶段分析里；
   - 后续再考虑和股吧情绪做联合解释。

## 7. 调度建议（按你“盘后决策”场景冻结）
- 交易日：
  - `16:10 ~ 23:00`：官方公告 / 问答每 `10~15` 分钟增量一次；
  - `16:10 ~ 23:30`：新闻每 `20~30` 分钟增量一次；
  - `23:40`：做一次当日全量 reconcile；
  - `次日 08:30`：再做一次补漏校验。
- 非交易日：
  - 每晚一次即可，主要补公告 / 长文 / 历史缺口。
- 范围：
  - 第一阶段只跑 `watchlist + selection focus pool + 利通这类研究票`；
  - 不先上全市场。

## 8. 验收标准（Given/When/Then，绝对时间）
- Given `2026-04-12 20:30` 某股票当晚在巨潮披露季报，When 事件层跑完公告增量，Then 本地必须存在 `source_type=report` 的事件记录，且带 `pdf_url` 与正确 `published_at`。
- Given `2026-04-12 21:00` 某深市公司在互动易答复投资者提问，When 问答增量任务执行，Then 本地必须存在 `question_text + answer_text + pub_time` 完整记录。
- Given `2026-04-12 22:00` 某财经媒体发布涉及两只股票的资讯，When 新闻归属任务执行，Then 系统要么把新闻正确关联到两只票，要么把置信度不足的记录留在待判定区，而不是误绑单票。
- Given `2026-04-13 09:00` 打开选股或复盘页面，When 查看某单票事件卡，Then 至少能看到最近公告 / 问答 / 新闻的标题、时间、来源与跳转链接。

## 9. 风险与回滚
- 风险：
  1. 若直接抓官网前端页面，反爬 / JS / 参数漂移会增加维护成本；
  2. 新闻多票归属是天然脏活，误绑风险高；
  3. 全文存储与前端展示要注意来源协议，尤其资讯类和互动平台内容；
  4. Tushare 的公告 / 新闻 / 董秘问答属于单独权限，需要确认是否开通。
- 回滚：
  1. 若新闻层质量不稳定，可暂时只保留 `公告 + 问答`；
  2. 若多票新闻归属误差太大，可先只展示“直接公告/问答单票事实”，新闻放到候选池；
  3. 若前端暂时不消费，也要先把 `stock_events` 底座沉淀下来。

## 10. 结果回填
- 实际改动：
  1. 已落地 `stock_events / stock_event_entities / stock_event_ingest_runs / stock_event_daily_rollup` 四张表；
  2. 已新增 `backend/app/services/stock_events.py` 与 `/api/stock_events/*` 路由；
  3. 已实现 `Tushare anns_d` 单票公告同步 / 回补第一版；
  4. 已实现深市互动问答 / 沪市互动问答的单票同步与回补第一版；
  5. 已实现财经快讯 + 长篇资讯的单票同步与回补第一版，并按单票名称/代码做首版归属过滤；
  6. 已新增 `stock_symbol_aliases` 别名字典表，支持代码、ts_code、公司名、简称裁剪等 alias 管理；
  7. 已增强资讯归属：支持公司简称清洗、公司后缀裁剪、代码+名称多证据匹配，并把匹配方法/置信度写入事件元数据；
  8. 已支持资讯多实体映射基础版：对目标股票之外的 watchlist/跟踪股票做 related 关联落库，便于后续复盘时看到“一条资讯涉及多票”；
  9. 已把资讯的 `source_event_id` 做成目标股票作用域，避免同一篇资讯在不同股票同步时互相覆盖；
  10. 已新增“单票事件包同步”能力，可按需一次性拉取某只股票的公告 / 问答 / 资讯；
  11. 已新增“单票事件覆盖摘要”能力，可快速看最近窗口里财报 / 公告 / 问答 / 资讯 / 监管五类是否采到、各自最新时间和来源分布；
  12. watchlist 新增时会 best-effort 触发最近 `365D` 公告回补 + 最近 `180D` 互动问答回补 + 最近 `30D` 财经资讯回补；
  13. 选股画像时间线已开始合并显示 `stock_events`。
- 验证结果：
  1. `pytest backend/tests/test_stock_events.py backend/tests/test_selection_research.py -q` 通过；
  2. `py_compile` 已通过 `database.py / stock_events.py / stock_events router / watchlist router / selection_research.py / main.py`。
- 遗留问题：
  1. `TUSHARE_TOKEN` 与对应公告/问答/新闻权限仍需在真实环境配置；
  2. 当前财经资讯已升级到“代码+名称+简称裁剪”多证据匹配，并已引入首版 alias 表，但仍未引入正式的曾用名/历史简称词典；
  3. 一条资讯关联多只股票时，当前已支持基础 related 映射，但范围仍偏 watchlist / 跟踪股票，后续需补更稳的全量实体映射；
  4. 板块/主题联动仍是下一阶段。

## 11. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
