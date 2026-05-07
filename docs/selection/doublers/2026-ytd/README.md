# 2026 YTD 翻倍股研究母池

## 持久化清单

- 全量母池（非 ST/退，78 只）：`/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/doubler_analysis/2026_ytd_doublers_master_manifest.csv`
- Top20 队列：`/Users/dong/Desktop/AIGC/market-live-terminal/data/selection/doubler_analysis/2026_ytd_doublers_top20_manifest.csv`
- Top20 报告目录：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/doublers/2026-ytd/top20/`

## 当前状态

- 已完成 Top20 案例报告：20 只
- 已补齐字段：阶段拆解、本地事件、外部消息核验、案例库标签、可复用条件、风险/出场触发
- 生成脚本：`/Users/dong/Desktop/AIGC/market-live-terminal/backend/scripts/build_ytd_doubler_analysis.py`
- 使用体系：`/Users/dong/Desktop/AIGC/market-live-terminal/docs/selection/doublers/CASE_LIBRARY_USAGE.md`

## 用法

```bash
python backend/scripts/build_ytd_doubler_analysis.py --limit 20 --report-symbols sh603629
```

> 默认不会覆盖已经手工润色过的报告；如需覆盖，额外加 `--overwrite-reports`。

## 案例库使用方式

后续评估新票时，先用`细分方向`、`点火链条`、`消息先后`、`案例库标签`匹配历史样本，再用`风险/出场`字段判断是否还能继续持有。
