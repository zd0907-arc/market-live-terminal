# MOD-20260528-01-spark-v2-stable-runup-and-windows-training-plan

## 1. 基本信息

- 标题：星火 v2 稳定冲高训练计划与 Windows 训练节点工作模式
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260528-01`
- 关联 CAP：`CAP-SELECTION-RESEARCH`, `CAP-WIN-PIPELINE`
- 关联 STG：星火 v2 纯选股训练

## 2. 背景与目标

用户明确下一轮不急着训练，先把目标和执行方式聊清楚。

本轮需要固定两件事：

1. 星火 v2 下一轮目标从“抓最大冲高”调整为“稳定有冲高，少选到买后从未上涨的票”。
2. 后续模型训练采用 Mac 端规划、Windows 端执行的工作模式，避免 Mac 长时间 CPU 100%。

## 3. 方案与边界

做什么：

- 新增稳定冲高训练计划。
- 新增 Windows 模型训练节点 SOP。
- 回写核心运维入口和模型开发 SOP。
- 做 Windows 端轻量检查，确认远程执行前置条件。

不做什么：

- 不启动正式训练。
- 不接入线上工作台。
- 不安装 Windows GPU 训练库。
- 不修改主 worktree 当前未提交改动。
- 不处理旧未跟踪 smoke 目录。

## 4. 执行步骤

1. 读取 Mac-Windows 运维 skill 和项目现有运维文档。
2. 检查 Windows SSH、项目目录、Python、GPU、基础训练依赖、特征库范围。
3. 编写 `docs/selection/spark_v2_stable_runup_training_plan_2026-05-28.md`。
4. 编写 `docs/ops/windows-model-training.md`。
5. 回写 `docs/04_OPS_AND_DEV.md` 和 `docs/selection/model_development_sop.md`。
6. 做文档/语法检查。

## 5. 验收标准

- Given 2026-05-28 的当前训练 worktree。
- When 后续 AI 或用户准备开启星火 v2 下一轮训练。
- Then 可以从训练计划理解业务目标、指标、模型分型和时间切分。
- Then 可以从 Windows 训练 SOP 理解如何从 Mac 同步脚本、在 Windows 执行、验真、回收结果。
- Then 文档明确说明 Windows 当前有 4070，但 `sklearn` 不直接吃 GPU，真正 GPU 训练需要另行安装验证训练库。

## 6. 风险与回滚

风险：

- Windows 项目目录不是 Git 仓库，不能使用 `git pull` 当同步方案。
- 当前 Windows 默认特征库物理名仍带 `smoke`，容易误导。
- Windows 有 RTX 4070，但当前未安装 GPU 版训练库。
- 复杂 SSH 单行命令容易被 PowerShell/cmd 引号规则拆坏。

回滚：

- 本轮只改文档，直接 revert 文档提交即可。

## 7. 结果回填

- 实际改动：
  - 新增 `docs/selection/spark_v2_stable_runup_training_plan_2026-05-28.md`。
  - 新增 `docs/ops/windows-model-training.md`。
  - `docs/04_OPS_AND_DEV.md` 增加 Windows 模型训练节点入口。
  - `docs/selection/model_development_sop.md` 增加训练执行节点规范。
- 验证结果：
  - Windows SSH 可达。
  - Windows Python 3.11.3 可用。
  - `pandas / numpy / sklearn / joblib` 可导入。
  - Windows RTX 4070 可见。
  - Windows 当前未安装 PyTorch / XGBoost / LightGBM / CatBoost。
  - Windows 特征库 `model_feature_store_smoke_20260401_20260515.db` 实际覆盖 `2024-09-02 ~ 2026-05-27`，标签覆盖到 `2026-05-13`。
  - 文档换行和 tab 检查通过。
- 遗留问题：
  - 尚未启动正式训练。
  - 尚未安装 GPU 训练库；当前 sklearn 模型不会真正使用 4070。
  - Windows 运行目录不是 Git 仓库，后续训练必须通过 Mac 显式同步脚本。
  - 特征库物理名仍带 `smoke`，后续应结合正式别名治理收口。

## 8. 归档信息

- 归档时间：
- Archive ID：
- 归档路径：
