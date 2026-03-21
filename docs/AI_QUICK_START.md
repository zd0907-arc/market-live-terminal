# AI_QUICK_START

## 当前真相
- 当前权威工作目录：`/Users/dong/Desktop/AIGC/market-live-terminal`
- 当前版本：`v4.2.28`
- 当前主线分支：`main`
- 当前临时工作分支规范：`codex/<feat|fix|chore>-<topic>-YYYYMMDD`
- 当前产品回退 Tag：`v4.2.28`
- 显式回滚别名 Tag：`baseline-v4.2.28-legacy-toggle`
- 上一产品版本 Tag：`v4.2.27`
- 当前基线归档：`docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`
- 深度治理回退 Tag：`snapshot-20260318-pre-governance`
- 当前回退分支：`codex/archive-pre-governance-20260318`

## 只允许修改的主区域
- 前端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/src`
- 后端源码：`/Users/dong/Desktop/AIGC/market-live-terminal/backend`
- 发布与部署：`/Users/dong/Desktop/AIGC/market-live-terminal/deploy`
- 项目文档：`/Users/dong/Desktop/AIGC/market-live-terminal/docs`

## 禁止当作当前主线开发目录
- 历史旧副本：`/Users/dong/Desktop/AIGC/market-live-terminal/market-live-terminal`
- 本地虚拟环境：`/Users/dong/Desktop/AIGC/market-live-terminal/.venv`
- 本地运行产物：`/Users/dong/Desktop/AIGC/market-live-terminal/.run`

## 权威数据路径
- 主业务库：`/Users/dong/Desktop/AIGC/market-live-terminal/data/market_data.db`
- 用户配置库：`/Users/dong/Desktop/AIGC/market-live-terminal/data/user_data.db`
- 沙盒复盘库：`/Users/dong/Desktop/AIGC/market-live-terminal/data/sandbox_review.db`

## 最小自检
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
npm run check:baseline
```

## 标准开分支模板
```bash
git checkout main && git pull
git checkout -b codex/<feat|fix|chore>-<topic>-YYYYMMDD
# 改代码 → 小步提交
npm run check:baseline
git checkout main && git merge --no-ff <branch>
# 若已影响生产：同步 bump 版本 + tag
```

## 发布前最小检查项
1. 只在仓库根目录开发，不进入旧副本目录。
2. `npm run check:baseline` 必须通过。
3. `package.json`、`src/version.ts`、`README.md`、`backend/app/main.py` 版本必须一致。
4. 前端不得持有 `WRITE_API_TOKEN`；写鉴权仅允许通过服务端代理/环境变量注入。

## 当前回退入口
- 产品代码回退：优先切回 `v4.2.28`（commit `c1eec34`）或上一版 `v4.2.27`
- 当前版本页面/数据基线：`docs/archive/changes/ARC-CHG-20260321-v4-2-28-last-legacy-toggle-baseline.md`
- 深度治理回退：`snapshot-20260318-pre-governance` 或 `codex/archive-pre-governance-20260318`
- 数据/配置回退目录：`/Users/dong/Desktop/AIGC/backups/market-live-terminal/20260318-pre-governance/`
