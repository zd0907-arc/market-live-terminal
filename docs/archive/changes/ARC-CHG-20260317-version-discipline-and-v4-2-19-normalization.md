> Archive-Meta
- Archive-ID: ARC-CHG-20260317-version-discipline-and-v4-2-19-normalization
- Archive-Type: CHG
- Archived-At: 2026-03-17
- Source-Path: docs/changes/REQ-20260317-12-version-discipline-and-v4-2-19-normalization.md
- Status: FROZEN

# REQ-20260317-12-version-discipline-and-v4-2-19-normalization

## 1. 基本信息
- 标题：版本纪律固化 + 当前线上状态收口为 v4.2.19
- 状态：DONE
- 负责人：Codex / 发布 AI
- 关联 Task ID：`CHG-20260317-12`
- 关联 CAP：`CAP-HISTORY-30M`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-WIN-PIPELINE`
- 前置依赖：`CHG-20260317-09`, `CHG-20260317-10`, `v4.2.18`

## 2. 背景与目标
- `v4.2.18` 打 tag 后，线上又继续发布了信息条布局修正，导致“当前线上真实代码 != v4.2.18 tag 对应代码”。
- 需要做两件事：
  1. 将当前线上真实状态正式收口成一个新版本；
  2. 把版本管理纪律写入 SOP，避免后续再次出现“线上代码比 tag 多一段”的情况。

## 3. 方案与边界
- 做什么：
  - 版本提升到 `v4.2.19`；
  - 让 `v4.2.19` 指向当前真实线上代码；
  - 更新版本可见面；
  - 在 `04_OPS_AND_DEV.md` 补充项目冻结版版本纪律。
- 不做什么：
  - 不改变业务功能范围；
  - 不新增后端接口；
  - 不重构现有 Git 模型，只先做纪律固化。

## 4. 冻结规则
- 只要生产代码发生变化，必须 bump 至新版本；
- 一个 tag 只代表一个线上状态；
- 发布顺序固定为：代码/文档 → bump 版本 → release commit → tag → push → deploy。

## 5. 结果回填
- 实际改动：
  1. 版本升级到 `4.2.19`；
  2. 文档补充版本管理纪律；
  3. 当前线上真实状态重新对齐到 `v4.2.19`。
- 验证结果：
  - `npm run build` 通过
- 产出：
  - `v4.2.19`

## 6. 归档信息
- 归档时间：2026-03-17
- Archive ID：ARC-CHG-20260317-version-discipline-and-v4-2-19-normalization
- 归档路径：docs/archive/changes/ARC-CHG-20260317-version-discipline-and-v4-2-19-normalization.md
