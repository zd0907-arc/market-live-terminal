# MOD-20260524-03 跨端正式数据产物清单（业务视角）

## 1. 基本信息
- 标题：跨端正式数据产物清单（业务视角）
- 状态：DRAFT
- 负责人：Codex
- 关联 Task ID：`MOD-20260524-03-canonical-data-artifacts-manifest`
- 关联 CAP：`CAP-WIN-PIPELINE`, `CAP-L2-HISTORY-FOUNDATION`, `CAP-SELECTION-RESEARCH`, `CAP-MARKET-HEAT`, `CAP-HISTORY-30M`
- 关联 STG：`N/A`

## 2. 这份文档现在回答什么

这份文档不是给工程师背文件名用的，而是回答 4 个业务问题：

1. 你现在系统里的每类正式数据，分别在支撑什么页面或功能。
2. 哪些库虽然名字像正式库，其实只是兼容件、快照、缓存或历史残留。
3. Mac、Windows、Cloud 三端现在分别谁在生产、谁在消费。
4. 后面做治理时，哪些对象应该保留，哪些只是要改名、归档或退役。

当前阶段只做识别和命名收口依据，不做删除。

## 3. 使用方式

以后判断一个数据库或大文件，先不要看技术名，先看它落在哪个业务位置：

1. 它支撑哪个页面或功能。
2. 如果它坏了，你在页面上会看到什么异常。
3. 它是正式真相源，还是快照/缓存/兼容件。
4. 再回头看它的技术对象名和物理路径。

凡是后续要执行的治理动作，都必须同时更新：

- [docs/01_SYSTEM_ARCHITECTURE.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/01_SYSTEM_ARCHITECTURE.md)
- [docs/03_DATA_CONTRACTS.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/03_DATA_CONTRACTS.md)
- [docs/contracts/storage.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/contracts/storage.md)
- [docs/04_OPS_AND_DEV.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/04_OPS_AND_DEV.md)
- [docs/08_DOCS_GOVERNANCE.md](/Users/dong/Desktop/AIGC/market-live-terminal/docs/08_DOCS_GOVERNANCE.md)

## 4. 正式数据总表（先按业务看）

| 业务名称 | 对应页面/功能 | 技术对象 | 当前正式位置 | 你能感知到什么 | 当前建议 |
|---|---|---|---|---|---|
| 轻量盯盘消费库 | 首页实时盯盘、云端应急查看、部分基础历史接口 | `market_data_main` | Windows `data/market_data.db`；Mac `market-data/market_data.db`；Cloud `data/market_data.db` | 如果它异常，首页实时数据、云端轻量页面、部分基础图表会缺数据或延迟 | 保留；明确它现在更偏“轻量消费库/旧主链兼容库”，不要再把它讲成唯一总库 |
| 每日选股研究库 | 选股研究页、每日候选、策略结果查看、部分研究脚本 | `selection_research_main` | Windows 实际主写：`data/selection/selection_research_windows.db`；Mac 主读：`market-data/selection/selection_research.db` | 如果它异常，选股页会出现候选缺失、策略结果不全、日期查不到 | 保留；最优先做命名收口，明确“Windows 主写名”和“Mac 主读名” |
| 盘后明细底座 | 复盘页、选股详情、热点研究里依赖的明细底层数据 | `atomic_compact_main` | Windows 实际主写：`data/atomic_facts/market_atomic_mainboard_compact_smoke_20260401_20260515.db`；Mac 主读：`market-data/atomic_facts/market_atomic_mainboard_compact_current.db` | 页面上你不会直接看到它的名字，但如果它错了，会表现为复盘明细不完整、个股细节缺失、热点研究数据不对 | 保留；最优先建立稳定正式别名，不要再让 `smoke` 文件名承担正式角色 |
| 模型训练特征库 | 模型训练、特征校验、训练前后的跑数验证 | `model_feature_store_main` | Windows 实际主写：`data/selection/model_feature_store_smoke_20260401_20260515.db`；Mac 主读：`market-data/selection/model_feature_store.db` | 前台页面通常感知不到；训练或验证时会表现为缺特征、日期缺口、样本不全 | 保留；建立 Windows 稳定正式名，避免继续用 `smoke` 名承载正式语义 |
| 模型指数前置库 | 特征构建前置依赖、指数相关训练输入 | `model_market_index_daily_main` | Windows `data/selection/model_market_index_daily.db`；Mac `market-data/selection/model_market_index_daily.db` | 通常页面无直接感知；特征构建会因为它缺失而失败 | 保留；它已经比较清晰，只要在文档里明确“正式前置库”身份 |
| 热点页面正式日表（兼容主表） | 热点页主列表、热点 API、部分热点研究 | `market_heat_fine_daily_v1` | Mac `market-data/market_heat/fine_theme_heat_daily.db` | 如果它异常，热点页会直接缺主题强弱结果、热点榜会不稳定 | 保留；明确它是“当前页面主消费库”，不是未来训练唯一真相源 |
| 热点训练/回测长表 | 热点训练、回测、未来更细颗粒分析 | `market_heat_fine_daily_v2` | Mac `market-data/market_heat/fine_theme_heat_daily_v2.db` | 页面通常感知不到；训练/回测会因为它缺失而无法完整运行 | 保留；明确它是训练主输入，不和热点页面主表混讲 |
| 热点预测结果库 | 热点预测、预测效果验证、未来预测展示 | `market_heat_forecast_main` | Mac `market-data/market_heat/fine_theme_heat_forecast.db` | 当前页面直接感知可能有限；预测功能会受影响 | 保留；定位为正式预测结果库 |
| 热点主题成分库 | 热点主题明细、主题成分股关系、热点解释 | `market_heat_member_daily_main` | Mac `market-data/market_heat/fine_theme_member_daily.db` | 如果它异常，热点页里的主题成分解释会不完整 | 保留；明确它是热点主表的配套正式库 |
| 股票-板块映射库 | 热点映射、主题归属、研究脚本的板块映射 | `market_heat_board_map_main` | Mac `market-data/market_heat/stock_sector_map.db` | 如果它异常，主题归属、板块映射和解释会不准 | 保留；正式映射库，不要和缓存混为一谈 |
| 可交易主题映射库 | 热点可交易主题口径、主题清洗后的正式映射 | `market_heat_tradable_theme_map_main` | Mac `market-data/market_heat/tradable_theme_map.db` | 如果它异常，热点主题结果会出现不可交易主题混入或分类口径漂移 | 保留；正式映射库 |
| 热点低位样本专题库 | 热点低位样本专题页/API、低位样本研究 | `market_heat_low_position_samples_main` | Mac `market-data/market_heat/hot_theme_low_position_l2_samples.db` | 如果它异常，热点低位样本功能会缺结果或解释不全 | 保留；专题正式库 |
| 本地用户配置库 | 自选、页面配置、用户态设置 | `user_data_main` | Windows `data/user_data.db`；Mac `market-data/user_data.db` | 如果它异常，你会感知到本地配置丢失、页面状态不一致 | 保留；正式用户态库 |

## 5. 容易误判，但不是正式主对象

| 技术对象 | 容易被误会成什么 | 实际角色 | 删错/改错会造成什么 | 当前动作 |
|---|---|---|---|---|
| Windows `data/selection/selection_research.db`（小库） | 每日选股正式库 | 占位/兼容名字，不是实际主写库 | 可能打断兼容脚本，但不会替代真正大库 | 先保留；后续只做命名收口，不直接删 |
| `market_atomic_mainboard_full_reverse.db`（Windows / Mac） | atomic 正式主库 | 历史兼容残留/旧 fallback 入口 | 部分历史脚本或兼容入口可能断掉 | 先保留；退役前先收脚本和文档口径 |
| Windows `market_atomic_mainboard_compact_smoke_*` | 试验库 | 现在实际上承担正式 atomic 主库角色 | 删错会直接影响复盘、选股细节、热点研究底层数据 | 先保留；后续重点不是删，是给它正式别名 |
| Windows `model_feature_store_smoke_*` | 试验库 | 现在实际上承担正式特征库角色 | 删错会直接影响训练和特征验证 | 先保留；同样先做正式别名 |
| `data/local_research/research_snapshot.db` | 正式研究主库 | 本地研究站快照 | 删错会影响本地快照研究站或离线验证 | 保留当前 1 份 + 最近回退点 |
| `data/local_research/selection/selection_research.db` | 正式选股主库 | 快照副本 | 删错会影响本地快照模式下的选股查看 | 跟随快照策略，不单独处理 |
| `market_heat/cache/fine_heat_snapshots_*.json` | 热点正式真相源 | 热点页面/脚本缓存 | 删错会导致热点页回到重算路径，或少掉当前缓存窗口 | 只控量，不清空 |
| repo 内 `data/market_heat/market_heat.db` | 当前热点正式主库 | 历史/本地残留库 | 最危险的是误导，不一定立刻影响现网 | 暂不删；后续归为高风险误导对象 |
| `*_validation.db` / `*_validation.json` | 正式生产库 | 验证产物 | 删错会影响复核，但不该影响正式功能 | 阶段收口后归档 |
| `*_smoke.db`（除当前实际正式大库外） | 正式生产库 | 烟测/试验库 | 删错影响排障，不应影响正式页面 | 阶段收口后归档或清理 |

## 6. 按页面倒推底层依赖

| 页面/功能 | 主要正式依赖 | 你会怎么感知到异常 | 当前备注 |
|---|---|---|---|
| 首页实时盯盘 | `market_data_main`、`user_data_main` | 实时数据卡住、基础图表缺失、自选状态不对 | 这是最偏轻量消费的一层 |
| 历史复盘页 | `market_data_main`、`atomic_compact_main` | 日期能打开，但细节不全、个股明细缺数据 | 复盘对 atomic 明细底座依赖已经很强 |
| 每日选股/策略研究 | `selection_research_main`、`atomic_compact_main`、部分热点库 | 候选池缺失、策略解释不全、详情页不完整 | 这是当前最需要命名收口的一条链 |
| 市场热点页 | `market_heat_fine_daily_v1`、`market_heat_member_daily_main`、`market_heat_board_map_main`、`market_heat_tradable_theme_map_main` | 热点主题榜不稳、主题解释缺项、加载慢或窗口不对 | 页面主消费仍是 v1 体系，训练主输入是 v2 |
| 模型训练 / 跑数验证 | `model_feature_store_main`、`model_market_index_daily_main`、`atomic_compact_main`、`market_heat_fine_daily_v2` | 训练缺字段、验证失败、日期不连续 | 这层不是前台页面，但属于当前核心业务能力 |
| 云端轻量查看 | Cloud `market_data.db` | 云端只剩壳或轻量数据不更新 | Cloud 目前不承担完整研究库角色 |

## 7. 现在真正要治理的，不是删库，而是 3 个命名冲突

### 7.1 每日选股正式库

- 业务名称：每日选股研究库
- 当前冲突：Windows 真正大库叫 `selection_research_windows.db`，Mac 主读叫 `selection_research.db`
- 治理目标：明确“Windows 主写正式名”和“Mac 主读正式名”的映射，不再靠脚本猜

### 7.2 盘后明细底座

- 业务名称：盘后明细底座
- 当前冲突：Windows 真正大库仍挂在 `compact_smoke_*` 文件名上，Mac 已经是 `compact_current.db`
- 治理目标：给 Windows 建稳定正式别名，停止让 `smoke` 这个词承载正式语义

### 7.3 模型训练特征库

- 业务名称：模型训练特征库
- 当前冲突：Windows 仍用 `model_feature_store_smoke_*`，Mac 已是稳定正式名
- 治理目标：同样建立稳定正式别名，和训练文档保持一致

## 8. 对后续治理的执行要求

1. 当前不删任何正式库，也不删当前仍在承担正式角色的大库。
2. 先完成“业务名称 -> 技术对象 -> 物理路径”的统一映射，再动清理。
3. 任何清理或重命名都要先更新本文件。
4. 任何正式角色变化，都必须同步回写核心文档：
   - 架构角色变了，改 `01_SYSTEM_ARCHITECTURE`
   - 正式库/表/路径口径变了，改 `03_DATA_CONTRACTS` 和 `docs/contracts/storage.md`
   - 运行入口、保留策略、同步方式变了，改 `04_OPS_AND_DEV`
   - 治理规则本身变了，改 `08_DOCS_GOVERNANCE`

## 9. 当前最重要的结论

1. 现在最危险的不是 `archive`，而是“正式角色已经变了，但名字还停留在历史叫法”。
2. 真正需要优先收口的是 `selection_research`、`atomic compact`、`model_feature_store` 三条主链。
3. 热点页当前页面主消费和训练主输入已经分层，文档必须明确，不要再混讲。
4. 在这张表稳定之前，不应该直接删库。
