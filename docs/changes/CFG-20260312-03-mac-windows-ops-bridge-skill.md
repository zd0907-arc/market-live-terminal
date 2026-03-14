# CFG-20260312-03-mac-windows-ops-bridge-skill

## 1. 基本信息
- 标题：Mac 控 Windows 长任务执行 Skill 与运维验真文档补齐
- 状态：DONE
- 负责人：后端 AI
- 关联 Task ID：`CHG-20260312-03`
- 关联 CAP：`CAP-WIN-PIPELINE`

## 2. 背景与目标
- 近期复盘 V2 长跑、Windows 月批重启、任务验真都依赖“Mac 开发 + Windows 执行”的跨机协作。
- 实操中已经暴露出一组高频坑：`scp` 落点误判、`schtasks /TR` 引号解析、`schtasks /End` 不会自动杀掉 Python 子进程、`out.log` 为空但任务其实正常推进、Mac 侧读取 Windows 文本需要按 `gbk` 解码等。
- 目标是把这些经验沉淀成一个可复用 Skill，并同步回填项目运维文档，避免后续同类任务重复踩坑。

## 3. 方案与边界
- 做什么：
  - 新建外部 Skill `mac-windows-ops-bridge`，覆盖同步、执行、验真、停止、排障的标准流程。
  - 在项目 `04_OPS_AND_DEV` 中增加“Mac 控 Windows 长任务执行与验真”小节，固化本项目约定。
  - 在 `AI_HANDOFF_LOG` 记录本次治理结果，方便后续接手。
- 不做什么：
  - 不改生产业务逻辑、不改数据库结构。
  - 不发布生产、不触碰正在运行的 Windows 月批任务。
  - 不把 Skill 内部说明混入核心业务文档，只保留项目级 SOP 与引用关系。

## 4. 执行步骤（按顺序）
1. 检查已创建的 `mac-windows-ops-bridge` 目录结构，补齐 `SKILL.md`、项目参考说明和 `agents/openai.yaml`。
2. 将“路径核对、任务启动、真运行验真、编码/日志注意事项”回填到 `docs/04_OPS_AND_DEV.md`。
3. 新建治理变更卡并在 `docs/AI_HANDOFF_LOG.md` 留下短日志。

## 5. 验收标准（Given/When/Then，绝对时间）
- Given `2026-03-12 23:05`，When 打开 `/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/SKILL.md`，Then 可以看到面向“Mac 开发、Windows 执行”的标准流程、护栏、验真规则与常见坑。
- Given `2026-03-12 23:08`，When 打开 `/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md`，Then 可以看到新增的“Mac 控 Windows 长任务执行与验真”小节，明确本项目的路径、命令、验真与停止规范。
- Given `2026-03-12 23:10`，When 查看 `docs/AI_HANDOFF_LOG.md`，Then 存在本次 Skill/文档治理的短日志，可追溯 Task ID、CAP、风险与链接。

## 6. 风险与回滚
- 风险：
  - Skill 为外部共享目录内容，不属于 repo 版本控制；若未来本地 skill 目录迁移，需要重新确认它是否仍会被 Codex 自动发现。
  - 运维文档仅沉淀 SOP，不替代真实连通性检查；执行前仍需先过 Tailscale/SSH 探活门。
- 回滚：
  1. 删除外部 Skill 目录 `/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/`；
  2. 回退 `docs/04_OPS_AND_DEV.md` 本次新增小节；
  3. 保留 `AI_HANDOFF_LOG` 历史记录不删除，仅追加说明回退原因。

## 7. 结果回填
- 实际改动：
  - 新建并完善外部 Skill：`/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/SKILL.md`
  - 新增项目参考：`/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/references/market-live-terminal.md`
  - 新增 Skill 元数据：`/Users/dong/Desktop/AIGC/skills/mac-windows-ops-bridge/agents/openai.yaml`
  - 回填项目运维文档：`docs/04_OPS_AND_DEV.md`
  - 回填交接日志：`docs/AI_HANDOFF_LOG.md`
- 验证结果：
  - `2026-03-12 23:05`：Skill 文件已写入共享 skill 目录并可读。
  - `2026-03-12 23:05`：项目文档已补齐“Mac 控 Windows 长任务执行与验真”小节。
- 遗留问题：
  - 当前仅完成 Skill + 文档治理，尚未做基于该 Skill 的自动化脚本封装；如后续反复使用，可再补 `scripts/` 模板化命令。

## 8. 归档信息
- 归档时间：
- Archive ID：
- 归档路径：
