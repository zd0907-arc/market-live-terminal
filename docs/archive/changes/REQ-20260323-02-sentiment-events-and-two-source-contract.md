# REQ-20260323-02-sentiment-events-and-two-source-contract

> ⚠️ 本卡保留为 **阶段性设计记录**。其中“两源接入”已不再代表当前正式范围；当前真实状态请优先查看：
> `docs/changes/MOD-20260324-01-retail-sentiment-v2-current-state.md`

## 1. 基本信息
- 标题：散户一致性观察 V2 Phase 1（统一事件模型 + 两源契约）
- 状态：ACTIVE
- 负责人：AI / Dong
- 关联 Task ID：`CHG-20260323-01`
- 关联 CAP：`CAP-RETAIL-SENTIMENT`
- 关联 STG：`STG-20260323-01-retail-sentiment-v2-heat-event-stream`

## 2. 背景与目标
- 目标：把散户舆情底座从“股吧主帖标题流”升级成可兼容股吧/雪球/同花顺的统一事件流。

## 3. 方案与边界
- 做什么：
  - 新增 `sentiment_events`
  - 事件字段冻结：
    - `event_id / source / symbol / event_type / thread_id / parent_id / content / author_name`
    - `pub_time / crawl_time`
    - `view_count / reply_count / like_count / repost_count`
    - `raw_url / source_event_id / extra_json`
  - 同源内唯一键冻结为 `source + source_event_id`
  - 旧 `sentiment_comments` 迁移/兼容回填到 `sentiment_events`
  - 股吧升级抓 `主帖 + 回复正文`
  - 雪球按同模型落 `主帖 + 评论`
- 不做什么：
  - 不做跨源去重
  - 不做同花顺抓取实现

## 4. 验收标准
- Given `2026-03-24 21:00`，When 执行旧股吧存量回填，Then `sentiment_events` 中可看到 `source=guba,event_type=post` 的兼容数据。
- Given `2026-03-24 21:10`，When 新抓股吧某线程，Then 主帖与回复都以独立事件落库，并能通过 `thread_id / parent_id` 关联。
- Given 雪球抓取成功，When 落库事件，Then 不需要新增第二套前端 schema。

## 5. 风险与回滚
- 风险：两源返回字段不一致时，弱字段必须允许为空，不能强行同构成脏值。
- 回滚：允许暂停雪球抓取，但 `sentiment_events` 保留为正式主模型。

## 6. 实施回填
- 已完成：
  - `sentiment_events` 表与索引已落地；
  - 旧 `sentiment_comments` 可按 symbol 懒回填到 `sentiment_events`；
  - 当前股吧抓取新增的主帖事件会同步写入 `sentiment_events`；
  - 股吧线程详情页已可解析 `post_article`，主帖正文不再只用列表标题；
  - 雪球已落 best-effort 适配器骨架：当配置 `XUEQIU_COOKIE` 时，可尝试抓 `statuses/search.json + statuses/comments.json`。
- 未完成：
  - 股吧回复正文仍受上游 reply API `系统繁忙[00003]` 影响，当前只能 best-effort 抓取；
  - 雪球在无 cookie / 被 WAF 挑战时会软失败，不保证当前环境一定有数据。
