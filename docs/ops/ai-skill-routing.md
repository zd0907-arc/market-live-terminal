# AI / Skill 路由与协同

> 目标：定义 `AGENTS.md`、核心文档、`AI_QUICK_START.md`、项目 skill 之间的分工，避免出现“第二套真相源”或“该用 skill 时没用、不该用时乱用”。

## 1. 分层原则

### 1.1 规则层
- 全局 `~/.codex/AGENTS.md`：跨项目通用行为规则。
- 项目根 `AGENTS.md`：本项目永久规则，如三端职责、跨平台脚本、远端抖动处理、前后端复用原则。

### 1.2 真相层
- `docs/00~08`：核心长记忆，负责长期事实、契约、流程、待办、治理规则。
- `docs/AI_QUICK_START.md`：高曝光快速入口，允许承载当前阶段入口与阅读顺序，但不替代 `00~08`。

### 1.3 执行层
- project skills：可复用的任务执行手册，负责“怎么做”，不负责定义项目长期真相。
- skill `references/`：只保留命令、检查清单、路径样例、判定规则；不单独承载正式主线事实。
- `docs/changes/*`：单次需求的过程记录、验收、归档。

### 1.4 压缩原则
- `AGENTS.md` 只保留“什么时候该切到某个 skill”这类入口规则。
- 具体执行细节、命令样例、验真步骤，尽量下沉到对应 skill。
- 同一条规则不要同时在 `AGENTS.md`、核心文档、skill 里各写一遍。

## 2. 冲突优先级

当 skill、reference、核心文档冲突时，按下面顺序裁决：
1. `AGENTS.md`
2. `docs/00~08`
3. `docs/AI_QUICK_START.md`
4. skill `SKILL.md`
5. skill `references/*`

一句话：**skill 服从文档真相，不反过来定义文档真相。**

## 3. 当前项目相关 skill 清单

| Skill | 角色 | 适用场景 | 不应主导 |
|---|---|---|---|
| `mac-windows-ops-bridge` | Windows 远端执行护栏 | Mac 控 Windows 跑脚本、计划任务、日志排障、PowerShell/cmd 引号问题 | 正式 L2 日跑策略裁决 |
| `market-ui-parity-keeper` | 前端共享壳与图表一致性 | 首页/复盘/研究页共享组件、图表、tooltip、股票卡复用 | 后端数据链路问题 |
| `zhangdata-dev-workflow-coordinator` | 多 skill 路由器 | 复杂需求的分支/worktree/skill 编排 | 代替 specialist skill 实施细节 |
| `zhangdata-governance-doc-keeper` | 文档收尾与归档 | 变更卡、handoff、pending、mother card、archive | 发布执行 |
| `zhangdata-market-data-alignment-operator` | 数据链路定位器 | 页面无数据、数据对不上、本地/线上漂移、窗口错位 | 通用 Windows 运维 |
| `zhangdata-l2-postclose-ops` | 正式 L2 盘后作业 | 日跑、月批、repair/review queue、正式 backfill 策略 | 首页数据错位这类泛化问题 |
| `zhangdata-version-discipline-keeper` | 版本/分支治理 | 版本漂移、tag 对齐、阶段收口、分支卫生 | 直接部署 |
| `zhangdata-release-ops-commander` | 发布执行 | release gate、部署、smoke checklist、rollback anchor | 版本决策、文档归档 |

## 4. 默认路由

### 4.1 默认情况
- 普通代码改动先遵守 `AGENTS.md` + `docs/00~08`。
- 只有任务明显进入某个专门领域时，才显式切到对应 skill。

### 4.2 高优先级 skill 路由
- `Windows` 远端执行、计划任务、PowerShell/cmd 坑：`mac-windows-ops-bridge`
- 页面有数据但显示不对 / 本地线上不一致 / 不确定断在哪一层：`zhangdata-market-data-alignment-operator`
- 正式 `postclose L2` 日跑、月批、repair queue：`zhangdata-l2-postclose-ops`
- 共享股票卡、共享图表、tooltip、页面壳一致性：`market-ui-parity-keeper`
- 文档补齐、handoff、pending 清理、治理复盘：`zhangdata-governance-doc-keeper`
- 版本、tag、分支卫生：`zhangdata-version-discipline-keeper`
- 发布、smoke、回滚锚点：`zhangdata-release-ops-commander`

### 4.3 低优先级 skill
- `zhangdata-dev-workflow-coordinator` 只在“需要编排多个 specialist skill”时启用。
- 普通单需求不要先走它，否则会增加一层无效调度。

## 5. 推荐组合

### 5.1 页面异常 / 数据异常
1. `zhangdata-market-data-alignment-operator`
2. 如需远端 Windows 动作，再接 `mac-windows-ops-bridge`
3. 若最终证明是共享 UI 漂移，再接 `market-ui-parity-keeper`

### 5.2 正式盘后 L2
1. `zhangdata-l2-postclose-ops`
2. 如需实际远控 Windows，再接 `mac-windows-ops-bridge`
3. 做完后由 `zhangdata-governance-doc-keeper` 收尾

### 5.3 普通功能开发
1. 直接按 `AGENTS.md` + `docs/ops/development-workflow.md`
2. 命中文档治理时再接 `zhangdata-governance-doc-keeper`
3. 命中共享 UI 时再接 `market-ui-parity-keeper`

### 5.4 版本与发布
1. `zhangdata-version-discipline-keeper`
2. `zhangdata-release-ops-commander`
3. `zhangdata-governance-doc-keeper`

## 6. 当前评估

### 6.1 设计合理、应继续保留
- `mac-windows-ops-bridge`
- `market-ui-parity-keeper`
- `zhangdata-market-data-alignment-operator`
- `zhangdata-governance-doc-keeper`
- `zhangdata-l2-postclose-ops`

这些 skill 都是“明显高频且容易踩坑”的专项能力，存在价值明确。

### 6.2 可保留，但不要默认先用
- `zhangdata-dev-workflow-coordinator`
- `zhangdata-version-discipline-keeper`
- `zhangdata-release-ops-commander`

原因不是它们没价值，而是它们更偏“管理编排”。只有当任务真的进入流程治理、版本治理、发布治理时，才值得触发。

## 7. 维护规则

1. 核心文档改了长期事实，同轮必须检查相关 skill 是否一起过时。
2. skill `references/*` 允许写命令和检查表，不允许单独维护正式真相。
3. 一个任务尽量只有一个 primary skill owner；其余 skill 只做 secondary。
4. `AGENTS.md` 只讲 skill 入口时，skill 必须把执行步骤写完整，避免入口和做法断裂。
5. 若某个 skill 连续多轮都不触发，要先查：
   - 是不是触发条件写得太“管理话术”；
   - 是不是它和 `AGENTS.md` / 核心文档重复；
   - 是不是实际已经不需要单独 skill。
6. 若某个 skill 的内容开始重复核心文档，应把长期事实回流到文档，再把 skill 收窄成执行手册。
