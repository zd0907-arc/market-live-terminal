# Mac 本地研究站

## 1. 作用
Mac 是当前正式的本地研究与开发环境，负责：
- 启动本地前后端
- 读取同步后的正式库
- 承载复盘 / 选股 / 文档治理

## 2. 日常启动顺序
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/bootstrap_mac_full_processed_sync.sh   # 首次或需要全量同步时
PORT=8001 bash ops/start_local_research_station.sh
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

默认：
- 前端：`http://localhost:3001`
- 后端：`http://127.0.0.1:8001`
- 端口规范：`docs/ops/port-management.md`

## 2.1 启动红线
- 本地后端必须通过 `ops/start_local_research_station.sh` 启动。
- 不要直接手工执行 `python -m backend.app.main`。
- 原因：正式脚本会注入外置数据根目录 `/Users/dong/Desktop/AIGC/market-data` 的 `DB_PATH / USER_DB_PATH / SELECTION_DB_PATH / ATOMIC_MAINBOARD_DB_PATH`；手工直跑容易退回项目内 `data/`，导致页面读到旧库，出现“历史多维停在旧日期”“盯盘页分时异常”等假故障。

## 2.2 重复实例防线
- `ops/start_local_research_station.sh` 已内置同仓库重复实例保护；再次执行时会先停掉旧实例，再启动新实例。
- 不要在多个终端重复 `nohup bash ops/start_local_research_station.sh`，也不要手工并行拉起多个 `python -m backend.app.main`。
- 重复实例的典型症状不是 `/api/health` 直接挂，而是：
  - `服务: 正常` 仍显示正常；
  - `历史多维`、`散户一致性观察`、`history/multiframe`、`sentiment/*` 这类业务接口开始一直转圈或超时；
  - 前端可能进一步出现动态模块加载失败、页面长期卡住。
- 快速排查：
  - `ps aux | rg 'backend\\.app\\.main'`：正常应只看到 1 个 Python 实例；
  - `lsof -nP -iTCP:8001 -sTCP:LISTEN`：正常应只看到 1 个监听进程。
- 快速恢复：
  - 直接重新执行 `PORT=8001 bash ops/start_local_research_station.sh`；
  - 脚本会自动清理同仓库旧实例并拉起干净的新实例。

## 2.3 前端端口纪律
- 本地前端正式端口固定为 `3001`。
- `5173`、`5174` 这类 Vite 临时端口不属于正式口径。
- `ops/start_local_research_frontend.sh` 现在会直接拉起本仓库 `vite`，并强制 `--strictPort`；若 `3001` 被占用，会直接报错，不再静默漂移。
- 正常恢复方式是重新执行：
  - `BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh`

## 2.4 兼容链边界
- `ops/legacy/sync_windows_research_snapshot.sh`
- `backend/scripts/legacy/compat/build_local_research_snapshot.py`
- `ops/legacy/start_local_backend_with_atomic.sh`

这三项只属于旧快照验证、兼容排查或人工应急链，不属于当前正式本地研究入口。

你现在如果只是想正常打开本地研究站、验证页面、继续开发，默认不要走这条链。

## 3. 当前正式消费对象
优先使用外置数据根目录：`/Users/dong/Desktop/AIGC/market-data`。启动脚本会自动把它映射成：
- `DB_PATH=/Users/dong/Desktop/AIGC/market-data/live/market_data.db`
- `USER_DB_PATH=/Users/dong/Desktop/AIGC/market-data/live/user_data.db`
- `ATOMIC_COMPACT_DB_PATH=/Users/dong/Desktop/AIGC/market-data/research/current/atomic_facts/market_atomic_mainboard_compact_current.db`
- `ATOMIC_MAINBOARD_DB_PATH` 在默认开启 compact 读取时会落到上述 compact 主路径
- `SELECTION_DB_PATH=/Users/dong/Desktop/AIGC/market-data/research/current/selection/selection_research.db`
- `model_feature_store` 正式主读路径：`/Users/dong/Desktop/AIGC/market-data/research/current/selection/model_feature_store.db`

若外置目录不存在，才回退到项目内 `data/`。

## 3.1 本地盯盘数据语义
- 本地页面默认读取 Mac 本机同步库，不跨网络直接查询 Windows sqlite。
- 默认不启动后台实时外采：`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`。
- 单票当日数据陈旧时，后端可按需调用行情源补拉该票 ticks 并写入本地库。
- 这不是生产连续 crawler；生产连续盯盘当前仍以 Windows -> NAS 在线后端 ingest 链路为准。NAS crawler 已跑通，但 Windows 暂未下线。

## 4. 日常 smoke
- `/api/health`
- `/api/review/pool`
- `/api/selection/health`
- `/api/selection/candidates`

## 5. 不要做的事
- 不要直接跨网络读 Windows sqlite 主库
- 不要把 Mac 本地临时验证库当成长期主库
- 不要在 `main` 上直接堆实验改动
