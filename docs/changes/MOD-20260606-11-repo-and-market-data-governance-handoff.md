# 仓库与 market-data 治理接手文档

## 1. 这份文档是干什么的

这份文档不是过程卡，也不是泛泛总结。

它只服务一个目标：

如果后续换一个没有当前对话上下文的 AI，它应当只靠这份文档和文中链接，就能继续把 `repo + market-data` 治理做下去，而不会把已经完成的内容重做一遍，也不会误清正式主库。

当前对应主卡：

- [MOD-20260606-10-repo-and-market-data-structure-governance-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md)

当前活跃待办：

- [07_PENDING_TODO.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/07_PENDING_TODO.md)

## 2. 接手时先看什么

按这个顺序看，不要反过来：

1. 先看本文档。
2. 再看主治理卡：
   - [MOD-20260606-10-repo-and-market-data-structure-governance-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md)
3. 再看当前活跃待办：
   - [07_PENDING_TODO.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/07_PENDING_TODO.md)
4. 再看运行与存储边界：
   - [04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md)
   - [storage.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/contracts/storage.md)
   - [market-data-reclassification-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/market-data-reclassification-plan.md)
   - [backend-script-families-boundary.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/backend-script-families-boundary.md)
5. 最后只把 [AI_HANDOFF_LOG.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_HANDOFF_LOG.md) 当短日志看，不要拿它替代主卡。

## 3. 当前真实结论

### 3.1 这轮治理已经做到了哪里

当前大约完成了 `50%~55%`。

已经完成的是：

1. 运行真相已经冻结。
2. 三端职责已经对齐。
3. 第一批和第二批低风险目录治理已经落地。
4. 核心文档已经从“旧口径”回写到“当前口径”。

还没完成的是：

1. repo 内 fallback 库最终边界。
2. `market-data` 第二批对象的物理治理。
3. 防止后续继续乱写的正式反熵规则。

### 3.2 三端当前正式口径

| 端 | 正式职责 | 当前正式数据位置 |
|---|---|---|
| Mac | 开发控制台、本地研究站、文档与发布控制台 | `/Users/dong/Desktop/AIGC/market-data` |
| Windows | 数据主站、盘中 crawler、盘后正式跑数与主产出 | Windows 本地正式产出目录，随后同步到 Mac / NAS |
| NAS | 在线服务、在线轻量库、`research/current` 在线查询、发布与回滚节点 | `/volume1/docker/market-live-terminal/data/live` + `/volume1/docker/market-live-terminal/data/research/current` |

重要提醒：

1. “三端已对齐”指的是职责、入口脚本、环境变量解析、发布链和文档真相对齐。
2. 这不等于 Mac `market-data` 和 NAS 上所有历史目录都已经物理整理干净。

## 4. 已完成事项

### 4.1 文档入口与治理骨架

已完成：

1. `docs/changes` 顶层已压缩，只保留当前高价值入口。
2. 当前治理主卡、活跃待办、短日志之间的引用关系已建立。
3. 高曝光文档已回写，不再把 repo 内 `data/` 讲成默认正式主库。

重点文档：

- [README.md](/Users/dong/Desktop/AIGC/market-live-terminal/README.md)
- [AI_QUICK_START.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_QUICK_START.md)
- [04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md)
- [storage.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/contracts/storage.md)

### 4.2 外置 market-data 第一批治理

已完成：

1. 已建立这些目录：
   - `/Users/dong/Desktop/AIGC/market-data/artifacts/model_feature_store`
   - `/Users/dong/Desktop/AIGC/market-data/artifacts/market_heat`
   - `/Users/dong/Desktop/AIGC/market-data/artifacts/reports`
   - `/Users/dong/Desktop/AIGC/market-data/artifacts/selection`
2. 已下沉这些对象：
   - `selection/model_feature_store.db.backup_20260602_101012`
   - `selection/model_feature_store.db.repaired`
   - `legacy_market_merge_report_20260425.json`
   - `selection/model_market_index_daily_validation_20260523.json`
3. 已删除两个明确 `0B` 空壳：
   - `/Users/dong/Desktop/AIGC/market-data/market_feature_store.db`
   - `/Users/dong/Desktop/AIGC/market-data/atomic_facts/market_atomic_mainboard_full_reverse.db`
4. 已清掉根目录、`atomic_facts/`、`market_heat/` 下的 `.DS_Store`
5. `market_heat/` 根目录已只保留正式库和正式元数据。

### 4.3 ops 迁目录后的收口

已完成：

1. `ops/nas/*`
2. `ops/legacy/*`
3. `ops/windows/*`

这三组脚本的根路径解析、互调路径和高曝光文档入口都已经回写到新结构。

### 4.4 backend/scripts 第一批和第二批分层

已完成两批低风险物理分层。

第一批：

- `backend/scripts/maintenance/bench/*`
- `backend/scripts/maintenance/audit/audit_l2_order_event_codes.py`
- `backend/scripts/legacy/compat/build_local_research_snapshot.py`
- `backend/scripts/legacy/history_merge/*`

第二批：

- `backend/scripts/maintenance/l2_repair/*`
- `backend/scripts/legacy/history_repair/*`

当前结果：

1. `backend/scripts` 顶层文件数已从约 `202` 降到约 `185`
2. 第二批迁移脚本的 `ROOT_DIR / REPO_ROOT` 解析已同步修正，避免迁目录后跑错仓库根

### 4.5 研究脚本默认路径第一批收口

已完成：

1. [build_cycle_return_snapshot.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/scripts/build_cycle_return_snapshot.py)
2. [build_cycle_return_sector_report.py](/Users/dong/Desktop/AIGC/market-live-terminal/backend/scripts/build_cycle_return_sector_report.py)

这两个脚本已改为默认跟随：

- `RESEARCH_CURRENT_ROOT/selection/selection_research.db`

不再默认把 repo 内 `data/selection/selection_research.db` 当正式主入口。

配套文档已回写：

- [cycle_returns/README.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/cycle_returns/README.md)
- [research_watchlist/README.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/research_watchlist/README.md)

## 5. 当前不要误判的对象

### 5.1 现在不要碰的 repo 内库

这轮之后，repo 内真正仍要保留的是 sandbox / review 这批对象：

1. `data/sandbox_review.db`
2. `data/sandbox/review_v2/*`

原因：

1. 它们仍属于 sandbox / review 功能域，不是这轮删库要清掉的对象。
2. `data/market_data.db`、`data/user_data.db`、`data/selection/selection_research.db` 当前默认已不存在；即使将来被旧兼容链重建，也不再当正式主库理解。

### 5.2 现在不要误删的 market-data 对象

1. `atomic_facts/market_atomic_mainboard_compact_current.db`
2. `live/market_data.db`
3. `live/user_data.db`
4. `research/current/selection/selection_research.db`
5. `research/current/selection/model_feature_store.db`
6. `research/current/market_heat/*.db`

它们都是正式主库。

### 5.3 已复核但别误删的特殊对象

`/Users/dong/Desktop/AIGC/market-data/research/current/atomic_facts/shadow`

它不是空目录，当前是一个指向：

- `../market_atomic_mainboard_compact_current.db`

的符号链接壳。

现阶段只能把它记成“待定兼容对象”，不能当垃圾目录直接删。

### 5.4 不纳入本轮治理的内容

1. `docs/portfolio-ops/*`
2. 与本轮无关的用户脏改
3. 正式大库的物理迁移

## 6. 剩余工作清单

按优先级继续，不要跳顺序。

### 第一优先级：repo fallback 库边界

还没完成：

1. `data/market_data.db`
2. `data/user_data.db`
3. `data/selection/selection_research.db`

目标：

1. 明确谁是仍然必须保留的 live fallback
2. 明确谁只是兼容副本
3. 明确哪些脚本还在默认命中它们

### 第二优先级：研究脚本默认路径第二批收口

下一批重点不是正式主链脚本，而是还会默认写 repo fallback 的专题脚本。

优先继续排查：

1. `report builder`
2. `watchlist snapshot`
3. `cycle return` 相关剩余脚本
4. 其他仍硬编码 repo `data/` 的研究脚本

### 第三优先级：backend/scripts 第三批物理分层

下一批建议对象：

1. 仍有活跃研究入口引用、但不属于正式主链的 `report builder`
2. `watchlist snapshot`
3. `cycle return`

原则：

1. 先改文档和路径引用
2. 再做物理迁移
3. 不要先搬了再补文档

### 第四优先级：market-data 第二批物理治理

这批对象还没治理：

1. `market_heat/cache`
2. `market_heat/eastmoney_sector_cache`
3. `market_heat/models`
4. `market_heat/*_latest.json`
5. `*.db-wal / *.db-shm`
6. `atomic_facts/shadow`

目标不是直接删，而是先确定：

1. 谁是缓存
2. 谁是模型产物
3. 谁是运行期临时文件
4. 谁是兼容对象

### 第五优先级：反熵规则落地

必须补成明确规则：

1. 新正式库只能写到哪里
2. 新缓存只能写到哪里
3. 新研究导出只能写到哪里
4. 什么脚本可以进入正式入口白名单

## 7. 接手时的操作红线

1. 不要因为看见大文件就删。
2. 不要把 repo 内 `data/` 自动理解成当前正式主数据根。
3. 不要把 `market-data` 里的 `cache / latest.json / models` 直接当正式主库。
4. 不要把 `atomic_facts/shadow` 当成空目录删掉。
5. 不要在没做引用审计前改 repo fallback 库默认路径。
6. 不要碰 `docs/portfolio-ops/*`。

## 8. 推荐验证方式

继续治理时，至少保持这些验证动作：

```bash
python3 -m py_compile \
  backend/scripts/build_cycle_return_snapshot.py \
  backend/scripts/build_cycle_return_sector_report.py

bash -n sync_to_windows.sh ops/nas/*.sh ops/legacy/*.sh

find backend/scripts -maxdepth 1 -type f | wc -l
```

如果继续处理 `market-data`，优先先做只读盘点：

```bash
du -sh /Users/dong/Desktop/AIGC/market-data/*
find /Users/dong/Desktop/AIGC/market-data -maxdepth 2 -type d | sort
find /Users/dong/Desktop/AIGC/market-data -maxdepth 2 \( -name '*.db-wal' -o -name '*.db-shm' -o -type l \) | sort
```

## 9. 这份文档更新规则

后续任何 AI 接手这条治理线时，必须同步做三件事：

1. 改完主卡：
   - [MOD-20260606-10-repo-and-market-data-structure-governance-plan.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260606-10-repo-and-market-data-structure-governance-plan.md)
2. 改完活跃待办：
   - [07_PENDING_TODO.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/07_PENDING_TODO.md)
3. 在短日志追加一条：
   - [AI_HANDOFF_LOG.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/AI_HANDOFF_LOG.md)

只改代码、不改这三份文档，视为治理未完成。

## 10. 2026-06-06 续接复核补充

本次总控接手后的补充判断：

1. 当前不是继续大范围搬目录的时候，第一优先级是把已经发生的结构迁移形成可审计闭环。
2. `docs/changes` 顶层当前是 6 个文件，`MOD-20260606-11` 本身就是活跃接手文档，不应被误判为未归档噪音。
3. `07_PENDING_TODO` 已移除 `T-033`、`T-035` 两个 `DONE` 项，待办板重新回到只保留活跃项。
4. repo fallback 仍需治理，但当前 active residual fallback 已清零：
   - 前一轮已收口：`backend/app/services/intraday_evolution_lab.py`、`ops/start_local_research_station.sh`、`ops/run_model_feature_store_batch.sh`
   - 本轮已继续收口：`backend/scripts/run_postclose_l2_daily.py`、`ops/legacy/start_local_backend_with_atomic.sh`、`backend/app/core/config.py`
5. `/Users/dong/Desktop/AIGC/market-data/README.md` 已补为外置数据根的单点说明入口；它只做说明，不改变任何库路径。
6. `ops/bench`、`ops/windows` 已复核为纯结构迁移；`docs/archive/changes` 也已通过恢复 `MOD-20260606-02` 的 archive 原文补齐纯结构闭环。
7. repo 内三类兼容库的 canonical map 已固定：
   - `market_data_main` -> `market-data/live/market_data.db`
   - `user_data_main` -> `market-data/live/user_data.db`
   - `selection_research_main` -> `market-data/research/current/selection/selection_research.db`
8. `market-data` 的 `live/`、`research/current/`、`cache/`、`artifacts/market_heat/models` 已落到文件系统；其中 `live/` 与 `research/current/` 已完成最终物理搬迁，`2026-06-08` 又进一步删除了 root 旧入口，不再保留兼容软链。

下一步顺序：

1. 这轮用户要求的三条线已完成：云端线、report 线、删库后的文档闭环都已落地。
2. 若继续推进，优先级已经降到低风险收尾：root 层孤儿 `market_data.db-wal / market_data.db-shm` 是否在停服务窗口清理。
3. 再往后若还有治理动作，应转向 report builder 家族的物理分层与 old cloud 的彻底退役，而不是继续修默认数据根。
