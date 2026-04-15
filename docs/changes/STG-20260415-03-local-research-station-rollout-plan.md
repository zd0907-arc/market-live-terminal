# STG-20260415-03 本地研究站落地路线图

> 本卡是 `MOD-20260415-02-local-research-station-architecture.md` 的执行卡。
> 目标不是重复解释为什么改，而是冻结：**接下来按什么顺序做、在哪做、做到什么算完成。**

## 1. 当前开发落点（冻结）
- 主开发 worktree：`/Users/dong/Desktop/AIGC/market-live-terminal-local-research`
- 主开发分支：`codex/local-research-station-20260415`
- `main`：只作为稳定基线与后续合并目标
- `codex/selection-hotfix-v4.3.1`：历史热修上下文，不再承载新需求

## 2. 总目标
把系统收口成：
- 云端：只保留盯盘
- Windows：full atomic + 盘后跑数 + 研究结果产出
- Mac：复盘 + 选股 + 本地前后端 + 研究工作台

## 3. 实施顺序

### Phase A：文档与边界冻结
- 完成母卡、核心文档、AI 入口、待办项统一
- 明确 worktree / branch 纪律
- 结果：后续开发不再以“full atomic 切生产”为默认目标

### Phase B：Windows -> Mac 全量处理后库同步链路
- 冻结同步对象：
  - `data/market_data.db`
  - `data/atomic_facts/market_atomic_mainboard_full_reverse.db`
  - `data/selection/selection_research*.db`
- 冻结同步方式：
  - 首次：整库全量同步到 Mac；
  - 后续：按交易日做增量同步；
  - 本地覆盖前保留回退快照。
- 结果：Mac 持有与 Windows 同口径的处理后全量库。
- 当前已落地（过渡态工具）：
  - `backend/scripts/build_local_research_snapshot.py`
  - `ops/sync_windows_research_snapshot.sh`
  - `ops/start_local_research_station.sh`
  - `ops/start_local_research_frontend.sh`
- 当前结论：
  - 以上“snapshot”链路只作为开发验证过渡，不再是最终日常方案；
  - 下一步要把 `./ops/run_postclose_l2.sh` 升级为：
    1. Windows 跑当日处理；
    2. 云端同步轻量盯盘数据；
    3. Mac 同步处理后全量库的日增量。
  - 当前已落地第一版：
    - Windows `market_data.db` 单日 merge
    - Mac `market_data.db` 单日 merge
    - Windows `atomic / selection` 单日更新
    - Mac `atomic / selection` 单日增量合并
    - `--bootstrap-mac-full-sync` 首次整库同步

### Phase C：Mac 本地读路径切换
- 复盘页切到本地 full processed DB
- 选股页切到本地 full `selection_research.db`
- 页面 smoke：
  - 选股页能出候选
  - 复盘页能看图和资金流
- 盯盘页能同时看到：
  - 历史 finalized 数据
  - 本地今日实时数据
- 结果：Mac 成为可稳定使用的研究工作台

### Phase D：云端收口
- 云端只保留盯盘必要链路
- 不再继续把复盘/选股重型前提强推上云
- 若后续要扩回生产，另开卡评审

## 4. 验收口径

### P1 验收
- Mac 能手动/脚本拉取最新快照
- 快照有时间戳/大小校验
- 已验证：
  - Windows -> Mac 真实拉取成功；
  - 本地生成文件：
    - `data/local_research/research_snapshot.db`
    - `data/local_research/selection/selection_research.db`
    - `data/local_research/research_snapshot_manifest.json`

### P2 验收
- 本地 `/api/selection/*` 正常
- 本地复盘主页面读取快照正常
- 不依赖跨网络直读 Windows sqlite
- 已验证：
  - `PORT=8001 bash ops/start_local_research_station.sh`
  - `/api/selection/health` 正常
  - `/api/selection/candidates?trade_date=2026-04-10&strategy=breakout&limit=3` 正常
  - `/api/review/pool` 与 `/api/review/data?symbol=sh603629...` 正常

### P3 验收
- 云端盯盘仍正常
- 新研究架构不影响生产盯盘

## 5. 红线
- 不在 `main` 上直接开发本轮架构改造
- 不把 38G full atomic 默认同步到 Mac
- 不让 Mac 页面长期依赖远程 Windows sqlite
- 不把本地研究型能力误发布成“生产必备能力”

## 6. 当前已知缺口
- Windows 端正式 `selection_research.db` 还未稳定产出；
- 因此当前同步脚本仍保留一个 **Mac 本地 bootstrap selection DB** 兜底；
- 后续要把这块彻底扶正，需要单独补 Windows 端的 selection 产出流程。
