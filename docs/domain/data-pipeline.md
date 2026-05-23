# Windows 数据主站 / L2 / 原子层

## 覆盖 CAP
- `CAP-WIN-PIPELINE`
- `CAP-L2-HISTORY-FOUNDATION`

## 当前正式结论
1. Windows 是原始包与正式跑数主站。
2. Mac 读取同步后的正式库，不直接跨网读 Windows sqlite。
3. 原子层已进入主线，但旧表依赖尚未完全剥离。
4. 新框架日跑入口已独立为 `ops/run_daily_new_framework.sh`；旧 `ops/run_postclose_l2.sh` 只保留为历史 L2/cloud 同步参考，不再作为新 compact atomic + selection + model_feature_store 的模板。
5. 新框架日跑在 Windows 侧会先刷新 `model_market_index_daily.db`，再构建 `model_feature_store.db`；指数刷新失败只降级告警，不阻断主链路。

## 当前仍需继续做的
- 全链路 `30m` 目标验证
- 存量表依赖剥离
- 自动编排与失败修复体系继续收口
- 旧 `market_data.db` / cloud merge 链路是否还要长期保留，需另行决策；不要混入新框架日跑。
