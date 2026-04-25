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

## 3. 当前正式消费对象
优先使用外置数据根目录：`/Users/dong/Desktop/AIGC/market-data`。启动脚本会自动把它映射成：
- `DB_PATH=/Users/dong/Desktop/AIGC/market-data/market_data.db`
- `USER_DB_PATH=/Users/dong/Desktop/AIGC/market-data/user_data.db`
- `ATOMIC_MAINBOARD_DB_PATH=/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
- `SELECTION_DB_PATH=/Users/dong/Desktop/AIGC/market-data/selection/selection_research.db`

若外置目录不存在，才回退到项目内 `data/`。

## 3.1 本地盯盘数据语义
- 本地页面默认读取 Mac 本机同步库，不跨网络直接查询 Windows sqlite。
- 默认不启动后台实时外采：`ENABLE_BACKGROUND_RUNTIME=false`、`ENABLE_CLOUD_COLLECTOR=false`。
- 单票当日数据陈旧时，后端可按需调用行情源补拉该票 ticks 并写入本地库。
- 这不是生产连续 crawler；生产连续盯盘仍以 Windows -> Cloud ingest 链路为准。

## 4. 日常 smoke
- `/api/health`
- `/api/review/pool`
- `/api/selection/health`
- `/api/selection/candidates`

## 5. 不要做的事
- 不要直接跨网络读 Windows sqlite 主库
- 不要把 Mac 本地临时验证库当成长期主库
- 不要在 `main` 上直接堆实验改动
