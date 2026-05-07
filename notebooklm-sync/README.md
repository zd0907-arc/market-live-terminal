# NotebookLM Sync Workspace

这个目录只服务于外部 NotebookLM 知识库同步，不参与项目核心文档治理。

## 当前同步包

优先上传 PDF：

- `dist/ZHANGDATA_STABLE_CONTEXT_v5.1.pdf`
- `dist/ZHANGDATA_CURRENT_UPDATE_2026-04-30.pdf`

Markdown 源文件：

- `ZHANGDATA_STABLE_CONTEXT_v5.1.md`
- `ZHANGDATA_CURRENT_UPDATE_2026-04-30.md`

## 写作原则

NotebookLM 看不到项目代码和数据库，所以同步包不应堆文件路径清单。它要读到的是：

- 项目为什么存在；
- 三端架构为什么这样分；
- 盯盘、复盘、选股分别解决什么问题；
- L1/L2、主力、超大单、回调承接、热点生命周期等核心概念；
- 哪些结论已验证，哪些仍在探索；
- 当前策略边界和不能做什么。

## 替换策略

- 稳定背景包：项目形态、架构边界、核心模块边界大变时才替换。
- 日期更新包：按需替换，只保留最新一份。
- 不上传数据库、日志、大体积实验结果、构建产物。

## 生成 PDF

使用本地 skill 脚本或仓库脚本生成 PDF。PDF 是 NotebookLM 文件上传的首选格式，因为它能保留文件名，避免“复制的文字”来源难以区分。
