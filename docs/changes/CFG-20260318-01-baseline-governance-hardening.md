# CFG-20260318-01 基线存档与最小治理加固

## 1. 基本信息
- ID：`CFG-20260318-01`
- 标题：基线存档与最小治理加固
- 状态：`DONE`
- 负责人：AI
- 关联 Task ID：`2026-03-18-baseline-governance`
- 关联 CAP：`CAP-OPS-GOVERNANCE`

## 2. 背景与目标
- 项目将长期采用“纯 AI 开发 + 单人维护”模式。
- 需要先冻结可回退基线，再补齐最小治理底座，降低 AI 误改、版本漂移和前端暴露共享写 token 的风险。

## 3. 方案与边界
- 做什么：
  - 建立 git / 数据 / 配置三层快照；
  - 收口前端写 token 暴露路径，改为服务端代理注入；
  - 补齐版本一致性检查与统一自检入口；
  - 收敛仓库边界，明确唯一开发目录；
  - 新增 AI 快速入口文档。
- 不做什么：
  - 不改业务接口语义；
  - 不调整数据库业务 schema；
  - 不顺带开发新功能。

## 4. 执行步骤
1. 创建 `snapshot-20260318-pre-governance` tag、归档分支和治理分支；
2. 导出 bundle，并在仓库外备份当前 db / `.env.local` / 基线说明；
3. 移除前端构建注入 `VITE_WRITE_API_TOKEN`，改为 dev proxy + nginx proxy 服务端注入；
4. 统一 `backend/app/main.py` 版本到 `4.2.19`；
5. 新增版本检查脚本与基线自检脚本；
6. 清理 `.venv` 与旧副本 gitlink 的主线参与状态；
7. 回填 AI 快速入口文档与运维/安全文档。

## 5. 验收标准
- Given 当前项目处于治理前状态，When 完成本轮治理，Then 可以通过 tag / 归档分支 / 外部备份回退代码、数据、配置。
- Given 前端生产构建完成，When 搜索静态产物，Then 不应出现 `WRITE_API_TOKEN` 或 `VITE_WRITE_API_TOKEN`。
- Given 运行 `npm run check:baseline`，When 检查结束，Then 后端测试、前端 build、版本一致性检查全部通过。

## 6. 风险与回滚
- 风险：前端写请求改为服务端代理注入后，若代理配置错误，写接口会返回 401/503。
- 回滚：
  - 代码：切回 `snapshot-20260318-pre-governance`；
  - 数据/配置：恢复 `/Users/dong/Desktop/AIGC/backups/market-live-terminal/20260318-pre-governance/` 下快照文件。

## 7. 结果回填
- 已完成 git / 数据 / 配置基线快照。
- 已移除前端 build 时注入共享写 token 的路径。
- 已新增版本检查与基线自检入口。
- 已新增 AI 快速入口文档并收敛仓库边界提示。

## 8. 归档信息
- 归档时间：``
- 归档 ID：``
- 归档路径：``
