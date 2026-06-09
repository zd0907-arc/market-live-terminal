# MOD-20260609-06-ai-skill-routing-and-governance-alignment

## 1. 基本信息
- 标题：AI / skill 路由与项目治理口径收口
- 状态：DONE
- 负责人：Codex
- 关联 Task ID：`MOD-20260609-06-ai-skill-routing-and-governance-alignment`
- 关联 CAP：`CAP-DOCS-GOVERNANCE`
- 关联 STG：

## 2. 背景与目标

当前项目已经同时存在全局 `AGENTS.md`、项目 `AGENTS.md`、核心文档、`AI_QUICK_START.md`、以及多份项目 skill，但它们之间缺少一份明确的协同路由说明。

直接问题有三类：
1. skill 虽然存在，但普通任务里不容易判断什么时候该用；
2. 部分 skill 已出现和当前项目真相不一致的口径；
3. 高曝光文档把基线 gate 写成了 `npm run check:baseline`，但仓库真实可执行入口是 `bash scripts/check_baseline.sh`。

这轮目标是把项目治理层的“规则 / 真相 / 执行”分层写清，并修掉最容易误导后续 AI 的几处冲突。

## 3. 方案与边界
- 做什么：
  - 新增项目级 `AI / skill` 路由文档；
  - 把新文档接入 `AGENTS.md`、`04_OPS_AND_DEV.md`、`AI_QUICK_START.md`；
  - 盘点项目相关 skill，并修正最明显的远端、版本、发布、Windows 运维口径冲突；
  - 把基线检查入口统一成真实存在的 `bash scripts/check_baseline.sh`。
- 不做什么：
  - 不重写全部历史 archive 文档；
  - 不在本轮决定 `package.json` 的版本号是否应改到 `5.2.2`；
  - 不新增新的核心编号文档。

## 4. 执行步骤（按顺序）
1. 阅读核心文档 `00~08` 与 `AI_QUICK_START.md`，确认当前治理分层。
2. 阅读项目相关 skill 与其 `references/`，盘点用途、重叠和老化点。
3. 新增 `docs/ops/ai-skill-routing.md`，明确 AGENTS / 核心文档 / AI_QUICK_START / skill 的分工与默认路由。
4. 回写项目入口文档：`AGENTS.md`、`docs/04_OPS_AND_DEV.md`、`docs/AI_QUICK_START.md`。
5. 修正 skill 口径：
   - `zhangdata-dev-workflow-coordinator`
   - `zhangdata-version-discipline-keeper`
   - `zhangdata-release-ops-commander`
   - `mac-windows-ops-bridge` reference
6. 执行真实基线命令，验证 gate 实际状态。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-06-09` 当前项目仍同时依赖 AGENTS、核心文档、AI 快速入口和多份 project skills，
- When 新 AI 需要判断“该读哪层文档、该用哪个 skill、哪个层级才是真相源”，
- Then 应能先从 `docs/ops/ai-skill-routing.md` 得到明确路由，并且高曝光文档与 skill 对基线命令、主发布远端、Windows/L2 边界不再给出互相冲突的说法。

## 6. 风险与回滚

- 当前仍存在一个未解决阻塞：`bash scripts/check_baseline.sh` 会失败，因为 `package.json=1.16.0`，而 `README.md`、`src/version.ts`、`backend/app/main.py` 都是 `5.2.2`。
- 这说明基线 gate 现在已经能真实暴露问题，但“到底应同步 `package.json`，还是调整版本治理口径”仍需单独裁决。
- 若本轮文档路由需要回退，只需删除 `docs/ops/ai-skill-routing.md` 并撤回三处入口链接；skill 侧改动均为说明层，不影响运行代码。

## 7. 结果回填
- 实际改动：
  - 新增 `docs/ops/ai-skill-routing.md`
  - 回写 `AGENTS.md`、`docs/04_OPS_AND_DEV.md`、`docs/AI_QUICK_START.md`
  - 统一高曝光文档中的 baseline 命令为 `bash scripts/check_baseline.sh`
  - 修正本地 project skills 中的主发布远端、UI/Windows 路由、Windows reference 边界
- 验证结果：
  - 已完成核心文档与相关 skill 盘点；
  - `npm run check:baseline` 已证实不是当前真实入口；
  - `bash scripts/check_baseline.sh` 可执行，并真实暴露了版本面不一致问题
- 遗留问题：
  - `package.json` 版本面与其余三处版本面不一致，已单独登记到 `07_PENDING_TODO.md`

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
