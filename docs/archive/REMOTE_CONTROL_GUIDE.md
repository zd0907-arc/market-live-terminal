# 系统异地协同与远程控制白皮书 (V4.0 合并版)

本文档是 Mac(主控端)、Windows(离线算力端)、Tencent Cloud(云生产端) 三台设备的协同工作权威指南。

## 一、 角色定位与数据流转
1. **Mac 电脑**: 司令部。所有关于前端页面、后端接口的代码修改均在这里进行。这里绝不参与抓取任务。
2. **Windows 电脑**: 苦力兼提纯机。负责运行清洗几十上百个 G 的 `D:\MarketData` 离线数据包，也是未来跑每天日内数据防封爬虫的地方。
3. **腾讯云**: 显示器。只能被动接收 Mac 的代码和 Windows 发来的干净数据，绝对不向外网请求。

---

## 二、 Mac 远程控制 Windows 指南 (SSH 隧道)

为了让 AI 或您随时直接在 Mac 终端控制 Windows 的数据清洗：

### 1. 开发前置 SOP：Tailscale 异地组网联通测试
未来在此架构下开发，**首要标准打卡动作**是验证虚拟局域网（Tailscale）的连通性。由于我们在公司（Mac）和家里（Windows）之间跨越了物理路由器，必须依赖 Tailscale 的内网穿透。

*   **Mac 节点 IP**: `100.112.131.36`
*   **Windows 节点 IP**: `100.115.228.56`

**操作步骤**：
在 Mac 终端中先进行 Ping 测试，确保存活：
```bash
ping -c 4 100.115.228.56
```
确认无丢包后，直接通过专属内部 IP 登录 Windows 获取控制权：
```bash
ssh laqiyuan@100.115.228.56
```
- 然后输入那台 Windows 电脑的开机密码（请从本地 1Password/备忘录中获取）即可进入黑框控制权。
- 此时，两端已建立加密隧道，与处于同一家庭局域网下无异。

### 2. 将清洗完的 DB 传回 Mac (如需要)
如果您在 Windows 上跑完了几千万行的超级数据库 `market_data_history.db`，需要传回 Mac：
```bash
# 在 Mac 的终端执行 (非 ssh 状态下)：
scp laqiyuan@192.168.3.108:D:/market_data_history.db ./data/
```

---

## 三、 Mac 远程控制腾讯云指南 (生产环境)

云端 IP: `111.229.144.202` ，账户: `ubuntu`

### 1. 核心 SSH 登陆命令
```bash
# 登陆云端查看日志或数据库排障
ssh -o StrictHostKeyChecking=no ubuntu@111.229.144.202
```

### 2. 代码自动发版流程
这套流程已经写死在 `deploy_to_cloud.sh` 中。当你在 Mac 上改完代码，只需要：
```bash
git add .
git commit -m "update xxxx"
git push origin main
./deploy_to_cloud.sh
```
部署脚本会自动使用 SSH 登入云端，下拉最新的 Git 代码，并执行 `docker compose up -d --build`。整个过程在您的终端是无缝全自动的。

### 3. 上传与覆盖云端超大数据库
当 Windows 把一年的历史数据洗完后，最终要部署到云端取代云端的瘸腿数据库：
```bash
# 在 Mac 终端执行：
scp data/market_data_history.db ubuntu@111.229.144.202:~/market_data_history.db
ssh ubuntu@111.229.144.202 "sudo mv ~/market_data_history.db ~/market-live-termial/deploy/data/market_data.db && sudo docker compose restart backend"
```
