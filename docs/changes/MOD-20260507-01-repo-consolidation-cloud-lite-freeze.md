# MOD-20260507-01 仓库收口与 Cloud Lite 发布前冻结

## 1. 结论
- 本轮目标不是发版，而是把本地 `v5.1.0`、GitHub `v5.0.20`、历史未提交研究代码和文档先合到一个可管理分支。
- 当前唯一主开发目录仍是 `/Users/dong/Desktop/AIGC/market-live-terminal`。
- 当前唯一持续更新的研究目录是 `docs/selection/long_term_trends/`；以后清理、stash、worktree 收口时必须优先保护。
- Cloud 后续只按 Cloud Lite 处理：盯盘 + 复盘优先；选股、热点、长期研究默认不作为云端必须能力。

## 2. 本轮已收口范围
- 合入 `origin/main` 的 `v5.0.10 ~ v5.0.20` 选股研究上下文、图表告警收口等改动。
- 保留本地 `v5.1.0` 市场热点研究入口和低位 L2 样本研究页代码。
- 保留长期趋势研究档案与存储主线第一批研究文档。
- 补充轻量配置数据：市场热度 JSON 规则、长期趋势线索 inbox 和 watchlist。
- `.obsidian/` 与 NotebookLM 临时测试文件只作为本机工具痕迹，不进仓库。

## 3. 云端边界
- 云端目标：`/` 盯盘、`/review` 复盘、必要的 `/api/realtime/*`、`/api/review/*`、watchlist/config/ingest。
- 云端非目标：`/selection-research`、`/market-heat`、长期趋势研究、全量 atomic/selection/research DB。
- 后续发 Cloud 前，需要做运行 profile 或环境开关，让同一套代码在 Cloud 隐藏/禁用非目标模块，而不是维护两套代码。

## 4. 后续处理顺序
1. 当前分支通过 baseline 后合回 `main`。
2. 清理或归档多余 worktree，只保留主目录作为默认开发入口。
3. 再做 Cloud Lite feature gate。
4. 最后才做云端数据白名单重建与旧数据删除。

## 5. 风险
- 热点低位 L2 样本仍是研究工具，不是生产策略。
- 长期趋势研究依赖人工更新和外部事实验证，不接入自动交易。
- 云端旧版本和数据盘清理必须等 Cloud Lite 代码边界确认后再执行。
