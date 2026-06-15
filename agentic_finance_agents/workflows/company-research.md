# 单公司研究流程

## 启动语句示例

用户可以在 Codex 里直接说：

```text
用 agentic_finance_agents 的 10 个 Agent 研究 sh600519，标准深度。
```

或：

```text
帮我跑一次宁德时代的单公司研究，重点看财务质量、估值和行业位置。
```

或：

```text
研究这家公司，并告诉我它过去股价主要跟什么走。
```

## Codex 应做的事

1. 识别股票代码和公司名称。
2. 建立 `runs/<run_id>/`。
3. 由 `02 任务拆解与研究 Brief Agent` 明确研究边界、信息来源清单和建议调用名单。
4. 初始化 `evidence_cache.jsonl` 和 `retrieval_log.jsonl`。
5. 按 `workflows/codex-orchestration.md` 调度 Agent；财报、公告、互动问答、行业、价格/L2、估值、股价驱动、风险材料由各负责 Agent 自行读取。
6. 由 `07 事实一致性对账 Agent` 检查冲突、缺来源和口径问题。
7. 必要时打回对应 Agent 补充或重写。
8. 由 `01 研究总签 Agent` 按 `schemas/company-final-report-template.md` 生成最终报告，`08 研究收口与晋级 Agent` 生成收口包。
9. 如用户需要页面展示，再由 `11 研究页面生成 Agent` 读取收口后的研究产物，生成 `ui/compact.html`、`ui/full.html` 和 `ui/research_ui_manifest.json`。

## 输出最小集合

- `00-meeting-brief.md`
- `run_context.json`
- `source_registry.json`
- `evidence_cache.jsonl`
- `retrieval_log.jsonl`
- `agents/*.md`
- `agents/*.json`
- `final_report.md`
- `close_pack.md`
- 按需：`ui/compact.html`
- 按需：`ui/full.html`
- 按需：`ui/research_ui_manifest.json`

## 最终报告必须回答

1. 公司是做什么的。
2. 收入从哪里来，按产品/地区/渠道尽量拆开。
3. 利润主要来自什么，区分毛利贡献、费用、减值、非经常损益、汇兑或资产处置。
4. 财务基本盘如何，包括增长、现金流、应收、存货、减值、商誉、负债、分红和资本开支。
5. 股价过去主要跟什么走，并给出驱动因子、证据、可信度和跟踪方式。
6. 接下来最应该盯哪些变量。
7. 估值分母如何变化：上一完整年度、TTM、最新季度扣非年化、同业/行业对比。

## 人工审阅方式

用户可以按下面顺序看：

1. `00-meeting-brief.md`：确认研究边界是否对。
2. `agents/03-earnings-reviewer.md`、`09-statement-auditor.md`：确认财报、管理层信号和财务质量。
3. `agents/05-market-researcher.md`：确认行业和市场环境。
4. `agents/06-valuation-reviewer.md`：确认估值是否靠谱，以及股价驱动归因是否成立。
5. `agents/07-gl-reconciler.md`：确认有没有数据冲突。
6. `final_report.md`：看最终结论。
7. `close_pack.md`：看还有哪些缺口，以及哪些字段可以晋级。
8. `ui/compact.html`、`ui/full.html`：看页面表达是否可用。

## 历史研究对比

再次研究同一家公司时，`02 任务拆解与研究 Brief Agent` 必须先查找最近一次 closed run，并把旧结论作为对比对象。最终报告必须补一节：

- 上次研究时的核心主线。
- 本次研究主线是否变化。
- 收入/利润/现金流/估值/股价驱动/风险分别发生了什么变化。
- 哪些旧判断被证实、被削弱或被推翻。
