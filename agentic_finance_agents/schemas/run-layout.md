# Run 目录格式

每次 Codex 调度都创建一个独立 run 目录。

```text
runs/
  20260611-1530-sh600519-company/
    run_manifest.json
    00-meeting-brief.md
    run_context.json
    source_registry.json
    evidence_cache.jsonl
    retrieval_log.jsonl
    agent_outputs.json
    agents/
      01-pitch-builder.md
      01-pitch-builder.json
      ...
    final_report.md
    promotion_candidates.json
    ui/
      compact.html
      full.html
      research_ui_manifest.json
      data.json
    close_pack.md
    close_pack.json
```

## run_manifest.json

```json
{
  "run_id": "20260611-1530-sh600519-company",
  "created_at": "2026-06-11T15:30:00+08:00",
  "created_by": "codex",
  "subject": "sh600519",
  "mode": "company",
  "depth": "standard",
  "status": "running",
  "workflow": "codex-orchestration-v1",
  "agents_requested": [],
  "agents_completed": [],
  "agents_skipped": {},
  "context_files": [
    "run_context.json",
    "source_registry.json",
    "evidence_cache.jsonl",
    "retrieval_log.jsonl"
  ],
  "notes": []
}
```

## run_context.json

只记录本次研究的最小上下文，不承载全量事实：

```json
{
  "subject": "sh600519",
  "company_name": "",
  "mode": "company",
  "as_of_date": "2026-06-11",
  "depth": "standard",
  "success_criteria": [],
  "assumptions": [],
  "blocking_questions": []
}
```

## source_registry.json

记录允许来源和禁用来源，供各 Agent 自行取数：

```json
{
  "allowed_local_sources": [],
  "allowed_public_sources": [],
  "forbidden_sources": [
    "FactSet",
    "CapIQ",
    "Daloopa",
    "IBISWorld",
    "PitchBook",
    "Dun & Bradstreet",
    "Moody's"
  ],
  "source_ref_policy": "required_for_all_facts"
}
```

## evidence_cache.jsonl

各 Agent 自取数后写入可复用证据。它是共享缓存，不是正式事实源。

```json
{"agent_id":"03-earnings-reviewer","evidence_type":"announcement","fact":"","metric":null,"source_ref":{},"created_at":"2026-06-11T15:30:00+08:00"}
```

## retrieval_log.jsonl

记录每次本地查询、服务调用或公开来源访问，便于 GL Reconciler 复核。

```json
{"agent_id":"06-valuation-reviewer","tool":"query_local_db","target":"","query":"","retrieved_at":"2026-06-11T15:30:00+08:00","status":"ok"}
```

## 临时产物边界

`runs/` 下的内容默认是实验产物。进入正式页面或数据库前必须满足：

1. 关键字段有来源。
2. 数据缺口已经明确。
3. 至少完成 `07-gl-reconciler` 和 `08-month-end-closer` 检查。
4. 用户在 Codex 中明确同意晋级或后续代码实现显式读取这些字段。

## 页面产物边界

`ui/` 下的 HTML 是研究展示候选，不是正式页面源码。主应用可通过 iframe/sandbox 方式读取，但不能把 HTML 内的结论自动视为正式库事实。

正式页面或数据库接入前必须满足：

1. `07-gl-reconciler` 未给 `hold`。
2. `08-month-end-closer` 状态不是 `blocked`。
3. `research_ui_manifest.json` 标明 `promotion_readiness`。
4. HTML 中的关键数字能追溯到 `evidence_cache.jsonl` 或上游 Agent JSON。
