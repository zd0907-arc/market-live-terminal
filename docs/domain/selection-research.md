# 选股研究与回测闭环

## 覆盖 CAP
- `CAP-SELECTION-RESEARCH`

## 当前正式结论
1. 选股研究结果写入独立库 `data/selection/selection_research.db`。
2. 候选、画像、回测接口已经存在，主链路可用。
3. 当前最大问题不是“有没有功能”，而是本地正式底座还不够完整。

## 当前仍需继续做的
- 本地 L2 / stock_universe_meta 继续补齐
- 候选票与事件层进一步融合
- 回测与研究结果继续打磨到可稳定日用
