# 长期研究跟踪清单

## 定位

这是“研究后持续盯盘”的轻量机制，不做复杂交易系统。

核心用法：

1. Codex 对话完成单票研究。
2. 把研究结论写入 `data/selection/research_watchlist/watchlist.json`。
3. 每天用脚本生成关注票快照。
4. 页面后续只读取清单、快照和现有图表数据，辅助人工判断是否买入、加仓、减仓或卖出。

## 数据文件

- 清单：`data/selection/research_watchlist/watchlist.json`
- 每日快照：`data/selection/research_watchlist/snapshots/YYYY-MM-DD.csv`
- 每日盯盘笔记：`docs/selection/research_watchlist/daily/YYYY-MM-DD.md`

## 单票状态

| 状态 | 含义 |
| --- | --- |
| `watching` | 已纳入长期关注，等待买点或基本面验证。 |
| `ready` | 条件接近触发，需重点盯盘。 |
| `holding` | 已买入，后续记录加减仓和退出。 |
| `closed` | 已卖出或结束跟踪。 |
| `paused` | 暂停跟踪，但保留研究档案。 |

## 每天看什么

系统自动汇总：

- 收盘价、涨跌、成交额
- 3/5/10/20 日涨幅
- 距 20 日线、60 日线位置
- L2 主力净额、超级单净额
- OIB/CVD、买撑/卖压
- 突破分、出货分、exit signal

人工补充：

- 当天新闻和公告
- 行业价格变化
- 研究结论是否变化
- 是否触发买入、加仓、减仓、卖出

## 当前首个跟踪标的

- 德明利 `sz001309`
- 研究档案：`docs/selection/litong_similarity/sz001309-德明利.md`
- 核心变量：后续季度成本率、毛利率、存储价格、企业级 SSD 订单持续性

## 生成快照

```bash
python3 backend/scripts/build_research_watchlist_snapshot.py
```

默认读取最新可用交易日。也可以指定日期：

```bash
python3 backend/scripts/build_research_watchlist_snapshot.py --date 2026-04-30
```
