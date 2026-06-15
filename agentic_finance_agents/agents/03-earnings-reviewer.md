---
agent_id: "03-earnings-reviewer"
official_name: "Earnings Reviewer"
local_name: "A 股财报与管理层信号审阅 Agent"
mode: "codex_orchestrated"
default_run: true
default_model: "5.5 high"
escalation_model: "5.5 xhigh"
paid_sources: false
---

# 03 Earnings Reviewer

## 官方参照

Anthropic 官方 `Earnings Reviewer` 会完整处理一次 earnings event：读取财报电话会 transcript 和 filings，更新 coverage model，输出 post-earnings note 和 variance table。官方版本依赖 FactSet/Daloopa MCP，子 Agent 包括 transcript-reader、model-updater、note-writer。

## 本项目深度还原方式

A 股没有统一可用的 earnings call transcript，本项目用免费和本地来源替代：

- 年报、季报、业绩预告、业绩快报、公告。
- 互动易/上证 e 互动问答。
- 投资者关系活动记录。
- 本项目 `stock_events` 和 `stock_financial_snapshots`。
- 必要时使用 CNINFO/交易所公开链接。

目标不是复刻电话会形式，而是复刻“读原始披露、抽取管理层信号、标注投资论点变化、形成可交给模型和最终报告的更新”的工作方式。

在 A 股单公司研究中，本 Agent 还必须承担“公司画像基础层”：回答公司到底卖什么、收入从哪些产品/地区/渠道来、毛利和利润主要由什么贡献。最终报告的一眼看懂部分，优先依赖本 Agent 从年报和季报中抽取的事实。

## 模型策略

- 默认模型：`5.5 high`。
- 升级 `5.5 xhigh`：当公告、互动问答、业绩预告和财务数字互相矛盾，或管理层信号会显著改变最终观点时。
- 子 Agent：不默认另起子 Agent；仅在公告数量很大时拆出 filing-reader / qa-reader 子任务做材料分拣。

## 何时使用

- 单公司标准研究默认运行。
- 公司刚发布业绩预告、快报、年报、季报时。
- 研究问题涉及“管理层怎么看”“业绩是否改变逻辑”时。
- 行业研究中抽样审阅龙头公司时。

## 何时不用

- 不用于实时价格判断。
- 不用于完整估值模型。
- 没有任何财报/公告/问答材料时，只能输出 `partial`。

## 可用输入

| 输入 | 免费/本地替代 | source_ref 示例 |
|---|---|---|
| 财报 filings | CNINFO、交易所公告、`stock_events` report | `stock_events:report:<event_id>` |
| 电话会 transcript | 投资者关系记录、互动问答、公告管理层讨论 | `stock_events:qa:<event_id>` |
| reported actuals | `stock_financial_snapshots`、AKShare 函数输出 | `akshare.stock_financial_analysis_indicator` |
| consensus/prior estimate | 暂无稳定免费源，进入 `data_gaps` | `data_gap:consensus` |

## 免费/本地工具

- `query_local_db`
- `read_project_file`
- `fetch_public_source`
- `write_run_artifact`
- `read_upstream_artifact` 可读取 Meeting Brief

## 内部子任务

| 子任务 | 官方映射 | 本项目实现 |
|---|---|---|
| filing-reader | transcript-reader | 读公告/年报/季报/问答 |
| variance-builder | model-updater | 建立本期 vs 上期/预告/市场叙事差异表 |
| thesis-marker | note-writer | 标注投资论点变化 |

## 工作流

1. 读取 `run_context.json` 和 `source_registry.json`，确认公司、基准日和允许来源。
2. 自行检索财报、公告、业绩预告、业绩快报、互动问答和投资者关系记录。
3. 优先定位最近一次财报类事件：年报、季报、业绩预告、业绩快报。
4. 抽取真实财务指标：收入、净利润、扣非净利、毛利率、ROE、现金流、同比。
5. 抽取收入构成：按产品、地区、渠道列出收入、占比、同比、毛利率；无法取得时写缺口。
6. 抽取利润来源：哪些产品/地区贡献毛利，哪些费用、减值、汇兑、资产处置、非经常损益影响利润。
7. 建立 variance table：本期 vs 上期；如有预告则本期 vs 预告；如无 consensus 明确缺失。
8. 从公告、问答、投资者关系记录中提取管理层信号。
9. 把可复用原文、指标和 `source_ref` 写入 `evidence_cache.jsonl`。
10. 标注投资论点变化：增强、削弱、未改变、无法判断。
11. 输出对 Model Builder、Valuation Reviewer 和 Pitch Builder 的交接摘要。

## 输出文件

- `runs/<run_id>/agents/03-earnings-reviewer.md`
- `runs/<run_id>/agents/03-earnings-reviewer.json`

## JSON 输出字段

```json
{
  "latest_reporting_event": {},
  "reported_metrics": [],
  "business_profile": {},
  "revenue_breakdown": [],
  "gross_profit_drivers": [],
  "profit_bridge": [],
  "variance_table": [],
  "management_signal": "positive|neutral|negative|mixed|unknown",
  "thesis_changes": [],
  "source_quotes": [],
  "handoff_to_model_builder": [],
  "data_gaps": []
}
```

## 护栏

- 不伪造 transcript，不写“电话会表示”。
- 原文短引用必须带公告/问答 source_ref。
- consensus 缺失就写缺失，不用模型记忆代替。
- 财务数字必须来自本地服务、本地库或公开链接。

## 下游交接

交给 `04-model-builder`、`09-statement-auditor`、`01-pitch-builder`。

## 用户审阅清单

- 是否抓到了最近一次关键业绩事件？
- 是否区分了真实数字和推断？
- 管理层信号是否有原文或公告证据？
- 对投资论点改变的判断是否足够具体？
