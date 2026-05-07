# MOD-20260429-07 核心文档审计与外部知识库同步准备

## 1. 基本信息
- 状态：DONE
- 负责人：Codex
- 关联 CAP：`CAP-REALTIME-FLOW`, `CAP-HISTORY-30M`, `CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联请求：2026-04-29 项目文档整体整理、三大已落地模块现状核对、外部知识库后续同步准备

## 2. 背景与目标
- 当前项目已经形成盯盘、正式复盘、选股研究工作台三条已落地主链路。
- 热点板块 / 市场热度研究正在 `codex/market-heat-sensing` 分支推进，但暂不并入已落地三模块。
- 目标是把长期文档重新对齐到当前代码、版本与模块边界，并为外部知识库同步准备独立产物区。

## 3. 本次处理
- 对齐 `README.md`、`AI_QUICK_START.md`、`04_OPS_AND_DEV.md` 的版本与工作区口径到 `v5.1.0`。
- 回写 `02_BUSINESS_DOMAIN.md`，新增 `EXPLORING` 状态，明确热点板块只属于探索能力。
- 补强 `docs/domain/review-and-history.md`、`docs/domain/selection-research.md`、`docs/contracts/review-selection.md`。
- 更新当前真相母卡 `MOD-20260421-01`，补入三大模块现状和热点探索边界。
- 新增仓库根目录独立同步产物区，避免把外部知识库同步规则写进核心文档治理。
- 压缩 `AI_HANDOFF_LOG.md`，把旧窗口整理到 archive summary。

## 4. 验收结果
- 文档已反映当前三大已落地模块：
  - 盯盘：Windows 实时 crawler + Cloud 轻量 ingest + Mac 本地同步库消费；
  - 复盘：`/review` + `/api/review/pool` + `/api/review/data`；
  - 选股：`/selection-research` + 多策略研究/观察工作台。
- 选股策略被重新描述为“研究与观察工作台”，不再暗示已经是稳定自动买入系统。
- 外部知识库后续同步有独立产物区和替换策略，不污染核心文档治理。
- `npm run check:version` 已通过，版本标记统一为 `5.1.0`。

## 5. 风险与遗留
- 当前主工作区仍有未提交的热点板块代码与研究文档；本卡不替这些改动做业务收口。
- 选股策略真实效果仍需继续滚动验证。
- 若后续热点板块转为正式模块，需要单独把 `CAP-MARKET-HEAT` 从 `EXPLORING` 改为正式状态，并补契约与运维文档。
