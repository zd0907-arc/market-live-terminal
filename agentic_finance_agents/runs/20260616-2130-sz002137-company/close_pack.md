# 实益达（sz002137）研究收口包

## 结论

本 run 只完成“页面产物读取和展示链路”的接入验证，晋级状态为 `candidate_only`。

## 已完成

- `ui/research_ui_manifest.json`
- `ui/data.json`
- `ui/compact.html`
- `ui/full.html`

## 未完成

- 10 个金融 Agent 独立输出。
- `evidence_cache.jsonl` 和 `retrieval_log.jsonl`。
- `07` 事实一致性对账。
- `08` 研究晋级判断。
- 正式财务、估值和股价驱动证据链。

## 页面可用性

可用于本地选股页 iframe 读取、简版卡展示、完整研究 overlay 打开验证。

不可用于正式研究结论、模型训练标签或线上生产发布。
