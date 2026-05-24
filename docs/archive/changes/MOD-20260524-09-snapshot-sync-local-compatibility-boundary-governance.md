# MOD-20260524-09 snapshot / sync / local compatibility 边界治理

## 1. 基本信息
- 标题：`snapshot / sync / local compatibility` 边界治理
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-09-snapshot-sync-local-compatibility-boundary-governance`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-SELECTION-RESEARCH`

## 2. 这次治理回答的问题

这批不是在判断“本地快照链还有没有价值”，而是在回答：

> `snapshot / sync / local compatibility` 这条链，现在到底是不是正式本地研究主入口？

结论不是。

当前正式本地研究入口仍然是：

```text
bootstrap_mac_full_processed_sync
-> start_local_research_station
-> start_local_research_frontend
```

而这一批对象：

- `ops/sync_windows_research_snapshot.sh`
- `backend/scripts/build_local_research_snapshot.py`
- `ops/start_local_backend_with_atomic.sh`

都只属于兼容、验证、排查或人工应急链。

## 3. 本轮分类结论

| 文件 | 当前角色 | 结论 |
|---|---|---|
| `ops/start_local_backend_with_atomic.sh` | 本地 atomic 兼容直启 | 可保留，但只按兼容排查入口理解 |
| `ops/sync_windows_research_snapshot.sh` | Windows -> Mac 旧快照同步 | 保留，但不是正式同步主方案 |
| `backend/scripts/build_local_research_snapshot.py` | 旧本地研究快照构建器 | 保留，但不是正式运行主链 |

## 4. 本轮实际动作

### 4.1 兼容脚本默认 atomic 口径收口

已更新：

- `backend/scripts/build_local_research_snapshot.py`

之前它默认把旧 `market_atomic_mainboard_full_reverse.db` 当成 snapshot builder 的 atomic 输入。

现在统一改成：

1. 优先显式 `ATOMIC_MAINBOARD_DB_PATH / ATOMIC_DB_PATH`
2. 再走全局 `candidate_atomic_db_paths()`
3. 再回到本机 `compact_current`
4. 最后才保留 `full_reverse` 作为兼容回退

这意味着：

- 旧快照链即便继续使用，也会先跟随当前正式 atomic 口径
- 不再把 `full_reverse` 误当成默认正式底座

### 4.2 正式入口文档边界补齐

已更新：

- `docs/ops/mac-local-research.md`
- `docs/ops/atomic-script-families-boundary.md`
- `docs/AI_QUICK_START.md`

现在这些入口文档都明确写清了：

1. 正式本地研究站应该怎么启动
2. 哪三项只属于兼容/验证链
3. 后续 AI 不应该把旧快照链误读成默认入口

## 5. 当前结论

这批治理的收益，不是“删掉快照链”，而是：

1. 把正式主入口和兼容排查入口彻底分开
2. 让仍然保留的旧快照脚本先跟随当前 `compact` 口径
3. 避免后续 AI 在本地研究站任务里又绕回 `snapshot / full_reverse`

## 6. 后续建议

这批之后，`atomic / selection / market_heat / watchlist / doubler / snapshot` 六类高混淆入口已经都有过第一轮边界治理。

后续更合理的方向，不再是继续补入口卡，而是：

1. 回到总治理文档更新当前完成度
2. 重新评估剩余高收益治理项
3. 再决定是否进入下一批代码或目录级治理
