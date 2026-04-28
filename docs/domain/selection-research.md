# 选股研究与回测闭环

## 覆盖 CAP
- `CAP-SELECTION-RESEARCH`

## 当前正式结论
1. 选股研究结果写入独立库 `data/selection/selection_research.db`。
2. 候选、画像、回测接口已经存在，主链路可用。
3. 每日复盘决策已接入候选票研究上下文包：公司概况、决策解释、研究依据、事件覆盖、价格/L2 序列可统一查询。
4. 当前最大问题不是“有没有功能”，而是研究数据源覆盖和摘要质量还要继续打磨。

## 当前仍需继续做的
- 本地 L2 / stock_universe_meta 继续补齐
- 候选票事件依据继续提升正文级覆盖和去噪
- 公司概况/决策解释继续提升可验证性和历史版本化
- 回测与研究结果继续打磨到可稳定日用

## 当前变更：选股研究工作台 UI 密度改造（2026-04-25）
- 关联变更卡：`docs/changes/REQ-20260425-01-selection-ui-density-rework.md`
- 策略入口只保留“启动确认 Top10 / 吸筹前置 Top10”；出货风险不作为选股策略入口，后续应作为图上风险点或风险判断模块呈现。
- UI 优先级调整为：顶部操作栏 → 复用股票横卡 → 左候选 / 右波段复盘图。
- 本轮不改后端、不重写图表主体；已压缩右侧冗余信息与重复控制，并新增选股信号日图上标记。

## 当前变更：候选票研究上下文与新闻事件解释（2026-04-28 / v5.0.19）
- 关联变更卡：`docs/changes/REQ-20260427-03-selection-news-event-research-context.md`
- 正式接口：`GET /api/selection/research-context/{symbol}`、`POST /api/selection/research-context/{symbol}/prepare`、`POST /api/selection/research-context/prewarm`。
- Codex 查询脚本：`backend/scripts/dump_selection_research_context.py`。
- 页面主展示：`公司概况`、`决策解释`、`研究依据`，全部优先读持久化结果。
- 查询触发：点击选股页 `查询候选` 时预热买入候选与前 5 个观察候选；切票不重新生成。
- 体验修复：日期选择和候选刷新不再清空旧内容，已有研究摘要会保留到新版本生成完成。

