# MOD-20260424-01-stock-events-current-state

## 1. 目的
把“新闻 / 公告 / 问答事件层”当前已经做到什么、实际能拿回什么数据、哪些是 fallback、哪些还没做，收成一张**当前真相母卡**。

> 先看这张，再看历史过程卡：
> - `REQ-20260412-01-single-stock-news-event-foundation.md`
> - `REQ-20260423-01-stock-event-refine-and-selection-fusion.md`
> - `INV-20260419-01-yuegui-event-truth-set.md`
> - `INV-20260419-02-three-sample-event-audit.md`

---

## 2. 当前已经能拿回来的数据

### A. 公告 / 财报 / 监管
- 主来源（有 `TUSHARE_TOKEN`）：
  - `tushare_anns_d`
- 公共 fallback（无 token）：
  - `public_sina_announcements`
  - `public_sina_earnings_notice`
- 当前能落到的事件类型：
  - 年报 / 季报 / 半年报 / 业绩预告 / 业绩快报
  - 董事会决议 / 股东大会决议
  - 问询函 / 监管函 / 关注函（通过公告标题分类进 `regulatory`）
- 关键字段：
  - `title`
  - `source_type`
  - `event_subtype`
  - `published_at`
  - `raw_url`
  - `pdf_url`（公告链路优先）

### B. 互动问答
- 主来源（有 `TUSHARE_TOKEN`）：
  - `tushare_irm_sz`
  - `tushare_irm_sh`
- 公共 fallback（无 token）：
  - `public_sina_dongmiqa`
- 当前能落到的关键字段：
  - `title`
  - `question_text`
  - `answer_text`
  - `published_at`
  - `raw_url`
  - `event_subtype`（如 `qa_material / qa_clarification / qa_reply`）

### C. 财经资讯
- 主来源（有 `TUSHARE_TOKEN`）：
  - `tushare_news`
  - `tushare_major_news`
- 公共 fallback（无 token）：
  - `public_sina_stock_news`
- 当前能落到的关键字段：
  - `title`
  - `content_text`（当前公共 fallback 主要是标题级；Tushare 源可带正文）
  - `published_at`
  - `raw_url`
  - `event_subtype`

### D. 统一产物
以上三类源都会统一沉淀到：
- `stock_events`
- `stock_event_entities`
- `stock_event_ingest_runs`
- `stock_event_daily_rollup`

并统一提供：
- `GET /api/stock_events/feed/{symbol}`
- `GET /api/stock_events/coverage/{symbol}`
- `GET /api/stock_events/audit/{symbol}`
- `GET /api/stock_events/capabilities`
- `POST /api/stock_events/bundle/{symbol}`
- `POST /api/stock_events/hydrate/{symbol}`

---

## 3. 当前真实能力边界

### 已经完成
1. **单票三大类事件都能采**
   - 公告
   - 问答
   - 资讯
2. **无 token 模式也能工作**
   - 不是只有公告能跑，现在问答和资讯也都有公共 fallback
3. **可以区分“没采到”与“源不可用”**
   - `capabilities / coverage / audit` 已接入这层语义
4. **可以按需触发**
   - `bundle`
   - `hydrate`
5. **已经能服务选股候选票场景**
   - 候选票出来后，可直接触发单票事件上下文准备

### 还没完成
1. **事件理解层还没做**
   - 还没有正式的利好/利空/催化类型/持续性结构化输出
2. **公共资讯 fallback 目前偏标题级**
   - 不等于完整正文事实库
3. **多票实体映射仍是基础版**
   - 目前偏 watchlist / 跟踪票范围，不是全市场强实体识别
4. **更稳的 alias / 曾用名 / 主题映射未完成**

---

## 4. 当前推荐怎么理解这块能力

### 如果服务端有 `TUSHARE_TOKEN`
- 公告 / 问答 / 新闻优先走 Tushare
- 覆盖更稳，新闻正文更完整

### 如果服务端没有 `TUSHARE_TOKEN`
- 公告：走新浪公告 / 业绩预告 fallback
- 问答：走新浪董秘问答 fallback
- 资讯：走新浪个股资讯 fallback

**结论：**
当前系统已经不再是“没 token 就基本没法用”，而是进入了：

## “没 token 也能用于盘后候选票研究”

但：
- 深度
- 稳定性
- 正文完整性

仍然是 **Tushare > 公共 fallback**。

---

## 5. 和选股模块的关系
当前这块已经能给选股模块提供：

1. **最近事件流**
2. **覆盖摘要**
3. **采集审计**
4. **按需触发补齐**

也就是说，现在已经能支撑：
- 候选票出来后再去拉它的事件
- 页面里展示事件来源
- 给后续 AI 解读做输入

但还**不能直接输出最终“为什么推荐这只票”的结构化事件结论**，因为事件理解层还没做。

---

## 6. 当前最重要的文档结论
截至 `2026-04-24`：

### 当前真实状态是
- `stock_events` 事件底座已成型
- 公告 / 问答 / 资讯三类都已接通
- 无 token fallback 已补到三类齐全
- 候选票按需触发入口已存在

### 当前未完成的是
- 事件理解层
- 更强的多票映射
- 更深的正文级资讯理解

