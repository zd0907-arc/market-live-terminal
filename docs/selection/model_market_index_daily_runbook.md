# model_market_index_daily 指数数据运行卡

更新时间：2026-05-23

## 结论

`model_feature_store` 的市场环境字段必须先补本地指数缓存：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

脚本默认读取 `MODEL_INDEX_DB`；未设置时使用 `DATA_DIR/selection/model_market_index_daily.db`。Mac 本地 `DATA_DIR` 默认是 `/Users/dong/Desktop/AIGC/market-data`；Windows 日跑建议显式设置：

```bat
set DATA_DIR=D:\market-live-terminal\data
set MODEL_INDEX_DB=D:\market-live-terminal\data\selection\model_market_index_daily.db
```

日跑不直接依赖外部网络。每日跑数前后只做一次低频指数刷新，`build_model_feature_store.py` 只读本地 index DB。

## 指数范围

P0 固定 5 个：

| index_code | 名称 | Baostock | 作用 |
|---|---|---|---|
| `000852.SH` | 中证1000 | `sh.000852` | P0 必需，生成 `csi1000_*` |
| `000905.SH` | 中证500 | `sh.000905` | 中小盘环境 |
| `000300.SH` | 沪深300 | `sh.000300` | 大盘权重环境 |
| `000001.SH` | 上证指数 | `sh.000001` | 全市场主指数 |
| `399006.SZ` | 创业板指 | `sz.399006` | 成长/20cm 环境 |

字段写入：

```text
index_code, index_name, trade_date, open, high, low, close, volume, amount, source
```

## 数据源策略

主源：

```text
Baostock query_history_k_data_plus
```

已验证 `2024-09-02 ~ 2026-05-22` 五个指数均返回 413 条，字段包含 OHLC、volume、amount。

备用：

```text
Eastmoney push2his kline
```

东财同样能返回完整数据，但连续请求容易 `RemoteDisconnected`，只作为备用和交叉校验，不放进日跑强依赖。

## 一次性历史补数

首次或大范围重建时，从 2024-07-01 开始拉，给 2024-09 和 2025-01 的 MA20 / 20 日收益留 warmup：

```bash
cd /Users/dong/ZhangData/market-live-terminal
python3 backend/scripts/sync_model_market_index_daily.py \
  --source baostock \
  --start-date 2024-07-01 \
  --end-date 2026-05-22
```

如果 Baostock 临时不可用，可备用：

```bash
python3 backend/scripts/sync_model_market_index_daily.py \
  --source eastmoney \
  --start-date 2024-07-01 \
  --end-date 2026-05-22 \
  --sleep 1.2
```

## 每日增量刷新

Windows 每日盘后跑数链路需要增加一步指数刷新。刷新最近 10 个自然日，自动覆盖重复日期，避免节假日、临时失败或补发导致漏数：

```bash
python3 backend/scripts/sync_model_market_index_daily.py \
  --source baostock \
  --daily \
  --lookback-days 10
```

然后再执行 `model_feature_store` 构建。构建脚本默认读取：

```text
/Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

Windows 侧对应路径按 `MODEL_INDEX_DB` 或 `--index-db` 传入。

也可显式传入：

```bash
python3 backend/scripts/build_model_feature_store.py \
  --date 2026-05-22 \
  --index-db /Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db
```

## 验收 SQL

```bash
sqlite3 /Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db "
SELECT index_code, COUNT(*), MIN(trade_date), MAX(trade_date)
FROM model_market_index_daily
GROUP BY index_code
ORDER BY index_code;
"
```

`model_feature_store` 构建后看：

```bash
sqlite3 /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db "
SELECT trade_date, has_index_data, csi1000_close, csi1000_ma20, csi1000_above_ma20
FROM model_market_state_daily_v1
ORDER BY trade_date DESC
LIMIT 5;
"
```

`model_feature_daily_v1` 中 `csi1000_above_ma20 / csi1000_dist_ma20_pct` 不应再全空。

也可以直接运行覆盖率校验：

```bash
python3 backend/scripts/validate_model_market_index_daily.py \
  --index-db /Users/dong/Desktop/AIGC/market-data/selection/model_market_index_daily.db \
  --feature-db /Users/dong/Desktop/AIGC/market-data/selection/model_feature_store.db
```

## 日跑约束

- 指数刷新失败不能直接阻断 L2/atomic/selection 主链路。
- 指数刷新失败应在 report / validator 中报警。
- 训练回填任务可以把 `000852.SH` 覆盖率设为硬门槛。
- 预测日更任务只依赖本地缓存；外网失败时沿用缓存，但必须输出最新指数日期。
