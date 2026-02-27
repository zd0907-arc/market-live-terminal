# Windows 离线算力网关 Standard Operating Procedure (SOP)

本文档专门解答关于 **“Windows 数据引擎”** 的长期运行机制、数据合并安全、以及完全免接触的远程控制方案。

---

## 1. 核心定心丸：关于“数据覆盖”的绝对安全声明

您非常敏锐地指出了“覆盖”这个词的危险性。请放心，系统设计的并非粗暴的“文件替换合并”，而是极具防御性的 **“增量合并 (Merge OR Ignore)”**。

*   **只补充，不破坏**：当我们把 Windows 洗好的 `market_data_history.db` 传到腾讯云后，执行的是专门编写的合并脚本 `merge_historical_db.py`。
*   **SQL 层面的保护**：该脚本执行的核心逻辑是 `INSERT OR IGNORE INTO main.history_30m SELECT * FROM ...`。
*   **含义**：它会逐条对比。如果云端已经有 2026年2月28日 10:30 的某只股票数据，它**绝对不会去覆盖或修改**。它只会把云端缺失的过去 1 年的 30 分钟 K 线、每日汇总 K 线及逐笔记录给“填补”进去。
*   **其他表不受影响**：离线洗出来的数据只有交易 `history` 和 `ticks`，合并脚本只会插这几张表。云端里您辛苦积累的“散户情绪摘要 (sentiment)”、“用户的配置阈值 (app_config)”等，**连碰都不会被碰一下**。

---

## 2. i5-12400 算力分配方案

您的电脑是 **Intel i5-12400**。
*   **硬件参数**：这颗 CPU 是 6 大核 / 12 线程架构。这在解压和跑 Pandas 矩阵运算时是非常优秀的中端神U。
*   **最优火力配置**：在执行多进程脚本时，建议保留 2 个线程给 Windows 系统做周转，剩下的 10 个线程全部拉满参与计算。
*   **执行口令**：待数据下载完毕，您执行这行命令即可（注意最后的 `--workers 10`）：
    ```bash
    python backend/scripts/etl_worker_win.py "您下载的文件夹绝对路径" "market_data_history.db" --workers 10
    ```

---

## 3. 完全免接触：Mac 遥控 Windows 方案

您要求“完全在 Mac 上操作，不碰 Windows 电脑”，这不仅可以实现，而且是高级开发者的标配（称为 Headless Node）。

### 步骤前提：开启 Windows 的 SSH 服务
在您的 Windows 电脑上（最后一次碰它）：
1. 打开“设置” -> “应用” -> “可选功能” -> “添加功能”。
2. 搜索 **OpenSSH 服务器**，安装它。
3. 打开 Windows 的“服务(services.msc)”，找到 **OpenSSH SSH Server**，将其启动类型改为“自动”，并点击“启动”。

### 未来日常操作 (纯 Mac 视角)
以后，只要您的 Windows 电脑开着机（连着同一个局域网的 WiFi 或网线），您只需要在 Mac 的终端里：

1. **远程登录 Windows**:
   ```bash
   # 假设您的 Windows 局域网 IP 是 192.168.3.108，用户名是 laqiyuan
   ssh laqiyuan@192.168.3.108
   # 输入 Windows 的开机密码后，您的 Mac 终端就变成了 Windows 的控制台！
   ```

2. **在 Mac 里指挥 Windows 干活**:
   ```bash
   cd D:\AIGC\market-live-terminal
   git pull origin main  # 拉取最新的清洗脚本
   python backend/scripts/etl_worker_win.py ...  # 启动清洗
   ```

3. **直接从 Windows 发射数据到云端 (Data Launch)**:
   ```bash
   # 清洗完毕后，还在刚才那个 Mac 终端（此时控制着 Windows）里，直接执行：
   scp market_data_history.db ubuntu@111.229.144.202:/home/ubuntu/market_data_history.db
   ```
   **至此，所有的运算、拉取、上传，全都是您坐在 Mac 前，通过命令行“遥控” Windows 完成的。**

---

## 4. 终极数据管线图景 (Data Pipeline Vision)

您问到这批历史数据做完后，未来的数据该怎么玩、Windows 还有啥用？这就是我们的终极大棋：

### 阶段A：创世回填 (咱们现在正在做的)
*   **目标**：把过去 1-2 年的空白期补齐。
*   **方案**：用 Windows 的算力硬吃几百 G 压缩包，合并到云端。此生只做这一次。

### 阶段B：日常巡航 (The Live Ingestion Pipeline)
回填完成后，您的 Windows **不需要每天开几十个核咆哮**，但它**每天盘中必须保持轻度唤醒**，作为实时雷达！

*   **为什么云端不能自己拉？**
    *   我们的云端 IP 被东方财富永久封锁，它是一个“睁眼瞎”。云端现在只负责提供网页、图表和保存数据库。
*   **雷达与基站的内网贯通 (Ingestion API)**：
    *   在交易日，您的 Windows 会化身为“外挂雷达”。它每 3 秒去抓一下盘口，每 3 分钟去拉一下逐笔明细。
    *   **核心安全点**：Windows 抓到后**不存本地直接转发**。它会把这些活水数据打包成加密 JSON，通过 `POST` 请求直接“射入”腾讯云的 `/api/internal/ingest` 高危接口。
    *   **无感合并**：云端接到数据，悄无声息地写入云库。您的手机刷新网页，立刻看到了最新的 30 分钟 K 线跳动！

### 阶段C：终极免接触——无感自启设置 (Set Once, Run Forever)
**【架构勘误】**：由于您的 Windows 机器在之前的系统搭建中，是作为纯粹的离线接收端（只有通过 SCP 拷贝过去的 `backend` 文件夹），它**并没有安装 Git 仓库**。因此，您**绝对不需要**去 Windows 电脑上执行复杂的 Git Pull 或寻找启动文件夹！

为了实现真正的“双手离开 Windows”，我刚刚在您的 Mac 司令部为您锻造了终极遥控钥匙：**`sync_to_windows.sh`**。

#### 真正的一键部署 (只需在 Mac 上操作)
在您的 Mac 终端里（确保您在 `market-live-terminal` 项目根目录下），直接执行这一行代码：

```bash
./sync_to_windows.sh
```

**这管代码在背后做了什么骇人听闻的操作？**
1. 它会通过 SSH 暗网，潜入您的 Windows 系统，创建好所需的所有目录结构。
2. 它会把刚才写好的最新雷达爬虫代码 (`live_crawler_win.py`) 和核心引擎 (`etl_worker_win.py`) 隔空传送到 Windows 的解压盘里。
3. 最核心的：它会使用 Windows CMD 命令行，**直接把自启文件塞进 Windows 最深处的隐藏级开机自启文件夹里** (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`)。

在这个过程中，它可能会提示您输入 2-3 次 Windows 电脑的开机密码。

#### 大功告成，物理隐藏！
跑完这行代码后，**结束了！**
*   **永远无人值守**：以后哪怕您家断电了重新来电，只要那台 i5 电脑一亮机进入桌面，它就会自动在后台跑起这个雷达服务。工作日它勤勉抓取数据并秘密射入云端；收盘和周末它就安安静静打盹，CPU 占用几乎为 0。您永远不需要再去碰它。
*   如果您想看看它活得好不好，随时可以用 `ssh laqiyuan@192.168.3.108` 查房。

### 突发情况：云端宕机/周末维护了怎么办？
假设腾讯云挂了一个星期。等您重新开机：
1. **云端漏数据**：断机期间，Windows 射向云端的数据全部失败丢失。
2. **您的复活操作 (Mac 直连补漏)**：
   打开 Mac 上的终端，执行我们在 `v3.0.x` 就写好的秘密武器：`./sync_local_to_cloud.sh`。Mac 会瞬间替代 Windows，去外网把缺失的这几天历史打包，像胶囊一样直连注射回腾讯云。瞬间抚平断层。

**一句话总结**：
此次 Windows 的满载咆哮，是为了这套系统长治久安所需要经历的唯一一次大手术。手术一旦成功合并，云端系统将彻底独立、自愈，再也不需要 Windows 来做日常苦力了。
