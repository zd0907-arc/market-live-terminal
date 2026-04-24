# 08_DOCS_GOVERNANCE（文档治理规范）

## 1. 目标
- 固定核心文档编号，防止编号膨胀。
- 将“核心规则”与“动态变更过程”分层管理。
- 保证从需求到归档的流程可复制、可交接、可追溯。
- 让核心文档保持**长记忆**角色，不再承接过多过程细节。

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

## 3.1 长记忆 / 短记忆边界
- `docs/`：长记忆，只描述“系统现在是什么”；
- `docs/changes/`：短记忆，只描述“这次需求是怎么做出来的”；
- 核心文档若开始承载长过程、试验讨论、历史来回，必须拆回 `docs/changes/` 或 `docs/archive/`。

## 3.2 动态核心文档的长度约束
- `AI_HANDOFF_LOG.md`：只保留最近 `1~2` 个版本窗口的短日志；
- `07_PENDING_TODO.md`：只保留当前真实 `ACTIVE/BLOCKED` 项；
- 超出窗口的旧日志、旧待办，必须整理成 archive summary，不继续堆在核心正文里。

## 4. docs 根目录保留集
- 只保留：
  - 核心文档 `00~08`
  - `AI_QUICK_START.md`
  - `AI_HANDOFF_LOG.md`
- 其余文档默认进入：
  - `docs/domain/`（业务主题长记忆）
  - `docs/contracts/`（契约细节长记忆）
  - `docs/ops/`（运维细节长记忆）
  - `docs/changes/`（动态过程）
  - `docs/archive/`（历史归档）

## 5. 归档规则（标准化）
- 归档目录：`docs/archive/`
- 变更卡归档目录：`docs/archive/changes/`
- 事件/事故归档目录：`docs/archive/incidents/`
- 新归档文件命名：`ARC-<TYPE>-<YYYYMMDD>-<slug>.md`
  - `TYPE` 推荐：`INC`(事件), `RET`(复盘), `REL`(发布), `ADR`(架构), `OPS`(运维), `LEG`(历史导入)
- 归档正文建议添加 `Archive-Meta` 信息块（见 `docs/archive/ARCHIVE_NAMING_STANDARD.md`）。

## 6. 线性执行流程（必须按序）
1. 新建变更卡（`docs/changes/`）。
2. 在 `02` 对应 CAP 卡登记拟变更点。
3. 实施改动并验证。
4. 如需上线，按 `04` 发布；生产冒烟由你手动执行，AI 提供清单与结果模板。
5. 回填 `02` + `AI_HANDOFF_LOG`；有阻塞更新 `07`。
6. 变更卡归档到 `docs/archive/changes/` 并记录 Archive ID（可在用户确认“业务冒烟通过”后单独执行，且不触发再次部署）。

## 6.1 文档收尾强制动作
- 需求做完后，不能只“追加新内容”，必须同步做三件事：
  1. 回流新的长期事实到核心文档；
  2. 移除 `07` 中已解决/失效项；
  3. 当 `AI_HANDOFF_LOG` 超窗时归档旧窗口。
- 具体顺序与 merge 后清理动作见：`docs/ops/development-workflow.md`

## 7. Release Gate（含前序动作）
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
