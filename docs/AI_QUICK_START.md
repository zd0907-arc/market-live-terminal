# AI_QUICK_START

## 当前真相
- 当前稳定基线目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前主线分支：`main`
- 当前主线代码版本：`v5.0.0`
- 当前真实运行模式：**云端只保留轻量盯盘；Windows 做数据主站；Mac 做本地研究工作台**
- 当前项目真相总入口：`docs/changes/MOD-20260421-01-project-current-state-and-doc-governance-normalization.md`
- 当前运行架构总入口：`docs/changes/MOD-20260417-01-local-research-current-state.md`
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
- 历史 worktree / 临时分支只作为备份，不再作为默认开发入口

## 当前数据职责
- 云端：盯盘 / 手机应急查看
- Windows：raw + full atomic + 跑数 + 研究结果产出
- Mac：复盘 + 选股 + 本地前后端 + 文档/开发，读取本机同步后的正式库

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
npm run check:baseline
```

## 当前工作原则
1. 复盘/选股/研究型改动优先按 **Mac 本地研究站** 设计，不默认以上生产为目标。
2. 不把 `38GB+` full atomic 主库放到云端；**Mac 允许保留一份处理后全量库**。
3. 当前最新冻结：**raw 只留 Windows；处理后全量库 Windows / Mac 各保留一份；Cloud 只保留轻量盯盘数据。**
4. Mac 不直接跨网络读 Windows sqlite 主库。
5. `snapshot` 只作为验证/应急工具，不作为当前正式主方案。
6. 若要动生产发布，先确认这次改动是否真的属于“盯盘应急版”范围。

## 当前文档阅读顺序
1. `docs/02_BUSINESS_DOMAIN.md`：只看能力地图与状态
2. `docs/03_DATA_CONTRACTS.md`：只看契约入口与分组
3. `docs/04_OPS_AND_DEV.md`：只看运维入口与常用脚本
4. 需要细节时再进入：
   - `docs/domain/*`
   - `docs/contracts/*`
   - `docs/ops/*`
5. 当前需求过程统一进 `docs/changes/*`

## 当前关键脚本
- Windows -> Mac 首次全量同步：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/bootstrap_mac_full_processed_sync.sh`
- 本地研究站启动：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/start_local_research_station.sh`
- 本地研究站前端：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/start_local_research_frontend.sh`
- 每日盘后总控：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/run_postclose_l2.sh`
- 每日盘后状态查询：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/check_postclose_l2_status.sh`
- Windows -> Mac 旧快照同步（仅过渡验证）：`/Users/dong/Desktop/AIGC/market-live-terminal/ops/sync_windows_research_snapshot.sh`

## 本地研究站最小启动顺序
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
# 首次：先把 Windows 处理后全量库同步到 Mac（同 WiFi 默认优先走 192.168.3.108）
bash ops/bootstrap_mac_full_processed_sync.sh

# 启动本地研究站
PORT=8001 bash ops/start_local_research_station.sh
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

## 当前同步约定
- `snapshot` 已降级为过渡验证工具，不是正式主方案；
- 当前正式方案是：
  - 首次把 Windows 的处理后全量库整库同步到 Mac；
  - 后续每天执行 `./ops/run_postclose_l2.sh` 做增量日跑；
  - 查询状态用 `./ops/check_postclose_l2_status.sh`；
  - 当前本地正式库已验证到 `2026-04-15`。

## 当前清理原则
- 不要直接在正式 `data/market_data.db` 里删旧表；
- 若要验证旧表是否还能删，先复制测试库，再让本地服务指向测试副本做回归。

## 当前回退入口
- 老阶段回退：`stage-pre-selection-v4.2.32`
- 选股进行中阶段回退：`stage-selection-in-progress-v4.3.2`
- 当前主线代码版本：`v5.0.0`
- 运行架构回看：`docs/changes/MOD-20260417-01-local-research-current-state.md`
