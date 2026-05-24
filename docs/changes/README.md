# changes（动态变更文档区）

本目录只放进行中的变更卡，命名必须为：
- `<TYPE>-YYYYMMDD-NN-<slug>.md`
- `TYPE` in `MOD|REQ|INV|CFG|STG`

进行中状态建议：`DRAFT -> ACTIVE -> VERIFY -> DONE -> ARCHIVED`

完成后：
1. 在文档末尾补“归档信息”；
2. 移动到 `docs/archive/changes/`；
3. 在 `AI_HANDOFF_LOG.md` 追加结论短日志。

顶层只保留少量当前入口：
- 当前真相母卡
- 当前治理阶段摘要
- 当前活跃待办盘点
- 当前仍在推进的少量治理卡

当前如果是看治理收口和活跃待办，优先看：
- `docs/changes/README_STAGE_SUMMARY.md`
- `docs/changes/MOD-20260524-13-governance-phase-summaries-and-active-wip-map.md`
- `docs/changes/MOD-20260524-14-active-pending-nine-item-audit.md`

涉及运行、补数、atomic、bench、full_reverse 的当前做法，先看 `docs/04_OPS_AND_DEV.md` 与 `docs/ops/atomic-script-families-boundary.md`，不要直接把历史 `changes` 卡里的脚本当正式入口。

如果某张变更卡已经完成且不再是当前推进入口，优先移入 `docs/archive/changes/`，不要继续留在顶层占视线。
