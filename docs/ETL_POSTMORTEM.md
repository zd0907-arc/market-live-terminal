# ETL 历史数据刷数复盘 & 操作手册

> 本文档记录 2026-02-28 ~ 03-01 全量 A 股历史数据 ETL 过程中遇到的问题、根因分析和最佳实践。
> 后续再刷数据时 **必须先阅读本文档**。

---

## 一、时间线

| 时间 | 事件 | 状态 |
|------|------|------|
| 02-28 16:00 | V3 ETL 启动（2 workers, 278 ZIP, schtasks 定时触发） | ▶ |
| 02-28 20:27 | **进程静默崩溃** — 停在 106/278（38%） | 💀 |
| 02-28 20:27 ~ 03-01 14:00 | 无人值守状态，PID Lock 残留导致重试循环无法自启 | ❌ |
| 03-01 14:10 | 诊断 + 手动清 Lock + 4 workers 重启 | 🔧 |
| 03-01 14:13 | 恢复运行，manifest 跳过 106 个已完成文件 | ✅ |

---

## 二、遇到的问题 & 根因

### 🐛 问题 1：进程静默崩溃，无错误日志
- **现象**：Python 进程消失（0 个 `python.exe`），日志最后一行只有正常的 tqdm 进度条，没有任何 Exception
- **根因**：**内存不足（OOM）**，Windows 直接杀掉了进程
  - 每个 ZIP 含 ~5000 个 CSV（A 股全市场），4 个 worker 同时解压 + Pandas 读取 → 瞬时内存峰值超过系统限制
  - Python 的 OOM 被操作系统直接 SIGKILL，来不及写 Exception 日志
- **证据**：schtasks 退出码 `267014`（非 Python 标准退出码），无 traceback

### 🐛 问题 2：PID Lock 导致无法自动重启
- **现象**：BAT 的重试循环应该能自动恢复，但实际没有触发
- **根因**：
  1. BAT 的 `taskkill /F /IM python.exe` 在第一行 → 杀掉了所有 Python → 但新的 ETL 还没启动
  2. PID Lock 文件指向已死进程（PID 13104），但 `acquire_pid_lock()` 使用 Windows API `OpenProcess` 检查进程存活性，有时会误判
  3. 最终 schtasks 的 72 小时超时也到了，整个计划任务退出

### 🐛 问题 3：`check_etl.sh` 进度不更新
- **现象**：连续多次 check 都显示 109/278
- **根因**：manifest 的 `DONE` 状态在每个 ZIP **完全处理完**并 commit 后才更新，4 workers 并行处理大 ZIP 时（每个需 ~2-5 分钟），中间状态不可见

---

## 三、修复措施

| # | 修复 | 效果 |
|---|------|------|
| 1 | BAT 去掉 `taskkill`，仅靠 PID Lock 防重复 | Lock 残留→等进程死→重新获取 |
| 2 | BAT 增加重试循环（最多 20 次，间隔 30s） | 崩溃 → 自动清 Lock → 自动重启 |
| 3 | Workers 2→4，充分利用 CPU | 处理速度提升 ~2x |
| 4 | BAT 日志追加写入（`>>`） | 崩溃前后日志连续可追溯 |

---

## 四、操作手册（后续刷数据参考）

### 4.1 前置检查
```bash
# 1. 确认 Windows 节点可访问
ssh laqiyuan@192.168.3.108 "echo ok"

# 2. 确认数据源目录存在
ssh laqiyuan@192.168.3.108 "dir D:\MarketData"

# 3. 确认磁盘空间 (历史DB约2GB，预留5GB)
ssh laqiyuan@192.168.3.108 "powershell -c \"(Get-PSDrive D).Free / 1GB\""
```

### 4.2 启动 ETL
```bash
# 方法1: 通过 schtasks（推荐，后台持久运行）
./restart_etl.exp

# 方法2: 直接 SSH（适合调试，SSH 断开会停）
ssh laqiyuan@192.168.3.108 "python D:\market-live-terminal\backend\scripts\etl_worker_win.py D:\MarketData D:\market-live-terminal\market_data_history.db --workers 4"
```

### 4.3 监控进度
```bash
# 检查 manifest 完成数
./check_etl.sh

# 检查进程是否存活
ssh laqiyuan@192.168.3.108 "tasklist /FI \"IMAGENAME eq python.exe\" /NH"

# 查看实时日志（最后 10 行）
ssh laqiyuan@192.168.3.108 "powershell -c \"Get-Content D:\market-live-terminal\etl_output.log -Tail 10\""
```

### 4.4 崩溃恢复（手动）
```bash
# 1. 清除 PID Lock
ssh laqiyuan@192.168.3.108 "del D:\market-live-terminal\.etl.lock"

# 2. 重启
ssh laqiyuan@192.168.3.108 "schtasks /run /tn ETL_V3_Run"
```

### 4.5 Workers 数量建议

| 机器配置 | 推荐 workers | 说明 |
|----------|-------------|------|
| 8GB 内存 | 2 | 每 worker 峰值 ~1.5GB |
| 16GB 内存 | 4 | 当前 Windows 节点配置 |
| 32GB+ | 6-8 | 视 CPU 核心数而定 |

> [!CAUTION]
> **Workers 不宜超过 `(可用内存GB - 2) / 1.5`**，否则 OOM 风险极高！
> 每个 worker 处理一个全市场 ZIP（~5000 个 CSV）时峰值内存约 1-1.5 GB。

### 4.6 完成后的合并流程
```bash
# 1. SCP 数据库到 Mac
scp laqiyuan@192.168.3.108:D:/market-live-terminal/market_data_history.db ./

# 2. 合并到云端主库
python backend/scripts/merge_historical_db.py

# 3. 验证数据完整性
sqlite3 market_data.db "SELECT count(DISTINCT date) FROM local_history"
```

---

## 五、避坑清单

> [!IMPORTANT]
> 以下是经过实战验证的关键注意事项：

1. **永远使用 `schtasks` 启动**，不要用 SSH 直连（断开=停止）
2. **首次运行先用小数据集验证**（`--test-symbols sh600519`）
3. **Workers 数量宁少勿多**，OOM 无日志、无回滚
4. **BAT 脚本不要包含 `taskkill`**，让 PID Lock 机制管理并发
5. **Manifest 是核心安全网**：无论崩溃多少次，已完成的文件不会被重复处理
6. **check_etl.sh 有延迟**：显示的 DONE 数比实际进度少 1-4 个（正在处理的文件未 commit）
7. **日志用追加模式（`>>`）**，否则重启后崩溃前的日志会被覆盖
