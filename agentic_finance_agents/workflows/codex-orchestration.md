# Codex 调度工作流

## 目标

用户通过 Codex 对话启动研究，不通过前端页面点击。Codex 主控负责理解用户问题、选择该叫哪些 Agent、派出独立子 Agent 或分批任务、检查结果、必要时打回重写，最后汇总给用户。

主控不替 Agent 做一线分析，不预拉全量资料包，不把临时产物写入正式库。

## 总流程

1. **确认任务**
   - 单公司：规范化为 `sh/sz/bj + 6位代码`
   - 行业/赛道：明确范围、成分股、研究角度
   - 不清楚时先列假设

2. **创建 run 目录**
   - 路径：`agentic_finance_agents/runs/<run_id>/`
   - 写入 `run_manifest.json`

3. **读取 Agent 手册**
   - 读取 `codex-agent-playbook.md`
   - 按需要读取 `agents/*.md`
   - 不需要用户理解或操作任何页面功能

4. **任务拆解与研究 Brief Agent**
   - 输出 `00-meeting-brief.md`
   - 写入 `run_context.json`
   - 写入 `source_registry.json`
   - 给出本次建议调用哪些 Agent

5. **初始化证据缓存**
   - 先读取 `tools/free-data-and-tools.md`，确认允许使用的本地和免费来源
   - 不预先拉取全量价格、L2、财务、公告、问答、新闻
   - 创建空的 `evidence_cache.jsonl` 和 `retrieval_log.jsonl`
   - 后续由各 Agent 按职责自取数、写证据、写缺口

6. **调度 Agent**
   - 标准公司研究建议顺序：
     - `02 任务拆解与研究 Brief Agent`
     - 并行或依次：`03 财报与管理层信号 Agent`、`05 市场与行业研究 Agent`、`09 财务质量审查 Agent`、`10 实体、监管与舆情风险 Agent`
     - 然后：`04 轻量财务建模 Agent`、`06 估值核查 Agent`
     - 质量检查：`07 事实一致性对账 Agent`
     - 最终签发：`01 研究总签 Agent`
     - 收口：`08 研究收口与晋级 Agent`
     - 页面表达：如用户要进入页面或卡片，再运行 `11 研究页面生成 Agent`

7. **保存输出**
   - 短研究可以直接在对话里输出各 Agent 小结
   - 正式研究再写 Markdown + JSON，例如 `agents/03-financial-signal.md`
   - 每个 Agent 把可复用事实写入 `evidence_cache.jsonl`
   - 每个 Agent 把取数动作写入 `retrieval_log.jsonl`
   - 每个 Agent 结果要能被单独阅读

8. **审阅与打回**
   - 主控或 `07 事实一致性对账 Agent` 指出冲突、来源缺失或口径问题
   - 不合格时，让对应 Agent 补充或重写
   - 缺数据时明确写缺口，不用模型记忆补数

9. **最终汇报**
   - `final_report.md`
   - `promotion_candidates.json`
   - `close_pack.md`

## 标准单公司调度矩阵

| 阶段 | Agent | 中文名 | 是否默认运行 | 说明 |
|---|---|---|---:|---|
| 0 | Meeting Preparer | 任务拆解与研究 Brief Agent | 是 | 任务边界和建议调用名单 |
| 1 | Earnings Reviewer | 财报与管理层信号 Agent | 是 | 财报/公告/互动问答 |
| 1 | Market Researcher | 市场与行业研究 Agent | 是 | 市场环境和行业/主题 |
| 1 | Statement Auditor | 财务质量审查 Agent | 是 | 利润质量和财务风险 |
| 1 | KYC Screener | 实体、监管与舆情风险 Agent | 是 | 监管合规舆情 |
| 2 | Model Builder | 轻量财务建模 Agent | 是 | 依赖财务和市场输入 |
| 2 | Valuation Reviewer | 估值与股价驱动核查 Agent | 是 | 依赖模型、同业、价格、事件和主题输入 |
| 3 | GL Reconciler | 事实一致性对账 Agent | 是 | 数据一致性检查 |
| 4 | Pitch Builder | 研究总签 Agent | 是 | 最终报告 |
| 5 | Month-end Closer | 研究收口与晋级 Agent | 是 | run 收口和晋级建议 |
| 6 | Research Page Composer | 研究页面生成 Agent | 按需 | 生成页面可嵌入 compact/full HTML，不负责一线研究 |

## 模型策略

| 规则 | 说明 |
|---|---|
| 默认模型 | 每个 Agent 独立决策时默认使用 `5.5 high` |
| 升级模型 | 遇到复杂推理、关键冲突裁决、正式晋级判断时可升级 `5.5 xhigh` |
| 子 Agent | 不默认为每个 Agent 再开子 Agent；只有长材料分拣、大样本行业拆解、多源冲突复核时，才作为该 Agent 的内部子任务临时拆分 |
| 记录要求 | Agent 输出中必须记录是否升级模型、升级原因、是否拆内部子任务 |

## 取数责任

| 信息类型 | 主要负责 Agent | 取数口径 |
|---|---|---|
| 公司基本资料 | Meeting Preparer / KYC Screener | 只取识别研究对象所需的最小资料；公司画像由相关 Agent 按需补齐 |
| 财报、公告、业绩预告 | Earnings Reviewer | 自行读取 `stock_events`、CNINFO/交易所、公开公告聚合 |
| 互动问答、投资者关系记录 | Earnings Reviewer | 自行读取互动易、上证 e 互动、董秘问答聚合或本地事件层 |
| 管理层信号 | Earnings Reviewer | 从公告、MD&A、互动问答、投资者关系记录中抽取，不作为独立原始源 |
| 财务质量、利润含金量 | Statement Auditor | 自行读取财务快照、年报/季报字段和上游披露证据 |
| 行业、政策、赛道环境 | Market Researcher | 自行读取 market_heat、trend_research、公开政策/行业资料和同业公告 |
| 股价、L2、估值、同业、股价驱动归因 | Valuation Reviewer / Market Researcher | 需要时自行读取本地价格、L2、财务、同业候选、事件和主题热度 |
| 监管、舆情、实体风险 | KYC Screener | 自行读取监管公告、处罚问询、新闻、sentiment 和公开来源 |
| 页面图文表达 | Research Page Composer | 只读取已收口研究产物，不自行新增金融事实 |

## 研究结果保存和复查

正式 run 不是只给对话结论。所有 Agent 输出都必须可按公司和时间回查：

- `agents/<agent_id>.md`
- `agents/<agent_id>.json`
- `evidence_cache.jsonl`
- `retrieval_log.jsonl`
- `final_report.md`
- `promotion_candidates.json`
- `close_pack.md`
- 如运行 11：`ui/compact.html`、`ui/full.html`、`ui/research_ui_manifest.json`

后续独立研究库方案见 `schemas/research-history-storage.md`。在正式库实现前，`runs/` 是唯一可追溯存档。

## 行业/赛道调度矩阵

行业研究默认弱化单公司财报和估值，强化市场与公司映射：

| Agent | 处理方式 |
|---|---|
| Meeting Preparer | 明确赛道边界和成分股 |
| Market Researcher | 主 Agent |
| Earnings Reviewer | 抽样审阅龙头/代表公司 |
| Statement Auditor | 只对样本公司做财务质量横截面 |
| Model Builder | 可跳过或仅做行业收入/利润驱动框架 |
| Valuation Reviewer | 做行业估值区间和龙头对比 |
| KYC Screener | 查监管/政策/负面风险 |
| GL Reconciler | 检查样本和来源一致性 |
| Pitch Builder | 输出赛道报告 |
| Month-end Closer | 收口 |

## 失败处理

- 单个 Agent 失败：说明失败原因，下游只能在缺口可接受时继续。
- 单个 Agent 证据不足：标注 `partial`，最终报告必须说明缺口。
- `run_context.json` 或 `source_registry.json` 失败：停止 run，不生成投资观点。
- 来源冲突：交给 `07 事实一致性对账 Agent`，未解决前不得晋级。

## 主控禁止事项

- 不把 10 个 Agent 的分析直接写在同一轮主线程回答里。
- 不把完整主线程聊天作为所有 Agent 的共享上下文。
- 不把“我扮演 10 个角色”伪装成真正的 Agent 调度。
- 不在关键冲突未处理前生成确定性结论。

## 不做的事

- 不开发页面交互。
- 不把临时 run 写回正式库。
- 不把 Agent 输出当自动交易信号。
- 不绕过项目三端边界直接查询 Windows 主库。
- 不调用付费金融数据源。
