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

## 2.1 当前正式日常指令
```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/run_postclose_l2.sh
```

## 2.2 当前同步铁律
- Windows -> Mac **禁止**走 SSH/scp 直拉。
- 只允许两条正式路径：
  1. 局域网 HTTP relay
  2. Cloud relay 中转
- 脚本当前已内置：
  - 局域网优先
  - 局域网失败自动回退云中转
  - 若某交易日已经完整成功，后续再次触发时优先复用成功结果，不重复全链路重跑

## 3. 当前目标
- 日跑稳定
- 失败可追溯
- repair queue 可导出
- 结果可被 Mac 本地研究站消费

## 3.1 已验证样本
- `2026-04-24` 已完成收口验证：
  - Mac `history_daily_l2 = 7644`
  - Mac `history_5m_l2 = 346154`
  - Mac `atomic_trade_daily = 3184`
  - Mac `selection_feature_daily = 3184`
  - Cloud 同日 verify 已通过

## 4. 当前待完成问题
- 是否继续推进完全无人值守
- 全链路 `prepare + run` 是否稳定压到 `30m` 目标线
- 存量旧表依赖是否可以继续剥离

## 5. 相关变更卡
- `docs/changes/MOD-20260315-02-l2-march-backfill-review-and-postclose-runbook.md`
- `docs/changes/MOD-20260411-14-market-data-governance-current-state.md`
- `docs/changes/MOD-20260417-01-local-research-current-state.md`
- `docs/changes/MOD-20260425-04-postclose-l2-command-solidification.md`
