# changes（动态变更文档区）

本目录只放进行中的变更卡，命名必须为：
- `<TYPE>-YYYYMMDD-NN-<slug>.md`
- `TYPE` in `MOD|REQ|INV|CFG|STG`

进行中状态建议：`DRAFT -> ACTIVE -> VERIFY -> DONE -> ARCHIVED`

完成后：
1. 在文档末尾补“归档信息”；
2. 移动到 `docs/archive/changes/`；
3. 在 `AI_HANDOFF_LOG.md` 追加结论短日志。

涉及运行、补数、atomic、bench、full_reverse 的当前做法，先看 `docs/04_OPS_AND_DEV.md` 与 `docs/ops/atomic-script-families-boundary.md`，不要直接把历史 `changes` 卡里的脚本当正式入口。
