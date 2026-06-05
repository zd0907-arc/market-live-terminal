# 模型训练资料总入口

更新时间：2026-06-03

## 结论

以后和“模型训练 / 选股研究 / 持仓研究 / 热点过滤 / 新方向探索”相关的资料，先从这里进入。

这份入口不替代项目总真相页，也不替代具体策略文档。它解决的是另一件事：

- 以后想做一个新模型方向时，先知道该看哪些资料；
- 先知道哪些文档是当前真相，哪些只是历史实验；
- 先知道新材料应该往哪一层放，不再把训练计划、结果、结论、产品接入说明混在一起。

## worktree 角色

这套治理框架不要求长期保留很多 worktree。

正确理解是：

- 文档框架本身是长期资产
- `worktree` 只是临时研究容器

规则见：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/worktree-lifecycle.md`

原则固定为：

1. 需要隔离时才开
2. 一个 worktree 只承接一个主题
3. 研究结论收口后马上删除

## 5 层结构

### 第 1 层：当前真相层

只放当前仍有效、以后每次开新方向都应该先读的内容。

当前主入口：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/daily_candidate_source_contract.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/model_development_sop.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/current-research-operating-summary.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/README.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/current-material-map.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/worktree-lifecycle.md`

### 第 2 层：研究方向层

解决“现在都研究过哪些方向、每个方向结论到哪一步”。

入口文档：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/research-directions-index.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/direction-status-card-template.md`

### 第 3 层：训练与验证层

解决“模型怎么训练、怎么防止未来函数、怎么评估”的共性问题。

核心文档：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/evaluation-metrics-dictionary.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/model_development_sop.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/strategy-rework/evolution-lab/README.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/model-research/experiment-artifact-governance.md`

### 第 4 层：实验记录层

只放具体某一轮实验、某一批训练、某一组结果，不承担总入口职责。

现有典型位置：

- `docs/selection/*_2026-*`
- `docs/strategy-rework/strategies/*/experiments/*`
- `docs/strategy-rework/experiments/*`

### 第 5 层：产品接入层

解决“研究结果怎么接到系统里”。

当前主入口：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/daily_candidate_source_contract.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/contracts/review-selection.md`
- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/changes/MOD-20260525-01-spark-exit-watchlist-integration.md`

## 以后默认阅读顺序

如果你想开一个新研究方向，默认顺序是：

1. `docs/model-research/README.md`
2. `docs/model-research/research-directions-index.md`
3. `docs/model-research/current-material-map.md`
4. `docs/model-research/worktree-lifecycle.md`
5. `docs/03_DATA_CONTRACTS.md`
6. `docs/selection/model_development_sop.md`
7. `docs/model-research/evaluation-metrics-dictionary.md`
8. 再进入具体方向材料

## 新材料以后怎么放

### 放在第 1 层

只有满足下面条件，才可以进总入口层：

- 未来三次以上新研究还会反复用到；
- 不依赖某一轮具体实验结果；
- 它描述的是共识、规则、总口径，而不是过程。

### 放在第 2 层

如果它是在讲某个研究方向本身，比如：

- 星火纯选股
- 持仓卖点
- 热点预筛
- 试盘识别
- 市场环境过滤

那它应该挂到研究方向层。

### 放在第 3 层

如果它描述的是共通训练方法，比如：

- 时间切分
- 评估指标
- 可买性约束
- Windows 训练执行方式

那它应该放到训练与验证层。

### 放在第 4 层

如果它只属于某一轮具体实验，比如：

- 某次 smoke
- 某次 full run
- 某次参数扫描
- 某次月度回测

那它应该只进实验记录层。

### 放在第 5 层

如果它描述的是：

- 如何接每日候选
- 如何进页面
- 如何进统一候选池
- 如何和现有工作台兼容

那它属于产品接入层。

## 还缺的核心文档

这次先把总入口搭起来，不一次做完所有治理。

后续建议继续补：

1. Windows 训练执行总说明
2. 点时安全与防未来函数审计说明
3. 模型数据集切分规范
4. 研究结果接入工作台 checklist
5. 方向状态卡逐条补齐
