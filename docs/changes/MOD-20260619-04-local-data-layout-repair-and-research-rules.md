# MOD-20260619-04 本地数据排布修复与研究产物规则

日期：2026-06-19
状态：`LOCAL_LAYOUT_CLEAN_PENDING_NAS_SYNC`

## 结论

本轮只修 Mac 本地正式仓库，不动 NAS/Windows。目标是把代码仓和数据仓分离后暴露的问题收口，并把后续研究产物规则写清楚。

## 已修问题

1. 复盘页历史只到 6 月 9 日：长周期复盘已回到日级历史口径。
2. 选股页市场水位没数据：已恢复水位历史读取和合并口径。
3. 缺本地大库日期时策略报错：已改为返回空状态，不再中断页面。
4. PPO 回测复盘没数据：已补回模型回测产物到数据仓。
5. 后端启动静态挂载报错：已修路由日志读取方式。
6. 选股页顶部股票卡压缩意图不稳定：已把 `compact` 做成公共卡片的显式模式。

## 研究产物签收

1. 旧 `docs/selection/*_2026-*` 和 `docs/strategy-rework/**/experiments/*` 先按历史实验包签收，不再作为新机器产物落点。
2. 旧 `.run` 已迁入 `market-data/runs`，代码仓副本已移除。
3. 旧 `public/research` 已迁入 `market-data/artifacts/research_payloads`，代码仓副本已移除；页面 `/research` 改由后端从数据仓提供。
4. 新研究、新模型、新回测必须默认写入 `market-data/artifacts` 或 `market-data/runs`；代码仓只放人读结论、说明和小型样例。

## 代码仓清理

1. `data/selection` 已迁入 `market-data/artifacts/selection`，代码仓副本已删除。
2. 本地日跑、盘后 L2、状态查询、crawler 运行痕迹默认写入 `market-data/runs`。
3. NAS full compose 已改为 `data/artifacts/selection`、`data/artifacts/research_payloads`、`data/runs`。

## 仍需后续处理

1. Mac 本地仍缺部分大库历史，用户已确认暂不处理。
2. 旧脚本里仍有少量历史输出路径；后续重新启用旧脚本时，按当前数据仓规则改输出。
3. 页面级点击验证交给用户；本轮只做代码层和接口层验证。
