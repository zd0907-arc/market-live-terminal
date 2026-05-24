# 市场热点板块口径管理机制

> 提示：这份文档是 `market_heat` 模块自己的口径与维护说明，不是整个项目的总入口。
> 这里提到的 `build_stock_sector_map.py`、`build_tradable_theme_map.py` 属于模块维护脚本，不属于 `docs/04_OPS_AND_DEV.md` 里的正式日常白名单脚本。
> 当前页面正式消费链路是 `tradable_theme_map.db + fine_heat_snapshots_* + /api/market_heat/fine_dashboard`；专题趋势页、回测页、案例页都不在这条默认链路里。

## 结论

热点板块不直接相信任何单一数据源。东财板块继续作为动态概念主源，但热点页和研究只使用经过清洗、去重和 canonical 治理后的主题池。

## 当前数据链路

```text
东财公开板块/个股所属板块接口
→ stock_sector_map.db
→ sector_clean_rules.json
→ fine_hotspot_rules.json
→ theme_canonical_rules.json
→ fine_heat_snapshots_*_m5_80.json
→ 热点页 / 回测 / 研究
```

当前本地源头：

- 原始库：`/Users/dong/Desktop/AIGC/market-data/market_heat/stock_sector_map.db`
- 清洗库：`/Users/dong/Desktop/AIGC/market-data/market_heat/tradable_theme_map.db`
- 原始来源字段：`eastmoney.push2`
- 当前原始库生成时间：2026-04-29 13:34
- 当前清洗库生成时间：2026-04-29 14:41
- 当前 canonical 后细颗粒主题数：633
- 当前页面使用缓存示例：`/Users/dong/Desktop/AIGC/market-data/market_heat/cache/fine_heat_snapshots_2026-01-28_2026-05-11_m5_80.json`

## 为什么会有航天装备Ⅱ/Ⅲ

这不是因为混用了同花顺和东财。

当前库里 `航天装备Ⅱ` 和 `航天装备Ⅲ` 的来源都是东财，且都是 `industry`。它们来自东财行业分层体系里的不同层级；当某个二级行业没有进一步有效拆分时，二级和三级行业的成分股可能完全一样。

本轮核验：

- `航天装备Ⅱ`：5只
- `航天装备Ⅲ`：5只
- 成分股重合：100%

因此它们不是两个有效热点，只能展示一个 canonical 主题。

## 三层板块体系

### 1. 原始源层

保留东财原始结果，不直接改写。

职责：

- 抓取行业、概念和个股所属板块。
- 记录来源和抓取时间。
- 允许定期或手动刷新。

不承诺：

- 名称稳定。
- 层级无重复。
- 所有标签都有交易意义。

### 2. 清洗层

由 `sector_clean_rules.json` 和 `fine_hotspot_rules.json` 控制。

当前规则：

- 剔除指数、地域、交易属性、机构持仓、财报预告、风格标签。
- 细颗粒热点默认保留成员数 5~80 只。
- 过大板块只做背景，不作为细颗粒热点。
- 过小板块可以观察，但不应高置信度解读。

### 3. canonical 治理层

由 `theme_canonical_rules.json` 控制。

职责：

- 成分股完全一致的板块，只保留一个 canonical。
- Jaccard >= 0.90 的高度近重复板块，自动只保留一个 canonical。
- Jaccard 0.75~0.90 或小板块覆盖率很高的板块，进入人工审计。
- 原始 alias 不删除，只是不参与热点展示和研究排名。

## 当前自动处理规则

```text
exact duplicate:
  成分股100%一致 → 自动保留一个 canonical

near duplicate:
  交集/并集 >= 0.90 且交集 >= 5 → 自动保留一个 canonical

review only:
  0.75 <= Jaccard < 0.90
  或 小板块95%以上被大板块覆盖
```

canonical 选择原则：

1. 优先去掉 `Ⅱ/Ⅲ/I/II/III/2/3` 这类层级后缀。
2. 同等情况下优先更短、更清晰的名称。
3. 同等情况下优先行业口径。
4. 不做成分股并集，不把不同板块粗暴合并。

## 更新方式

不固定周期。只有在下面这些场景才需要手动执行：

1. 东财板块映射明显变了，需要重建原始映射；
2. 主题清洗规则或 canonical 规则变了，需要重建 `tradable_theme_map.db`；
3. 页面主题池明显不合理，且判断不是单纯缓存没刷新。

维护命令：

```bash
python3 backend/scripts/build_stock_sector_map.py --source stock-plate --types concept,industry --sleep 0.03
python3 backend/scripts/build_tradable_theme_map.py
```

如果只是交易日数据已经跑完，需要刷新市场热点页面缓存，不需要重建板块关系，直接在页面点 `刷新最新数据`，或调用：

```bash
curl -X POST 'http://127.0.0.1:8000/api/market_heat/fine_dashboard/refresh?days=63&force=true'
```

刷新后必须检查：

1. 原始板块数是否异常变化。
2. 成分股关系数是否异常变化。
3. 完全重复组数量。
4. 高重合审计名单。
5. 新增大板块是否应降为背景层。
6. 新增热点概念是否应加入白名单。
7. 最新交易日 `fine_dashboard` 的 6 池结果是否符合市场直觉，尤其是首次新热、主线再加速和退潮观察。

## 页面生命周期口径

页面不再直接展示原始热点排行，而是把细颗粒主题分成 6 个池子：

| 池子 | 用途 |
|---|---|
| 今日最强 | 当日 Top5，回答“今天最强在哪里” |
| 首次新热 | 过去 20 日少热、今天进入 Top15，回答“今天新冒出来什么” |
| 主线再加速 | 近 20 日已反复活跃、今天进入 Top10，回答“老主线是否重新打到前排” |
| 持续升温 | Top6~Top30 且近 5 日明显改善，回答“哪些正在升温但还没成熟” |
| 持续主线 | 仍在 Top30 且近 20 日反复活跃，回答“哪些还在打” |
| 退潮观察 | 跌出 Top30 且近期从前排掉队，回答“哪些主线在退潮” |

阈值治理：

```text
Top5  = 当日最强
Top10 = 前排强热点
Top15 = 热区
Top30 = 观察边界
```

Top30 不能单独解释为强热点，只能配合近 20 日命中次数、近 5 日热度变化和当前排名使用。

## 多数据源原则

如果未来接入同花顺、Choice、Wind、申万或中证：

- 不允许直接把同名板块混进现有东财ID。
- 每个来源保留独立 source namespace。
- 用成分股重叠率判断是否是 alias、子集、补充源或冲突源。
- 只有进入 canonical 规则后，才允许进入热点页。

建议定位：

```text
东财概念 = 动态热点发现主源
申万/中证/证监会行业 = 稳定背景和行业归类
自定义主题 = 交易研究沉淀
canonical规则 = 最终展示与策略使用口径
```

## 不能做的事

- 不把成员数几百只的大标签当成细颗粒热点。
- 不把完全重复的Ⅱ/Ⅲ层级同时展示。
- 不因为名字像就自动合并。
- 不把不同来源的同名板块直接覆盖。
- 不让原始数据源变化直接影响策略口径，必须先过审计。
