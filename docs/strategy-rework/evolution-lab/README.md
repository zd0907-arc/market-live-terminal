# 5分钟伪日内自进化实验室

第一版只读 Mac 已生成的 processed atomic DB，不默认解压 Windows raw 包，也不接实盘自动交易。

## 数据口径

- 主窗口：`2026-03-02 ~ 2026-05-12`，使用 `atomic_trade_5m + atomic_order_5m + atomic_book_state_5m + atomic_limit_state_daily`；5分钟触板/封板字段由 5m 行情和日级涨跌停价按需派生。
- 弱窗口：`2025-01-02 ~ 2026-03-01`，只适合成交/L2资金流版本，不能和 full order/book 结果混排。
- 默认股票池：10cm 主板票，并按上一交易日成交额 TopN 预选，避免用当日收盘后的成交额裁剪样本。
- raw 解压只用于补新日包、重建特征、逐笔级研究、数据审计；常规策略搜索不依赖 raw。

## 回放规则

- 每个交易日按 5分钟 bucket 推进。
- 当前 bucket 只能看到当前及以前的 5m 聚合数据。
- 入场信号在当前 bucket close 后生成，实际买入用下一 bucket open。
- 强制执行 A 股 T+1：同日买入不可同日卖出，没有研究绕过开关。
- 已计入买卖滑点和手续费，涨跌停状态会阻断买入/卖出。

## 强化学习环境

- 新主线是 `RLTradingEnv`：环境只负责真实账户、市场回放和交易规则，不内置策略 DSL。
- 一局 episode 推荐使用一个月，从 100 万初始资金开始。
- agent 每 5分钟接收 point-in-time observation，然后输出账户动作。
- 动作空间：`hold`、`buy(symbol, cash_amount|cash_fraction)`、`sell(symbol, fraction)`。
- 支持多股持仓、分仓、加仓、减仓、清仓、留现金。
- episode 结束不强制清仓，最终资产按现金 + 持仓市值计价。
- reward 以最终资产为第一权重，回撤、换手、无效动作作为惩罚项。

## 第一版 learner

- `train-ppo-policy` 是当前主训练入口，使用 PyTorch + Stable-Baselines3 PPO。
- PPO 动作是 Top-N 股票的连续目标仓位，环境负责转换成买入、加仓、减仓、清仓。
- 2026-04 全月 smoke：`ppo_train_202604_t20k.json`，20k timesteps，最终资产 `1,115,044.87`，收益 `11.50%`，最大回撤 `-6.41%`。
- 4月模型外推到 2026-05-06 ~ 2026-05-12：`ppo_eval_20260501_20260512_from_202604.json`，最终资产 `998,957.23`，收益 `-0.10%`，最大回撤 `-2.99%`。
- `train-rl-policy` 是最小可用 policy-search learner。
- 它训练一组线性动作打分权重，不是手写交易策略。
- 每个候选 policy 都完整跑一个 episode，从 100 万开始连续交易。
- 每代按 episode 结果选精英，再更新下一代权重分布。
- 这是强化学习训练闭环的第一版，不是最终深度 RL。

## 旧版参数进化器

- `run-arena` 仍保留作 baseline，但不是最终主线。
- 它使用策略参数 DSL + 随机蒙特卡洛 + 遗传变异。
- 排行榜按 validation score 排名，test 只用于最终报告。

## 回测切分方案

- 弱数据预训练：`2025-01-02 ~ 2026-03-01`，只用 trade/limit/L2 成交流特征，不能和 full order/book 结果混排。
- full 口径训练/验证：`2026-03-02 ~ 2026-04-30`，按月或滚动 20 交易日 walk-forward。
- 最后外推测试：`2026-05-06 ~ 2026-05-12`，只评估 4 月前训练出的模型，不再训练。
- 任何报告都必须同时列出：训练区间、评估区间、交易日数、T+1 违规数、bucket 执行违规数。

## 常用命令

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py catalog-data \
  --out data/selection/evolution_lab/catalog.json
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py eval-ppo-policy \
  --model-path data/selection/evolution_lab/ppo_train_202604_t20k.zip \
  --start-date 2026-05-01 \
  --end-date 2026-05-12 \
  --budget 1000000 \
  --max-symbols-per-day 40 \
  --max-observation-symbols 20 \
  --out data/selection/evolution_lab/ppo_eval_20260501_20260512_from_202604.json
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py train-ppo-policy \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --budget 1000000 \
  --total-timesteps 20000 \
  --n-steps 512 \
  --batch-size 128 \
  --n-epochs 6 \
  --max-symbols-per-day 40 \
  --max-observation-symbols 20 \
  --target-return-pct 5 \
  --out data/selection/evolution_lab/ppo_train_202604_t20k.json \
  --model-out data/selection/evolution_lab/ppo_train_202604_t20k.zip
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py train-rl-policy \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --budget 1000000 \
  --population-size 48 \
  --generations 4 \
  --max-symbols-per-day 60 \
  --max-observation-symbols 60 \
  --out data/selection/evolution_lab/rl_policy_train_202604.json
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py rl-random-smoke \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --budget 1000000 \
  --max-symbols-per-day 60 \
  --out data/selection/evolution_lab/rl_random_smoke_202604.json
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py run-arena \
  --start-date 2026-03-02 \
  --end-date 2026-05-12 \
  --population-size 200 \
  --generations 2 \
  --elite-size 12 \
  --max-symbols-per-day 180 \
  --train-days 18 \
  --validation-days 8 \
  --test-days 8 \
  --step-days 8 \
  --out data/selection/evolution_lab/full_l2_main_20260302_20260512
```

```bash
/usr/bin/python3 backend/scripts/run_intraday_evolution_lab.py run-arena \
  --start-date 2025-01-02 \
  --end-date 2026-03-01 \
  --data-tier weak_trade_l2 \
  --population-size 200 \
  --generations 2 \
  --elite-size 12 \
  --max-symbols-per-day 180 \
  --out data/selection/evolution_lab/weak_trade_l2_20250102_20260301
```

输出目录包含：

- `arena_summary.json`：完整配置、fold、leaderboard、最优策略和测试交易。
- `leaderboard.csv`：策略排行榜。
- `best_test_trades.csv`：最优策略在 test 区间的逐笔买卖。
- `README.md`：本次实验摘要。
