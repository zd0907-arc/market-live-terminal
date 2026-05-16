# S06 机会发现模型

## 当前结论

这一版核心是选股，不是完整操盘系统。

当前已经证明它有一定效果：

```text
Top1 在未来 22 个交易日内达到 15% 冲高的比例为 65.38%。
严格账户回测最佳组合收益 +87.58%，但只有 13 笔成交。
```

当前离场方案只是评估壳，不是成熟卖点系统。

短周期第一轮已跑完：H5 方案表现最好，`8%止盈 / 无硬止损 / 5日到期` 的严格账户回测收益为 `+40.60%`；2/3 日超短线整体不成立。

H5 + 22日融合第一轮已跑完：不建议用 H5 重排 22日模型；更适合把 H5 当作短线启动确认标签。当前主推荐仍以 22日 Top1 为核心。

## 文档

| 文档 | 说明 |
|---|---|
| [当前版记录](./2026-05-15-current-version-record.md) | 记录 22 日机会发现模型的数据、标签、特征、回测口径、结果和限制 |
| [下一轮短周期计划](./2026-05-15-short-horizon-next-plan.md) | 拆分 2/3/5/7/10 日短周期模型训练和月度账户评估方案 |
| [H5+22日融合实验](./2026-05-15-fusion-h5-22-result.md) | 记录 H5 确认、候选池重排、账户回测和当前推荐用法 |

## 当前入口

```bash
/usr/bin/python3 backend/scripts/research_opportunity_discovery_model.py train
/usr/bin/python3 backend/scripts/research_opportunity_short_horizon.py train --out data/selection/opportunity_discovery/short_horizon_v0_1
/usr/bin/python3 backend/scripts/research_opportunity_fusion_h5_22.py run --out data/selection/opportunity_discovery/fusion_h5_22_v0_1
```
