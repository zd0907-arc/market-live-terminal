# Windows / NAS 跑数完成后同步方案

日期：2026-06-16

## 1. 结论

这份方案等用户确认“Windows 当天跑数已完成”后再执行。执行前不碰 Windows 正在跑的任务，也不改 NAS 正在使用的数据卷。

三端职责按业务重新确认：

1. `Mac`：主开发机、本地研究站、方案与代码真相源。
2. `Windows`：跑数工具 + 一份相对稳定的完整数据副本；不承担开发、不承担研究页面、不承担 Git 发布。
3. `NAS`：线上服务运行环境 + Docker data 运行数据；用户另行手动做整文件夹冷备。

本次后续同步目标不是“把三台机器做成完全一样”，而是：

1. Windows 能继续稳定跑数，并保留完整跑数数据库。
2. Mac 能消费 Windows 跑完后的结果，继续正常开发和研究。
3. NAS 在线页面和接口能读到最新结果。
4. 三端关键库的名字、入口路径和最低表结构不再互相打架。

## 2. 执行前提

必须等下面条件满足后再动：

1. 用户明确说当天 Windows 跑数完成。
2. Windows 上没有正在写入正式库的大任务。
3. NAS 当前在线服务可以短时间重启。
4. Mac 当前代码已经提交并双推到 `GitHub origin` 与 `NAS Gitea nas`。

不满足这些条件，只允许做只读核查，不做同步和迁移。

## 3. 当前要解决的业务问题

### 3.1 Windows

Windows 的问题不是“要不要做研究站”，答案已经明确：不要。

Windows 只需要做好两件事：

1. 每天跑数。
2. 保留一份完整、稳定、可回查的数据副本。

所以 Windows 后续处理不追求页面体验，也不做前端部署，只做：

1. 确认跑数结果完整。
2. 补齐 Mac / NAS 新代码期望的最低数据库结构。
3. 保持完整 atomic 大库和模型/选股库留在 Windows。
4. 保持路径入口可被脚本稳定找到。

这里的“补齐数据库结构”用业务话说就是：

> Windows 不需要真的有这些研究数据，但如果新代码会查询某些表，Windows 的库里至少要有这些表的结构，避免脚本或同步检查因为“表不存在”失败。

这一步通常只创建空表或补字段，不搬大数据、不重算历史。

### 3.2 NAS

NAS 后续处理只围绕线上服务：

1. app 目录要和 Git 当前版本一致。
2. Docker data 目录要有线上接口需要的最新库。
3. 线上接口验证通过后，才算同步完成。

用户手动做的“整文件夹备份”不纳入本方案执行范围。

## 4. 同步方向

不能把所有东西都理解成互相覆盖。正式方向如下：

| 类型 | 源头 | 目标 | 说明 |
|---|---|---|---|
| 代码、脚本、配置 | Mac | GitHub + NAS Gitea + NAS app | Mac 是开发真相源 |
| Windows 跑数产物 | Windows | Mac，再到 NAS | Windows 是当天跑数源 |
| NAS 线上运行 | Mac 代码 + Mac/NAS data | NAS Docker | NAS 是服务落点 |
| 整文件夹冷备 | 用户手动选择 | NAS 某个备份目录 | Agent 不自动做 |

## 5. Windows 执行方案

### 5.1 跑数完成后先做只读核查

核查内容：

1. 当天日期是否已经落进 Windows 正式库。
2. `market_atomic_mainboard_compact_current.db` 是否完成写入。
3. `selection_research.db` 是否完成当天候选和策略 run。
4. `model_feature_store.db` 是否完成当天特征。
5. `.run` 目录里是否有失败日志或未完成中间库。

完成标准：

1. 当天交易日能在 Windows 的 atomic / selection / model feature 三条链路查到。
2. 没有还在写正式库的 Python 进程。
3. Windows 日跑日志没有 fatal error。

### 5.2 给 Windows 补最低表结构

这一步等跑数停下后做。

目标不是让 Windows 变成研究站，而是让它作为备份副本时不会缺基础表。

计划补齐：

1. `live/market_data.db` 中 Mac / NAS 已有、Windows 缺失的在线服务表结构。
2. `selection_research.db` 中 Mac / NAS 已有、Windows 缺失的选股结果表结构。
3. 不向 Windows 灌入 Mac/NAS 的研究内容，除非该表是跑数链路必须依赖。

当前已知差异：

1. Windows `live` 缺在线研究上下文、股票事件、研究卡等表。
2. Windows `selection` 缺 `selection_exit_watchlist_daily`。
3. Windows `model_feature_store` 与 Mac/NAS 已一致。
4. Windows atomic 保留完整跑数库，不为了追求完全一致去删旧表。

业务解释：

1. 缺的这些表主要影响“新代码拿 Windows 当备份副本读”的兼容性。
2. 不补的话，某些校验脚本或后续同步检查可能会因为缺表失败。
3. 补了以后，Windows 仍然只是跑数站，不会变成研究站。

### 5.3 Windows 路径处理

当前先不做物理搬家。

业务解释：

1. Windows 现在的新目录入口能看到统一路径。
2. 实际大文件还在旧位置。
3. 这对运行没问题，前提是不要删除旧位置。

后续如果要做真实物理整理，必须单独安排停机窗口：

1. 停跑数任务。
2. 复制大库到新物理目录。
3. 校验文件大小、hash、表数。
4. 改脚本写入路径。
5. 保留旧目录数天观察。
6. 再决定是否删除旧目录。

这不是本次同步的必要动作。

## 6. Mac 执行方案

Mac 是本次同步的控制台。

执行内容：

1. 确认代码工作区干净，必要时先处理未提交改动。
2. 确认 `origin/main` 与 `nas/main` 等于本地 `HEAD`。
3. 拉取 Windows 当天跑数结果到 `/Users/dong/ZhangData/market-data`。
4. 更新 Mac 本地 `live`、`research/current/selection`、`research/current/market_heat`。
5. 不把完整 66G/67G atomic 大库拉到 Mac。

完成标准：

1. Mac 页面所需的 live、selection、model feature、market heat 都有当天数据。
2. Mac 本地研究站能读到当天复盘、选股候选、市场热度。
3. Mac 不新增完整大库常驻副本。

## 7. NAS 执行方案

NAS 不在 Windows 跑数期间改。

跑数完成、Mac 同步完成后再做：

1. 对比 Mac 与 NAS 的正式 data 差异。
2. 同步线上需要的数据：
   - `live/market_data.db`
   - `live/user_data.db` 如有必要
   - `research/current/selection/selection_research.db`
   - `research/current/selection/model_feature_store.db`
   - `research/current/selection/model_market_index_daily.db`
   - `research/current/market_heat/*`
   - `research/current/atomic_facts/market_atomic_mainboard_compact_current.db` 只在确认需要更新大库时处理
3. 保留 NAS Docker data 里的完整库，不从 Mac 覆盖成轻量库。
4. 如代码有新提交，更新 NAS app 并重启 full compose。

完成标准：

1. NAS `/api/health` 正常。
2. 首页/盯盘接口能读当天数据。
3. 复盘池能看到当天或最新交易日。
4. 选股候选能看到当天 run 结果。
5. 市场热度能看到当天日期和 dashboard。
6. 研究上下文接口不报缺表。
7. Docker 容器 `backend / frontend / crawler` 都处于 running。

## 8. 推荐执行顺序

等用户通知“Windows 跑数完成”后，按这个顺序：

1. 只读核查 Windows 跑数是否完整。
2. 只读核查 Mac / NAS 当前数据版本。
3. 如果 Windows 跑数完整，先把 Windows 结果同步到 Mac。
4. 在 Mac 上跑本地冒烟。
5. 给 Windows 补最低表结构。
6. 对比 Mac 与 NAS 差异。
7. 把线上需要的数据同步到 NAS。
8. 如代码或部署目录不一致，更新 NAS app。
9. 跑 NAS 线上冒烟。
10. 写同步结果报告。

## 9. 不做事项

本次方案明确不做：

1. 不把 Windows 改成开发仓。
2. 不在 Windows 上部署前端页面。
3. 不在 Windows 跑数过程中搬库或改库。
4. 不把 Mac 变成完整大库存储机。
5. 不替用户做整文件夹冷备。
6. 不删除 Windows 旧物理目录。
7. 不删除 NAS Docker data 里的完整库。

## 10. 风险与回滚

### 10.1 Windows 风险

风险：补表结构时误碰正在写入的库。

控制：

1. 必须先确认跑数进程结束。
2. 补结构前记录库大小、修改时间、表清单。
3. 只执行 `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN` 这类轻量动作。
4. 不做 `DROP`、不做 `DELETE`、不做大范围重写。

### 10.2 NAS 风险

风险：把 NAS 完整库误覆盖成 Mac 轻量库。

控制：

1. 同步前明确每个文件方向。
2. 对 atomic 大库单独确认，不跟普通小文件一起批量覆盖。
3. 先同步小库和 market heat，再处理大库。

### 10.3 Mac 风险

风险：本地研究站误读旧路径。

控制：

1. 默认路径已经收口到 `/Users/dong/ZhangData/market-data`。
2. 冒烟时打印关键 env 和 DB path。
3. 不再使用桌面旧 AIGC 目录作为运行源。

## 11. 给用户的确认口径

后续用户只需要给一句话：

> Windows 今天跑数完成了，可以按同步方案执行。

收到后再开始动 Windows / NAS。

如果用户只说“先看一下”，则只做只读核查，不改任何远端文件。
