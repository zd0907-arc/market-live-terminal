# MOD-20260507-02 厄尔尼诺长期趋势线索接入

## 1. 结论
- 新增 `el_nino` 长期趋势线索：厄尔尼诺 / 气候异常。
- 当前判断：2026 年中后段发生概率上升，但不是必然；阶段为“概率上升 / 预警期”。
- 研究动作：进入长期趋势观察池，先跟踪 ENSO 官方更新、农产品价格、水利节水、电力制冷和气候风险管理。

## 2. 本轮范围
- 新增研究卡：`docs/selection/long_term_trends/cases/el_nino_2026-05-07.md`
- 新增长期趋势话题 SOP：`docs/selection/long_term_trends/08_topic_research_sop.md`
- 新增深度研究计划：`docs/selection/long_term_trends/cases/el_nino_2026-05-07_deep_plan.md`
- 新增页面日报：`docs/selection/long_term_trends/el_nino/el_nino_tracking_report_2026-05-07.md`
- 新增结构化跟踪数据：`data/selection/long_term_trends/el_nino/`
- 接入趋势研究 API：`GET /api/trend-research/ideas/{idea_id}/dashboard` 支持 `el_nino`。
- 趋势研究页对空模块做条件渲染，避免宏观线索显示一堆空的 A 股/估值模块。
- 按评论/市场讨论补入橡胶链：海南橡胶为 A 类核心观察，轮胎股为 C 类成本压力旁路。
- 2026-05-09 补充橡胶长周期研究：World Bank 月度 RSS3 数据显示 2011-02 高点约为 2026-04 的 2.5 倍，2011 式行情来自需求、天气、低库存、高油价和流动性共振，不应只按厄尔尼诺单因子外推。
- 2026-05-09 继续补充：解释 RU/NR/主力/主连，接入 RU/NR 主连行情、价差和 2024 以来价格阶段；基于 NOAA ONI + World Bank 商品价格做历史厄尔尼诺事件后 12 个月商品表现统计，初步收敛优先级为橡胶、棕榈油/油脂、粮食种业/水利抗旱。

## 3. 边界
- 这不是买入建议，也不是自动交易信号。
- 当前没有建立 A 股个股横评；等 ENSO 和商品/行业数据确认后再做。
- 关键下一次复核：2026-05-14 NOAA/CPC 更新。

## 4. 验证
- `python3` 调用 `list_trend_ideas()`：返回 `storage`、`el_nino`、`power`。
- `python3` 调用 `get_trend_dashboard("el_nino")`：返回 6 条产业链、17 个观察池标的。
- `npm run check:version`：通过。
- `npm run build`：通过。
