# AI_QUICK_START

## 当前真相
- 当前稳定基线目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前主线分支：`main`
- 当前工作版本：`v5.2.2`
- 当前真实运行模式：**Mac 主开发控制台 + Windows 数据主站 + NAS 在线运行节点**
- 当前 Mac 正式主读数据根目录：`/Users/dong/Desktop/AIGC/market-data`
- 当前已验证 NAS 直连入口：`dxp4800pro` / `100.119.0.126`
- 当前已验证 NAS 公网入口：`https://dxp4800pro.tailfff556.ts.net/`
- 当前已验证 NAS Git 主入口：`nas-git:zhangdong/market-live-terminal.git`
- 当前 NAS Git 局域网备用入口：`ssh://git@192.168.3.43:2222/zhangdong/market-live-terminal.git`
- 当前正式端口口径：本地前端 `3001`、本地后端 `8001`、NAS 项目 Web `8080`、NAS Gitea `3000`；`8000` 仅按容器内部 backend 端口理解，`5173/5174` 只按历史临时调试端口理解
- repo 内 `data/` 只按本地回退/兼容副本理解，不是默认正式研究根目录
- 正式数据根按 `live / research/current / cache / artifacts / incoming` 收口；repo 内 `data/` 仅兼容/fallback
- 当前项目真相总入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
- 当前运行架构总入口：`docs/01_SYSTEM_ARCHITECTURE.md`
- 当前唯一持续更新研究目录：`docs/selection/long_term_trends/`
- 当前阶段回滚锚点：
  - 老阶段：`stage-pre-selection-v4.2.32`
  - 选股进行中阶段：`stage-selection-in-progress-v4.3.2`

## 只允许修改的主区域
- 前端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/src`
- 后端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/backend`
- 发布与部署：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy`
- 项目文档：`/Users/dong/Desktop/AIGC/market-live-terminal/docs`

## 禁止当作当前主线开发目录
- 本地虚拟环境：`/Users/dong/Desktop/AIGC/market-live-terminal/.venv`
- 本地运行产物：`/Users/dong/Desktop/AIGC/market-live-terminal/.run`

## 当前 worktree / 分支纪律
- 当前唯一主工作目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前唯一主线分支：`main`
- `codex/*` 分支只承接当前需求；历史 worktree / 临时分支只作为备份，不再作为默认开发入口
- 若存在多个 worktree，默认只在上述主工作目录整理文档和做主线收口。
- 若要做治理线收口，先在 `main` 只读排查；进入写入阶段时，治理工作必须放到独立治理分支 / worktree。

## 当前数据职责
- NAS：线上前后端、`live/` 轻量盯盘、`research/current` 在线查询、发布/回滚节点
- Windows：raw + 盘后明细底座 + 选股研究 + 模型特征 + 跑数
- Mac：复盘 + 选股 + 本地前后端 + 文档/开发，读取本机同步后的正式库
- Windows 盘中 crawler 仍是当前正式基线；NAS crawler 已跑通但还在观察期，Windows 暂未下线

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash scripts/check_baseline.sh
```

## 当前工作原则
1. 复盘/选股/研究型改动优先按 **Mac 本地研究站** 设计，不默认以上生产为目标。
2. 不把 `38GB+` 盘后明细底座放到云端；**Mac 允许保留一份处理后全量库**。
3. 当前最新冻结：**raw 只留 Windows；处理后正式研究库由 Windows 产出、Mac 主读、NAS 走 `research/current` 在线查询；repo 内 `data/` 只按回退/兼容副本理解。**
4. Mac 不直接跨网络读 Windows sqlite 主库。
5. `snapshot` 只作为验证/应急工具，不作为当前正式主方案。
6. 若要动生产发布，先确认这次改动是否真的属于“盯盘应急版”范围。
7. 清理 / stash / worktree 收口前，必须确认 `docs/selection/long_term_trends/` 没被隐藏或遗漏。

## 当前文档阅读顺序
1. `README.md`：确认当前工作目录、版本、模块边界
2. `docs/02_BUSINESS_DOMAIN.md`：只看能力地图与状态
3. `docs/03_DATA_CONTRACTS.md`：只看契约入口与分组
4. `docs/04_OPS_AND_DEV.md`：只看运维入口与常用脚本
5. `docs/ops/mac-nas-collaboration.md`：看 Mac 直连 NAS、远程查库、发布与公网域名规划
6. `docs/ops/port-management.md`：看本地 / NAS 正式端口与临时端口边界
7. 非正式 `ops` 脚本边界看 `docs/ops/atomic-script-families-boundary.md`
8. report / artifacts 的正式边界看 `docs/ops/report-and-artifact-boundary.md`
9. 若任务属于选股研究入口治理，先看 `docs/selection/daily_candidate_source_contract.md`，它是工作台统一候选池入口说明
10. 若想看选股历史脉络，先看 `docs/selection/selection_research_history_summary.md`
11. 需要细节时再进入：
   - `docs/domain/*`
   - `docs/contracts/*`
   - `docs/ops/*`
12. 若任务属于模型训练 / 研究方向探索，先看：
   - `docs/model-research/README.md`
   - `docs/model-research/research-directions-index.md`
   - `docs/model-research/evaluation-metrics-dictionary.md`
   - `docs/model-research/current-material-map.md`
   - `docs/model-research/worktree-lifecycle.md`
13. 选股策略细节先看 `docs/strategy-rework/LONG_MEMORY.md`；当前阶段状态补充看 `docs/strategy-rework/current-research-operating-summary.md`
14. 当前需求过程统一进 `docs/changes/*`
15. 开始做需求前，先看：`docs/ops/development-workflow.md`
16. 若任务涉及 skill 选择、项目级 AI 协作路由，补看：`docs/ops/ai-skill-routing.md`

## 当前治理固定产物
- `code review findings`：本轮代码审查发现与修复顺序
- `health snapshot`：当前分支 / worktree / 版本 / pending / 风险快照
- `current-state mother card`：某主题的当前真相入口
- `archive summary`：已结束主题的压缩结论

默认顺序：
`review -> health -> mother card -> archive`

## 当前关键脚本
- Windows -> Mac 首次全量同步：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/bootstrap_mac_full_processed_sync.sh`
- NAS 轻量部署：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/nas/deploy_nas_lite.sh`
- 本地研究站启动：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/start_local_research_station.sh`
- 本地研究站前端：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/start_local_research_frontend.sh`
- 每日盘后正式主链：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/run_daily_new_framework.sh`
- 新框架月批/阶段状态查询：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/check_windows_new_framework_months_status.sh`
- 兼容旧盘后链路：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/legacy/run_postclose_l2.sh`
- 旧盘后状态查询：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/legacy/check_postclose_l2_status.sh`
- Windows -> Mac 旧快照同步（仅过渡验证）：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/legacy/sync_windows_research_snapshot.sh`
- atomic 兼容直启（仅兼容排查）：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/legacy/start_local_backend_with_atomic.sh`

除白名单脚本外，其他 `ops` 脚本默认先按历史工具处理；具体边界见 `docs/ops/atomic-script-families-boundary.md`。

## 当前 NAS 最小入口

```bash
ssh zhangdong@dxp4800pro
```

```text
项目服务：http://dxp4800pro:8080
管理后台：https://100.119.0.126:9443
公网入口：https://dxp4800pro.tailfff556.ts.net/
```

当前默认规则：

- Mac -> NAS 直接走 Tailscale
- 不再默认经 Windows 跳转
- 默认上传方式优先 `tar | ssh`
- 当前 Git 推送优先 `git push nas main`；单文件上传可用 `scp -O`
- 当前公网已可直接使用 `Tailscale Funnel`；只有要固定品牌域名时，才再补 `Cloudflare Tunnel + 自定义域名`

## 每天盘后要跑的指令
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_daily_new_framework.sh --json
```

默认不传日期。脚本会自动查 Windows 日包，跳过已完整日期，只补最新完整日之后的缺失日期；完成标准包含 Windows 跑数、Mac delta 合并、市场环境指数、热点长表、热点页面缓存、model feature store，以及选股工作台活跃模型/策略产出。

补充：
- `--sync-nas` 当前负责把 Mac 已确认正确的正式 `live` 结果同步到 NAS 生产库，并后台启动一轮 NAS 数据库快照
- 这条主链现在会在本地校验通过后，顺手补一次 Mac 本地 `live/market_data.db` 的 `postclose_l2` 历史并刷新 `stock_universe_meta`
- 整套 `research/current` 的大体量发布仍保留为单独动作，不再绑进每天跑数后的默认收口

## 本地研究站最小启动顺序
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
# 首次：先把 Windows 处理后全量库同步到 Mac
bash ops/bootstrap_mac_full_processed_sync.sh

# 启动本地研究站
PORT=8001 bash ops/start_local_research_station.sh
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

补充约束：
- 不要手工并行启动多个 `backend.app.main`；
- 现在 `ops/start_local_research_station.sh` 已内置同仓库重复实例保护，重复执行会自动替换旧实例，不会继续叠后端进程。

## 当前同步约定
- `snapshot` 已降级为过渡验证工具，不是正式主方案；
- `ops/legacy/sync_windows_research_snapshot.sh`、`backend/scripts/legacy/compat/build_local_research_snapshot.py`、`ops/legacy/start_local_backend_with_atomic.sh` 只按兼容/验证工具理解；
- 当前正式方案是：
  - 首次把 Windows 的处理后全量库整库同步到 Mac；
  - 后续每天执行 `./ops/run_daily_new_framework.sh --json` 做正式主链增量日跑，日期由脚本自动检测；
  - 查询新框架月批或阶段状态时用 `./ops/check_windows_new_framework_months_status.sh`；
  - `./ops/legacy/run_postclose_l2.sh` 只保留为旧盘后 L2 / cloud 同步兼容链路；
  - Windows -> Mac 数据同步只允许两条路径：
    - 局域网 HTTP 直拉
    - Windows 上传云端 relay，Mac 再下载
  - 禁止再走 Windows -> Mac 的 SSH/scp 直拉。

## 当前清理原则
- 不要直接在正式 `market_data_main`（默认 `market-data/live/market_data.db`）里删旧表；
- 若要验证旧表是否还能删，先复制测试库，再让本地服务指向测试副本做回归。

## 当前回退入口
- 老阶段回退：`stage-pre-selection-v4.2.32`
- 选股进行中阶段回退：`stage-selection-in-progress-v4.3.2`
- 当前工作版本：`v5.2.2`
- 运行架构当前入口：`docs/01_SYSTEM_ARCHITECTURE.md`
