# 盘后 L2 / 原子层日跑总控

## 1. 当前正式语义
当前正式日跑主路径是：
1. Windows 产出原始包与跑数结果
2. 控制端执行盘后总控
3. 必要结果同步到 Mac / Cloud

## 2. 当前正式入口
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
./ops/run_postclose_l2.sh
./ops/check_postclose_l2_status.sh
```

## 3. 当前目标
- 日跑稳定
- 失败可追溯
- repair queue 可导出
- 结果可被 Mac 本地研究站消费

## 4. 当前待完成问题
- 是否继续推进完全无人值守
- 全链路 `prepare + run` 是否稳定压到 `30m` 目标线
- 存量旧表依赖是否可以继续剥离

## 5. 相关变更卡
- `docs/changes/MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook.md`
- `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`
- `docs/changes/MOD-20260417-01-local-research-current-state.md`
