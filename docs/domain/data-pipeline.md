# Windows 数据主站 / L2 / 原子层

## 覆盖 CAP
- `CAP-WIN-PIPELINE`
- `CAP-L2-HISTORY-FOUNDATION`

## 当前正式结论
1. Windows 是原始包与正式跑数主站。
2. Mac 读取同步后的正式库，不直接跨网读 Windows sqlite。
3. 原子层已进入主线，但旧表依赖尚未完全剥离。
4. 新框架日跑入口已独立为 `ops/run_daily_new_framework.sh --json --sync-nas`；正式 wrapper 会自动补 NAS 同步口径，`--skip-nas` 只允许显式排障；旧 `ops/legacy/run_postclose_l2.sh` 只保留为历史 L2/cloud 同步参考，不再作为新 compact atomic + selection + model_feature_store 的模板。
5. 新框架日跑默认自动检测日期：扫描 Windows 日包，对比 Mac 本地完整性，只补最新完整日之后的缺失日期。
6. 新框架日跑在 Windows 侧会把市场环境指数和当天热点结果纳入主链：指数刷新与 atomic 并行，热点计算在 atomic 完成后执行，二者都必须在模型特征构建前到位。
7. Mac 侧完成标准包含 atomic、selection、model_feature_store 落表，以及选股工作台活跃模型/策略的 success 运行记录；当前活跃来源为 `spark_opportunity_selector`、`stable_capital_callback`、`trend_continuation_callback`、`probe_day0_watch`、`probe_d3_confirmed`。
8. 当启用 `--sync-nas` 时，Mac 本地校验通过后，会同步 NAS 生产 `live` 增量、市场水位目录，并后台启动运行库快照；整套 `research/current` 大体量发布不再绑在每日默认收口里。

## 当前仍需继续做的
- 全链路 `30m` 目标验证
- 存量表依赖剥离
- 自动编排与失败修复体系继续收口
- 旧 `market_data.db` / cloud merge 链路是否还要长期保留，需另行决策；不要混入新框架日跑。
