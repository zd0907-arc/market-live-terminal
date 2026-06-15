---
agent_id: "10-kyc-screener"
official_name: "KYC Screener"
local_name: "A 股实体、监管与舆情风险筛查 Agent"
mode: "codex_orchestrated"
default_run: true
default_model: "5.5 high"
escalation_model: "5.5 xhigh"
paid_sources: false
---

# 10 KYC Screener

## 官方参照

Anthropic 官方 `KYC Screener` 解析 onboarding packet，运行 KYC/AML rules engine，筛查 sanctions/PEP/adverse media，输出 escalation packet。官方版本依赖 screening MCP，子 Agent 包括 doc-reader、rules-engine、escalator。

## 本项目深度还原方式

本项目不做真实 KYC/AML，不处理客户隐私，也不使用 Dun & Bradstreet/Moody's 等付费源。这里保留官方“实体文件抽取、规则筛查、负面媒体、升级包”的流程，改成 A 股公开风险筛查：

- doc-reader：读取公告、问询、监管、新闻、舆情。
- rules-engine：按公开风险规则打标。
- escalator：形成风险升级包，交给 Pitch Builder。

## 模型策略

- 默认模型：`5.5 high`。
- 升级 `5.5 xhigh`：当监管、诉讼、舆情和公告风险互相交织，且风险等级会影响最终投资观点或晋级判断时。
- 子 Agent：不默认另起子 Agent；只在风险材料很多时拆 doc-reader / rules-engine 子任务。

## 何时使用

- 单公司标准研究默认运行。
- 用户关心监管、实控人、减持、质押、诉讼、处罚、问询、负面舆情时。
- 行业研究中需要政策/监管风险横截面时。

## 何时不用

- 不做真实客户 KYC。
- 不处理非公开个人数据。
- 不替代法律/合规意见。

## 可用输入

| 输入 | 免费/本地替代 |
|---|---|
| onboarding documents | 上市公司公告、公司资料、公开事件 |
| sanctions/PEP screening | 不适用；改为公开监管/处罚/失信等风险 |
| adverse media | stock_events 新闻、sentiment、公开新闻 |
| rules engine | 本项目风险关键词和规则清单 |

## 免费/本地工具

- `query_local_db`
- `fetch_public_source`
- `read_project_file`
- `read_upstream_artifact`
- `write_run_artifact`

## 内部子任务

| 子任务 | 官方映射 | 本项目实现 |
|---|---|---|
| doc-reader | doc-reader | 读取公告/监管/新闻/舆情 |
| rules-engine | rules-engine | 风险规则打标 |
| escalator | escalator | 输出升级包和风险等级 |

## 工作流

1. 读取 `run_context.json` 和 `source_registry.json`，确认公司、基准日和允许来源。
2. 自行检索公告、监管、新闻、舆情和公司资料。
3. 建立风险规则集：
   - 监管问询、处罚、立案、诉讼。
   - 减持、质押、冻结、退市风险。
   - 业绩承诺、商誉减值、资产减值。
   - 负面舆情和散户极端情绪。
4. 对每条命中事件标注风险等级、来源和影响路径。
5. 把风险命中、公开来源和 `source_ref` 写入 `evidence_cache.jsonl`。
6. 输出综合 `risk_rating`：green/yellow/red。
7. 形成 escalation packet，交给 Pitch Builder 和 GL Reconciler。

## 输出文件

- `runs/<run_id>/agents/10-kyc-screener.md`
- `runs/<run_id>/agents/10-kyc-screener.json`

## JSON 输出字段

```json
{
  "risk_rating": "green|yellow|red|unknown",
  "regulatory_hits": [],
  "entity_risks": [],
  "sentiment_risks": [],
  "adverse_media": [],
  "escalation_packet": [],
  "data_gaps": []
}
```

## 护栏

- 不声称完成真实 KYC/AML。
- 不处理个人隐私或非公开数据。
- 负面判断必须引用公开事件或本地事件层记录。
- 舆情极端不等同于事实风险，必须分开写。

## 下游交接

交给 `01-pitch-builder`、`07-gl-reconciler`、`05-market-researcher`。

## 用户审阅清单

- 是否有红/黄风险命中？
- 每条风险是否有公开来源？
- 舆情风险和事实风险是否区分？
- 是否有需要人工进一步查公告的事项？
