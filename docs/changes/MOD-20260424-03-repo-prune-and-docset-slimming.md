# MOD-20260424-03 仓库瘦身与文档集收敛

## 1. 基本信息
- ID：`MOD-20260424-03`
- 类型：`MOD`
- 状态：`ACTIVE`
- 发起时间：`2026-04-24 23:55 CST`
- 执行分支：`codex/chore-repo-prune-audit-20260424`

## 2. 背景
- 当前核心文档 `00~08` 已归一，但 `docs/` 根目录仍混有一个低价值索引页；
- 仓库根目录仍保留一批早期调试脚本、样本产物、Trae 计划文件、嵌套旧副本；
- 这些内容已经不再构成当前正式入口，却会继续增加误读与维护成本。

## 3. 本轮目标
1. 明确 `docs/` 根目录必须保留的文档集；
2. 删除纯索引/纯历史/无正式引用的低价值文件；
3. 清理本地嵌套旧副本与明显无用运行产物；
4. 回填核心文档，保证仓库入口与现状一致。

## 4. 保留原则
- `00~08`：全部保留，继续作为核心文档集；
- `AI_QUICK_START.md`：保留，作为 AI/接手时的最小入口；
- `AI_HANDOFF_LOG.md`：保留，作为短日志；
- `docs/archive/**`：保留，承接历史；
- 纯索引且正文已完全并入核心文档的文件，可删除；
- 无当前引用、无正式运行职责、且明显属于历史调试/样本产物的脚本与文件，可删除。

## 5. 本轮拟清理对象
### 5.1 文档
- `docs/REMOTE_CONTROL_GUIDE.md`

### 5.2 跟踪但低价值的历史文件
- `.trae/documents/plan_*.md`
- `push_db_to_cloud.sh`
- `etl_autorun.bat`
- `test_env.py`
- `market.db`
- `metadata.json`
- `mined_comments.txt`
- `scripts/init_sentiment_db.py`
- `scripts/mine_keywords.py`
- `scripts/update_keywords.py`

### 5.3 本地未跟踪残留（不再作为仓库内容保留）
- `market-live-terminal/` 嵌套旧副本
- `backend.log`
- `frontend.log`

## 6. 验收
- `docs/` 根目录不再保留 `REMOTE_CONTROL_GUIDE.md`；
- `README / 08 / AI_QUICK_START` 不再把已删除对象写成当前入口；
- Git 跟踪文件中不再保留上述低价值历史文件；
- `npm run check:baseline` 通过。

## 7. 结果回填
- 当前进度（`2026-04-25 00:10 CST`）：
  - 已删除 `docs/REMOTE_CONTROL_GUIDE.md`，远控唯一入口明确收敛到 `04_OPS_AND_DEV.md`；
  - 已删除一批无当前引用的历史调试/样本文件：
    - `.trae/documents/plan_*.md`
    - `push_db_to_cloud.sh`
    - `etl_autorun.bat`
    - `test_env.py`
    - `market.db`
    - `metadata.json`
    - `mined_comments.txt`
    - `scripts/init_sentiment_db.py`
    - `scripts/mine_keywords.py`
    - `scripts/update_keywords.py`
  - 已清理本地未跟踪残留：
    - 嵌套旧副本 `market-live-terminal/`
    - `backend.log`
    - `frontend.log`
  - 已回填 `README / 04 / 08 / AI_QUICK_START / .gitignore`。
