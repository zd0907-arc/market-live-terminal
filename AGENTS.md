# Market Live Terminal Agent Instructions

## 项目边界

- 这是三端协作项目：`Mac` 负责开发、文档、本地研究站；`Windows` 负责抓取、盘后跑数、训练；`NAS` 负责在线服务、发布、在线查询。
- 当前唯一正式项目根目录是 `/Users/dong/ZhangData`；开发仓库固定为 `/Users/dong/ZhangData/market-live-terminal`，正式数据仓库固定为 `/Users/dong/ZhangData/market-data`。
- 桌面、iCloud、NAS 备份中恢复出来的同名目录只作为找回资料或只读比对来源；除非用户明确指定，不作为开发、验证、发布的主路径。
- 任何跨端任务都先说明：改哪一端、依赖哪一端、在哪一端验证。
- 不静默假设三端已经同步；涉及库、脚本、发布结果时，先确认当前主端和目标端。
- 默认按 `Mac 本地研究站` 设计与验证，不默认把本地改动直接等同于 `NAS` 线上结果。
- 用户提到“代码提交云端”“远程代码备份”“双备份”时，默认含义是同时推到 `GitHub origin` 和 `NAS Gitea nas`；除非用户明确限定，不只推其中一个。

## 表达规则

- 对用户解释数据、目录、三端同步时，先讲业务职责和影响，再给路径；不要用一串库名、表名、环境变量替代解释。
- “三端拉齐”默认指业务能力、正式数据口径和可用功能拉齐，不等于 Mac、Windows、NAS 的文件夹必须长得一模一样。
- 判断某个目录能否删除时，必须先说明它服务哪个页面/功能、删掉会坏什么、是否有替代来源；路径只作为定位信息。

## 开发规则

- 先读再改：先看相邻实现、调用方、测试和相关文档，再动手。
- 先说假设：需求、数据口径或运行环境不清楚时，先明确假设，不要直接脑补。
- 只做必要修改：不顺手重构、不改无关格式、不补未要求抽象。
- 发现冲突要暴露：旧口径和新口径冲突时，先指出，不混成第三套。
- 能验证就验证；没跑测试、没做远端检查、没做同步核验，都要明说。

## 跨平台与远端

- 写脚本前先确认目标壳：`bash`、`python`、`bat`、`PowerShell` 不能混写语法。
- Windows 脚本默认单独考虑路径分隔符、引号、变量展开、编码和换行，不按 `Mac/bash` 习惯脑补。
- 新增或修改跨端脚本时，优先复用现有脚本家族和目录，不另起一套入口。
- `SSH` / `Tailscale` 首次失败默认按瞬时抖动处理；先做同路径重试，再判断是否需要切换方案。
- 不因为一次远端失败就立刻改架构、改入口或重写流程。
- Git 远端提交默认由 Mac 控制面执行；提交后必须分别验真 `origin/main` 与 `nas/main` 的 commit 是否等于本地 `HEAD`。

## 前后端协作

- 前端新增页面或模块时，优先复用现有 canonical 组件和视觉骨架，不复制近似实现。
- 股票头卡、研究卡壳、价格走势、成交量/资金图这类跨页公共能力，优先收敛到共享组件。
- 后端新增接口、脚本、表名、路径前，先对齐现有 canonical 命名和正式数据口径。
- 非明确要求时，不新增新的数据真相源、页面主入口或脚本主链。
- 新研究、新模型、新回测的机器产物默认写入 `/Users/dong/ZhangData/market-data/artifacts` 或 `/Users/dong/ZhangData/market-data/runs`；代码仓只保留人读结论、说明文档、小型配置和必要样例。
- 代码仓不再保留 `.run`、`public/research`、`data/selection`；页面 `/research` 与 `/data/selection` 由后端从数据仓提供。

## 文档路由

- 架构与三端职责：`docs/01_SYSTEM_ARCHITECTURE.md`
- 业务能力与验收：`docs/02_BUSINESS_DOMAIN.md`
- 数据契约与存储口径：`docs/03_DATA_CONTRACTS.md`、`docs/contracts/storage.md`
- 代码仓 / 数据仓最终排布：`docs/ops/code-data-layout-finalization-plan.md`
- 运维、发布、脚本入口：`docs/04_OPS_AND_DEV.md`
- AI / skill 路由：`docs/ops/ai-skill-routing.md`
- 金融研究 Agent 领域：`agentic_finance_agents/HANDOFF.md`、`agentic_finance_agents/DOCS_INDEX.md`
- 三端同步与 Mac/NAS 协作：`docs/ops/three-end-sync.md`、`docs/ops/mac-nas-collaboration.md`
- AI 协作、过程卡、交接：`docs/00_AI_HANDOFF_PROTOCOL.md`、`docs/06_CHANGE_MANAGEMENT.md`
