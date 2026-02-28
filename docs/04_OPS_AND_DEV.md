# 04_OPS_AND_DEV (开发与运维 SOP)

> **核心定位**：当准备进行系统的架构升级、代码上线部署或本地调试时所需的标准操作流程（SOP）。在动用 `ssh`、`git push` 前，需要严格参考此文档。

## 一、 网络联通测试规范 (The Tailscale Gate)

在进行任何 Mac <-> Windows 的联动开发和代码推送前，必须确认虚拟内网组网通畅。所有对家庭主机的操作，**废弃 `192.168.3.108` 的原始局域网称呼，统一切换为 Tailscale 魔方化局域网 IP**。

*   **司令部 Mac (您当前的操作机器)**: `100.112.131.36`
*   **雷达站 Windows (运行无头爬虫与爬虫任务)**: `100.115.228.56`

### 1. 探活测试 (Ping)
必须可以在公网跨越公司防火墙 PING 通家里电脑。如果在公司办公室开发：
```bash
ping -c 4 100.115.228.56
```
### 2. 登陆检查与状态恢复 (SSH)
如果需要手动连进家里机器看清洗日志或重启进程：
```bash
ssh laqiyuan@100.115.228.56
# 密码：zhangdong
```
*提示：由于 Windows 不是完整的 Git Repo，且是“无感隐藏自启运行”，如果您只是为了发代码，本步骤甚至都是多余的。直接看发版流程。*

---

## 二、 发版与一键装填协议 (CD/CI Pipeline)

所有的后端业务核心逻辑（包括 Web 服务 `app`、爬虫调度 `scripts`）都会在 Mac 司令部被研发完毕。完成修改后，你面对两个目的地：【腾讯云】和【Windows 雷达站】。

### 目的 A：发版到云端 (腾讯云 FastAPI + Web)
腾讯云运行的主程序通过 Docker 承载。为了避免手工敲一大堆 Docker 构建命令，我们已经封装了完全的流水线。

1. **提交代码核心库**：
   ```bash
   git add .
   git commit -m "feat: added new indicator"
   git push origin main
   ```
2. **触发无间断上线**：
   在 Mac 根目录下执行即可。底层会自动通过 SSH 登入并触发拉取和 Docker 重建。
   ```bash
   ./deploy_to_cloud.sh
   ```

### 目的 B：隔空装填 Windows 洗地/抓取节点
**红线**：Windows 不受 Git 控制。绝不允许手动通过 RDP 等工具拷贝文件过去拖拽！它是一个被物理封印的黑盒主机。

只需在 Mac 根目录执行隔空输送指令：
```bash
./sync_to_windows.sh
```
该指令会在背后：
1. 使用 SCP 命令，极其蛮横地把 Mac 里刚写好的最新 Python `backend/scripts/` 文件覆盖向 Windows 的运行目录。
2. 注入开机自启的注册表批处理，让明早断电来电时它自动跑最新的爬虫逻辑。

---

## 三、 SQLite 数据库安全覆盖

由于我们历史数据非常珍贵且极大。很多时候我们的云端机器是一具空壳。需要把 Windows 苦力长年累月洗好的 GB 级别的历史数据库传上去供 Web 显示。

**历史复活注射 SOP**：
1. SSH 到 Windows，或者通过 SCP 把大数据库下载到本地。
2. 用类似下面这样的超级命令，把清洗好的包强行挤换掉腾讯云那瘸腿的空 DB 文件：
```bash
scp data/market_data_history.db ubuntu@111.229.144.202:~/market_data_history.db
ssh ubuntu@111.229.144.202 "sudo mv ~/market_data_history.db ~/market-live-termial/deploy/data/market_data.db && sudo docker compose restart backend"
```
完成以上替换，前端图表立刻拥有数年的回溯能力。
