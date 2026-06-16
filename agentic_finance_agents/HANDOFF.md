# Agentic Finance Agents 新会话交接

## 结论

新开 Codex 会话后，先读本文件，再读 `DOCS_INDEX.md`。本目录定义的是 Codex 对话内调度的 A 股金融研究 Agent，不是前端页面功能，也不是正式数据库。

当前工作区：

```text
/Users/dong/ZhangData/market-live-terminal
```

当前分支：

```text
main
```

## 先读顺序

1. `agentic_finance_agents/DOCS_INDEX.md`
2. `agentic_finance_agents/README.md`
3. `agentic_finance_agents/ARCHITECTURE.md`
4. `agentic_finance_agents/registry/README.md`
5. `agentic_finance_agents/codex-agent-playbook.md`
6. 按任务类型读取 `workflows/company-research.md` 或 `workflows/industry-research.md`
7. 读取本次需要的 `agents/*.md`

页面产物读：

1. `agentic_finance_agents/agents/11-research-page-composer.md`
2. `agentic_finance_agents/schemas/research-ui-artifact.schema.md`

历史重跑读：

1. `agentic_finance_agents/schemas/research-history-storage.md`
2. 最近一次 `agentic_finance_agents/runs/<run_id>/final_report.md`
3. 最近一次 `agentic_finance_agents/runs/<run_id>/close_pack.md`

## 用户怎么发起研究

标准单公司研究：

```text
用 agentic_finance_agents 按新版单公司流程研究 <公司名/股票代码>。
```

带页面产物：

```text
研究 <公司名/股票代码>，并让 11 研究页面生成 Agent 输出 compact/full 页面产物。
```

再次研究同一公司：

```text
重新研究 <公司名/股票代码>，先查历史 run，并和上次研究结论做对比。
```

更严格的提示词：

```text
用 agentic_finance_agents 按新版单公司流程研究 <公司>。
要求：
1. 每个 Agent 独立输出 Markdown 和 JSON。
2. 04/06 必须输出盈利桥、估值分母桥、同业估值位置。
3. 07 做事实和估值口径对账。
4. 08 做可晋级字段和缺口收口。
5. 需要页面时运行 11，输出 compact/full HTML。
```

## 已定规则

1. 官方参照是 10 个金融 Agent；本项目新增第 11 个 `研究页面生成 Agent`。
2. 研究入口是 Codex 对话，不是在系统页面上点 Agent。
3. 每个 Agent 应独立产出自己的结论、证据、缺口和 JSON。
4. 主控负责调度、打回、对账和汇总，不能假装一个人写完整报告就是多 Agent。
5. 临时产物放在 `agentic_finance_agents/runs/`，不自动进入正式页面或数据库。
6. 估值研究不能只报当前 PE；必须看历史利润分母、TTM、单季年化、同业位置和可持续性。

完整准绳见 `DOCS_INDEX.md` 的“单一事实来源”表。

## 当前已知不足

2026-06-16 恢复后核查：当前仓库恢复了 Agent 定义、流程、schema 和页面产物规范；本轮新增了 1 个 `sz002137 / 实益达` 候选级 UI run，用于验证 `research_ui_manifest.json`、`compact.html` 和 `full.html` 的读取链路。

历史文档里提到的振德医疗和粤桂股份两次示范 run，即便后续找回，也仍不算生产级：

- Agent JSON 不完整。
- `evidence_cache.jsonl` 和 `retrieval_log.jsonl` 基本为空。
- 估值桥、同业位置、历史对比还不够深。
- 页面产物尚未对历史 run 生成。
- 研究结果尚未进入独立 `company_research.db`。
- 主应用已具备候选级只读接入链路，但只有 1 个样例 run；尚未形成批量正式研究库。

后续新研究应按新版要求重跑，不要复用旧示范 run 的质量标准。

## 冲突处理

如果本文件和其他文档冲突，以 `DOCS_INDEX.md` 里列出的准绳文件为准。本文件只负责交接，不负责承载完整流程。
