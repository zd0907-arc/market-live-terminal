# 08_DOCS_GOVERNANCE（文档治理规范）

## 1. 目标
- 固定核心文档编号，防止编号膨胀。
- 将“核心规则”与“动态变更过程”分层管理。
- 保证从需求到归档的流程可复制、可交接、可追溯。

## 2. 核心文档编号冻结（仅此 9 份）
> 自 2026-03-09 起，核心编号固定为 `00~08`，不得新增/改号/挪号。

| 编号 | 文档 | 角色 |
|---|---|---|
| `00` | `00_AI_HANDOFF_PROTOCOL.md` | 多 AI 协作协议 |
| `01` | `01_SYSTEM_ARCHITECTURE.md` | 架构边界与红线 |
| `02` | `02_BUSINESS_DOMAIN.md` | 需求总册（唯一业务真相源） |
| `03` | `03_DATA_CONTRACTS.md` | 接口与字段契约 |
| `04` | `04_OPS_AND_DEV.md` | 运维发布与远程控制 SOP |
| `05` | `05_LLM_KEY_SECURITY.md` | 密钥与安全规范 |
| `06` | `06_CHANGE_MANAGEMENT.md` | 动态变更与阶段目标流程 |
| `07` | `07_PENDING_TODO.md` | 阻塞与待办板 |
| `08` | `08_DOCS_GOVERNANCE.md` | 文档治理规则 |

## 3. 非核心文档规则
- 非核心文档不得使用 `NN_*.md` 命名。
- 动态变更文档统一放 `docs/changes/`，命名见 `06`。
- 当前新变更统一使用 `MOD/REQ/INV/CFG/STG` 类型化 ID；历史 `CHG-*` 仅保留为旧记录引用。
- 交接日志固定为 `AI_HANDOFF_LOG.md`（短日志）。
- `REMOTE_CONTROL_GUIDE.md` 仅索引，不承载流程正文。

## 4. 归档规则（标准化）
- 归档目录：`docs/archive/`
- 变更卡归档目录：`docs/archive/changes/`
- 事件/事故归档目录：`docs/archive/incidents/`
- 新归档文件命名：`ARC-<TYPE>-<YYYYMMDD>-<slug>.md`
  - `TYPE` 推荐：`INC`(事件), `RET`(复盘), `REL`(发布), `ADR`(架构), `OPS`(运维), `LEG`(历史导入)
- 归档正文建议添加 `Archive-Meta` 信息块（见 `docs/archive/ARCHIVE_NAMING_STANDARD.md`）。

## 5. 线性执行流程（必须按序）
1. 新建变更卡（`docs/changes/`）。
2. 在 `02` 对应 CAP 卡登记拟变更点。
3. 实施改动并验证。
4. 如需上线，按 `04` 发布；生产冒烟由你手动执行，AI 提供清单与结果模板。
5. 回填 `02` + `AI_HANDOFF_LOG`；有阻塞更新 `07`。
6. 变更卡归档到 `docs/archive/changes/` 并记录 Archive ID（可在用户确认“业务冒烟通过”后单独执行，且不触发再次部署）。

## 6. Release Gate（含前序动作）
- 前序动作 A：Task ID 与 CAP 回填完成。
- 前序动作 B：若依赖 Windows，先通过 `04` 的连通性 gate。
- 核查项：
  - `README.md` 入口与端口正确；
  - 发版版本一致：`package.json` = `src/version.ts` = `README.md` 标题版本；
  - `02` 验收案例含绝对时间；
  - 变更涉及接口时已更新 `03`；
  - 变更涉及 SOP/安全时已更新 `04/05`；
  - `AI_HANDOFF_LOG` 已登记；
  - 阻塞项已同步到 `07`。
