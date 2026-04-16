# AI_QUICK_START

## 当前真相
- 当前稳定基线目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前主线分支：`main`
- 当前生产代码版本：`v4.3.1`
- 当前真实运行模式：**云端只保留轻量盯盘；Windows 做数据主站；Mac 做本地研究工作台**
- 当前运行架构总入口：`docs/changes/MOD-20260415-02-local-research-station-architecture.md`
- 当前生产回滚锚点：`v4.2.32`

## 只允许修改的主区域
- 前端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/src`
- 后端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/backend`
- 发布与部署：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy`
- 项目文档：`/Users/dong/Desktop/AIGC/market-live-terminal/docs`

## 禁止当作当前主线开发目录
- 历史旧副本：`/Users/dong/Desktop/AIGC/market-live-terminal/market-live-terminal`
- 本地虚拟环境：`/Users/dong/Desktop/AIGC/market-live-terminal/.venv`
- 本地运行产物：`/Users/dong/Desktop/AIGC/market-live-terminal/.run`

## 当前 worktree / 分支纪律
- 稳定基线 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal`（仅保留 `main`）
- 本轮主开发 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research`
- 本轮主开发分支：`codex/local-research-station-20260415`
- 历史热修/数据治理 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-data-governance`
- 当前原则：**本轮新架构与本地研究站实现，一律在 `market-live-terminal-local-research / codex/local-research-station-20260415` 上推进**

## 当前数据职责
- 云端：盯盘 / 手机应急查看
- Windows：raw + full atomic + 跑数 + 研究结果产出
- Mac：复盘 + 选股 + 本地前后端 + 文档/开发

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal-local-research
npm run check:baseline
```

## 当前工作原则
1. 复盘/选股/研究型改动优先按 **Mac 本地研究站** 设计，不默认以上生产为目标。
2. 不把 `38GB+` full atomic 主库放到云端；**Mac 允许保留一份处理后全量库**。
3. 当前最新冻结：**raw 只留 Windows；处理后全量库 Windows / Mac 各保留一份；Cloud 只保留轻量盯盘数据。**
4. Mac 不直接跨网络读 Windows sqlite 主库。
5. 若要动生产发布，先确认这次改动是否真的属于“盯盘应急版”范围。

## 当前关键脚本
- Windows -> Mac 首次全量同步：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research/ops/bootstrap_mac_full_processed_sync.sh`
- Windows -> Mac 旧快照同步（仅过渡验证）：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research/ops/sync_windows_research_snapshot.sh`
- 本地研究站启动：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research/ops/start_local_research_station.sh`
- 本地研究站前端：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research/ops/start_local_research_frontend.sh`
- 历史盘后总控旧入口：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research/ops/run_postclose_l2.sh`

## 本地研究站最小启动顺序
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal-local-research
# 首次：先把 Windows 处理后全量库同步到 Mac（同 WiFi 默认优先走 192.168.3.108）
bash ops/bootstrap_mac_full_processed_sync.sh

# 启动本地研究站
PORT=8001 bash ops/start_local_research_station.sh
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

## 当前同步约定
- 当前过渡态 `snapshot` 只用于开发验证；
- 最终目标是：
  - 首次把 Windows 的处理后全量库整库同步到 Mac；
  - 后续每天只同步新增交易日的处理结果；
  - `./ops/run_postclose_l2.sh` 需要升级为这套新语义的一键入口。

## 当前回退入口
- 生产轻量版回退：`v4.2.32`
- 当前生产代码版本：`v4.3.1`
- 运行架构回看：`docs/changes/MOD-20260415-02-local-research-station-architecture.md`
