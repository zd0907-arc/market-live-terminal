# Windows 数据主站 / L2 / 原子层

## 覆盖 CAP
- `CAP-WIN-PIPELINE`
- `CAP-L2-HISTORY-FOUNDATION`

## 当前正式结论
1. Windows 是原始包与正式跑数主站。
2. Mac 读取同步后的正式库，不直接跨网读 Windows sqlite。
3. 原子层已进入主线，但旧表依赖尚未完全剥离。
4. 盘后总控已经成型，当前重点是稳定性和继续收口。

## 当前仍需继续做的
- 全链路 `30m` 目标验证
- 存量表依赖剥离
- 自动编排与失败修复体系继续收口
