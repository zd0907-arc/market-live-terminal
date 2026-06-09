# Windows 模型训练节点 SOP

更新时间：2026-05-28

## 结论

模型训练默认采用：

```text
Mac 端开发与规划
Windows 端执行长训练
Mac 端回收结果与维护文档
```

Windows 是训练执行节点，不是 Git 主开发环境。

## 1. 固定节点

| 项 | 值 |
|---|---|
| Windows SSH | `laqiyuan@100.115.228.56` |
| Windows 项目目录 | `D:\market-live-terminal` |
| Windows Python | `C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe` |
| 训练运行根目录 | `D:\market-live-terminal\.run\spark_v2_training` |
| 默认特征库 | `D:\market-live-terminal\data\selection\model_feature_store.db` |

当前正式训练默认使用 `model_feature_store.db`。它是从 Mac 侧完整特征库同步到 Windows 的正式别名，已确认覆盖 `2024-09-02 ~ 2026-05-27`。

旧文件 `model_feature_store_smoke_20260401_20260515.db` 已退休到 `Z:\atomic_legacy_backup\windows_retired_20260608\selection\`，不能再作为星火 v2 正式训练默认库。当前 Windows 现场只应把 canonical `model_feature_store.db` 当正式库。实测旧 smoke 库缺少 38 个市场指数相关字段，包括：

- 中证 1000 的完整收盘、均线、斜率、1/5/20 日收益；
- 中证 500、沪深 300、上证指数、创业板指对应的同类字段。

如果继续用旧 smoke 库训练，会导致：

1. 市场环境特征组不完整；
2. Mac / Windows 训练结果不在同一口径；
3. 稳健型与市场状态型结果失真。

## 2. 每次训练前检查

Mac 端先检查：

```bash
ping -c 2 100.115.228.56
ssh -o ConnectTimeout=8 laqiyuan@100.115.228.56 "echo ok"
```

Windows 端必须确认：

1. Python 可用。
2. `pandas / numpy / sklearn / joblib` 可导入。
3. 训练特征库存在。
4. `model_feature_daily_v1` 和 `model_label_forward_return_v1` 的日期范围覆盖本轮计划。
5. 输出 run_id 不覆盖旧结果。
6. 当前没有同类训练进程在跑。

## 3. 脚本同步方式

不要在 Windows 上手改训练脚本。

推荐流程：

```text
Mac 端确认脚本
-> scp 训练脚本到 Windows backend\scripts
-> scp runner / config 到 Windows .run\spark_v2_training\<run_id>
-> Windows 执行
-> Mac 拉回 .run\spark_v2_training\<run_id> 结果
```

如果涉及多个依赖脚本，必须同步完整依赖集合，而不是只传入口脚本。

## 4. 远程命令规则

不要把复杂 Python 或 PowerShell 代码塞进一行 SSH 命令。

禁止作为标准流程：

```text
ssh win 'cmd /c "python -c \"多行代码 / 百分号 / 复杂引号\""'
```

原因：

```text
PowerShell / cmd 对引号、百分号、换行的解析容易不同；
Mac 端 shell、ssh、Windows cmd 会重复解释同一段文本；
失败时经常表现为 SyntaxError 或字符串缺少终止符。
```

推荐两种方式：

1. Mac 生成 `.py` / `.ps1` / `.bat`，上传后执行文件。
2. 复用项目已有的 UTF-16LE base64 `PowerShell -EncodedCommand` 模式。

## 5. 训练命令形态

训练入口必须显式传入数据和输出目录：

```text
C:\Users\laqiyuan\AppData\Local\Programs\Python\Python311\python.exe ^
  D:\market-live-terminal\backend\scripts\<training_script>.py ^
  --feature-db D:\market-live-terminal\data\selection\model_feature_store.db ^
  --out-dir D:\market-live-terminal\.run\spark_v2_training\<run_id>
```

Windows 批处理文件里可以用 `^` 换行；不要把这段写成 PowerShell 的反引号版本后再交给 `cmd /c`。

## 6. 日志与验真

每次训练至少写：

```text
D:\market-live-terminal\.run\spark_v2_training\<run_id>\out.log
D:\market-live-terminal\.run\spark_v2_training\<run_id>\err.log
D:\market-live-terminal\.run\spark_v2_training\<run_id>\run_summary.json
```

长训练是否真的在跑，至少用两个信号确认：

1. Python 进程存在。
2. CPU 时间增长。
3. `out.log` 或结果文件持续更新。
4. `run_summary.json` 或中间 CSV 有新增。

只看 `schtasks Running` 或 SSH 命令未返回，不算验真。

## 7. GPU 现实约束

Windows 有 RTX 4070，但当前基础环境只确认了 `sklearn`。

`sklearn` 的当前树模型基本不使用 4070 GPU。要真正利用显卡，必须另做环境准备：

```text
安装并验证 GPU 版 XGBoost / LightGBM / CatBoost
或建立 PyTorch / CUDA 训练环境
```

未完成 GPU 训练库验证前，Windows 的主要价值是：

```text
不占用 Mac
适合长时间 CPU 训练
本地离数据更近
磁盘空间更充足
```

## 8. 结果回收

训练结束后，Mac 端拉回：

```text
training_report.md
business_readable_leaderboard.csv
monthly_metrics.csv
market_regime_metrics.csv
final_holdout_metrics.csv
daily_top3_candidates.csv
run_summary.json
models/
```

可追溯报告进入：

```text
docs/selection/<training_run_name>/
```

可落地模型进入：

```text
data/selection/models/<source_id>/<source_version>/
```

本地文档和模型归档仍由 Mac 端 Git 管理。
