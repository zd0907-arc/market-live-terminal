# 模型特征库实施记录

日期：2026-05-17  
分支：`codex/model-training-data-audit`

## 当前结论

P0 样本链路已跑通。

已新增：

```text
backend/scripts/sql/model_feature_store_schema.sql
backend/scripts/build_model_feature_store.py
backend/scripts/validate_model_feature_store.py
```

正式样本输出：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_20260513_20260515.json
```

## 本轮样本结果

命令：

```bash
python3 backend/scripts/build_model_feature_store.py \
  --start-date 2026-05-13 \
  --end-date 2026-05-15 \
  --reset-target
```

结果：

| 表 | 行数 |
|---|---:|
| `model_market_state_daily_v1` | 3 |
| `model_feature_daily_v1` | 9,547 |
| `model_feature_intraday_shape_v1` | 9,547 |
| `model_label_forward_return_v1` | 0 |
| `model_market_index_daily` | 0 |

覆盖：

| 项 | 结果 |
|---|---:|
| trade daily / 5m | 100% |
| order daily / 5m | 100% |
| book daily / 5m | 100% |
| limit daily | 100% |
| symbol heat | 0% |
| index daily | 0% |

验证：

```bash
python3 backend/scripts/validate_model_feature_store.py \
  --db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db \
  --output /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_20260513_20260515.json
```

验证状态：`pass`。

`model_feature_store.db` 当前约 `15MB`，这 3 个交易日粗略约 `5MB/交易日`。这只是模型特征库，不含 atomic 原子库。

## 已知缺口

1. 5 月最近样本没有 forward label，是因为当前本地数据只到 `2026-05-15`，没有未来 3/5/10/22 个交易日。
2. 指数源接口已接入 builder，但当前 P0 不强制维护指数日线；训练侧需要指数因子时，在训练任务前单独补齐 index DB。
3. `fine_theme_member_daily` 不覆盖 `2026-05-13 ~ 2026-05-15`，个股 heat 字段为空，`has_heat=0`。
4. `fine_theme_heat_daily_v2` 只覆盖到 `2026-05-13`，所以市场级 heat 只命中 1 天。
5. compact current 没有 auction 表，P0 不写 auction 特征。

这些缺口已写入 manifest / validation，不按真实 0 伪造。

## Label Smoke

为验证标签 SQL，额外用临时库跑了更早样本：

```bash
python3 backend/scripts/build_model_feature_store.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-03 \
  --target-db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke.db \
  --reset-target
```

结果：

| 表 | 行数 |
|---|---:|
| `model_feature_daily_v1` | 9,547 |
| `model_feature_intraday_shape_v1` | 9,547 |
| `model_label_forward_return_v1` | 38,020 |
| `heat_feature_rows` | 539 |
| `heat_market_rows` | 3 |

补充结果：

| 项 | 结果 |
|---|---:|
| `label_end_date` / `label_complete_asof_date` 非空 | 100% |
| `entry_buyable` 非空 | 100% |
| 一字涨停不可买 | 20 行 |
| 接近涨停风险 | 28 行 |
| 缺失次日 limit state，保守不可买 | 6 行 |

training mode 验证结果：label 完整性通过；指数未接入时只输出降级 warning，不阻塞 P0。

latest labelable：

| horizon | latest_labelable_signal_date |
|---:|---|
| 3d | `2026-04-03` |
| 5d | `2026-04-03` |
| 10d | `2026-04-03` |
| 22d | `2026-04-03` |

训练过滤口径：

```text
label_complete_asof_date = label_end_date 收盘后可得
```

做月度验证时，训练样本必须满足：

```text
label_complete_asof_date < validation_start
```

`label_end_date` 只表示收益窗口结束日，不作为训练可用性过滤字段。

做逐日盘后预测时，预测特征只能读 signal_date 当天已知的 feature 表，不能读 `model_label_forward_return_v1`。

结论：label 构建逻辑可运行；5 月样本 label 为空不是代码失败。

## 指数源口径

指数不进入每日盘后 P0 强依赖，也不从 Windows 原始 L2 日包抽取。

当前正式口径：

1. P0 支持 no-index 训练。
2. `has_index_data=0` 或 `csi1000_*` 为空时，模型训练侧必须排除所有指数字段。
3. 指数只作为训练侧可选增强，不进入每日盘后强依赖。

原因：

1. Mac compact 里出现的 `sz000852` 是股票代码，不是中证1000指数，不能作为 `000852.SH` 使用。
2. Windows 原始包里 `000852.SZ / 000905.SZ / 000001.SZ` 的 `行情.csv` 也是股票价位，不是指数点位。
3. 指数代码必须走官方指数代码口径，不做 `000852.SZ -> 000852.SH` 这种目录名映射。
4. 指数主要服务模型训练，不是每日候选生产的 P0 必需输入；避免为了低频训练需求增加每日跑数复杂度。

当前保留可选同步脚本：

```text
backend/scripts/sync_model_market_index_daily.py
```

支持：

| index_code | 名称 |
|---|---|
| `000852.SH` | 中证1000 |
| `000905.SH` | 中证500 |
| `000300.SH` | 沪深300 |
| `000001.SH` | 上证指数 |
| `399006.SZ` | 创业板指 |
|
输出到：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

使用原则：

1. 每日盘后不默认运行。
2. 模型训练任务需要指数特征时，训练前单独执行并把结果作为 `build_model_feature_store.py --index-db` 输入。
3. 没有指数时，feature store 保留 `has_index_data=0`，`csi1000_*` 为空，validator 报 warning 但不阻塞 P0。

## 验收命令

prediction 样本构建：

```bash
python3 backend/scripts/build_model_feature_store.py \
  --start-date 2026-05-13 \
  --end-date 2026-05-15 \
  --reset-target
```

prediction 验证：

```bash
python3 backend/scripts/validate_model_feature_store.py \
  --mode prediction \
  --db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db \
  --output /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_20260513_20260515.json
```

training smoke 构建：

```bash
python3 backend/scripts/build_model_feature_store.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-03 \
  --target-db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke.db \
  --reset-target
```

training 验证：

```bash
python3 backend/scripts/validate_model_feature_store.py \
  --mode training \
  --db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke.db \
  --output /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke_validation_training.json
```

输出位置：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke.db
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_validation_20260513_20260515.json
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store_label_smoke_validation_training.json
```

不要提交 git：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store*.db
/Users/dong/Desktop/AIGC/market-data/selection/model_feature_store*_validation*.json
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
/tmp/fine_theme_heat_daily_smoke*.db
/tmp/fine_theme_heat_daily_smoke*.md
```

## Heat 覆盖检查

当前正式 heat 库覆盖：

| 表 | 覆盖 | 交易日 | 行数 |
|---|---|---:|---:|
| `fine_theme_heat_daily_v2` | `2025-01-02 ~ 2026-05-13` | 325 | 205,638 |
| `fine_theme_heat_daily` | `2025-01-02 ~ 2026-04-30` | 319 | 15,950 |
| `fine_theme_member_daily` | `2025-01-02 ~ 2026-04-30` | 319 | 93,770 |
| `fine_theme_lifecycle_daily` | `2025-01-02 ~ 2026-04-30` | 319 | 15,950 |

当前 Mac compact 覆盖 `2025-01-02 ~ 2026-05-15`，所以 `2024-09 ~ 2024-12` 暂时不能在 Mac 上稳定回建 heat；必须等 2024-09 之后的 atomic compact 重跑入库后再验证。

已用临时库验证 v1 heat/member/lifecycle 可回建：

```bash
python3 backend/scripts/build_fine_theme_heat_daily.py \
  --start-date 2025-01-02 \
  --end-date 2025-01-03 \
  --atomic-db /Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db \
  --out-db /tmp/fine_theme_heat_daily_smoke.db \
  --report /tmp/fine_theme_heat_daily_smoke.md \
  --warmup-days 20 \
  --top-k 50
```

结果：

| 样本 | heat | member | lifecycle |
|---|---:|---:|---:|
| `2025-01-02 ~ 2025-01-03` | 100 | 595 | 100 |
| `2026-05-13 ~ 2026-05-15` | 150 | 733 | 150 |

已用临时库验证 v2 heat 可回建：

```bash
MARKET_HEAT_ATOMIC_DB=/Users/dong/Desktop/AIGC/market-data/atomic_facts/shadow/market_atomic_mainboard_compact_current.db \
FINE_THEME_HEAT_V2_DB=/tmp/fine_theme_heat_daily_v2_smoke_202605.db \
python3 backend/scripts/build_fine_theme_heat_daily_v2.py \
  --end-date 2026-05-15 \
  --days 30 \
  --force
```

结果：

| 样本 | v2 heat |
|---|---:|
| `2025-01-02 ~ 2025-01-03` | 1,264 |
| `2026-03-27 ~ 2026-05-15` | 18,990 |

注意：v2 builder 只写 `fine_theme_heat_daily_v2`，不写 `fine_theme_member_daily`；成员表仍由 v1 builder 负责。

训练口径先保留两套：

| 口径 | 使用方式 |
|---|---|
| `with_heat` | 只使用 `has_heat=1` 的样本，允许 `hot_theme_*`、主题 rank、lifecycle、member role 等字段入模 |
| `no_heat` | 排除所有 heat 派生字段；`has_heat` 只作为覆盖诊断，不作为收益预测特征 |

下一步重点不是大跑历史，而是先确认 2024-09 之后 atomic compact 补齐后，`fine_theme_heat_daily_v2` 和 `fine_theme_member_daily` 能否按同一脚本稳定回建。

## 下一步

先把当前 `model_feature_store.db` 和 validation JSON 给模型训练侧看字段是否够用。

如果字段方向确认，下一步再做：

1. 先补齐并验证 heat 覆盖，尤其是 `fine_theme_heat_daily_v2` / `fine_theme_member_daily`。
2. 训练任务如果明确要指数增强，再由训练侧单独准备指数数据。
3. Windows 单日重跑 `2026-05-15`，记录 D/Z 盘、解压峰值、DB 增量。
4. 再选 `2024-09-02` 和 `2025-01` 的 2~3 天做 full L2 跨历史验证。
