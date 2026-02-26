# 腾讯云服务器远程控制指南 (Mac 新手版)

本文档旨在帮助你快速、正确地从 Mac 本地连接到腾讯云服务器，执行各种人工运维命令（如查看数据库、强行手动回补数据等）。

## 1. 核心概念：你在哪敲命令？
运维过程中经常会因为“敲命令的窗口不对”导致执行失败，请牢记以下两个环境的区别：

- **💻 本地终端 (Your Mac)**:
  - 这是你自己电脑上的黑框。在这里你的路径通常是 `~/Desktop/AIGC/market-live-terminal`。
  - **只在这里执行**：`npm run dev` (本地调试前端)、`python -m backend.app.main` (本地调试后端)、`./deploy_to_cloud.sh` (向云端发版)。
- **☁️ 云端终端 (Tencent Cloud)**:
  - 这是远程服务器里面的黑框环境。
  - **只在这里执行**：排查线上数据库问题、查看线上错误日志、执行数据强行回补脚本等。

---

## 2. 如何进入云端终端 (SSH 登录)

不需要安装任何第三方软件，Mac 自带的 `终端 (Terminal)` 即可完成。

### 第一步：打开本地终端
按下 `Command(⌘) + 空格` 调出聚焦搜索，输入 "终端" 或 "Terminal"，回车打开。

### 第二步：敲击登录指令
在本地终端中输入以下命令并回车：
```bash
ssh ubuntu@111.229.144.202
```

### 第三步：输入云端密码
- 如果提示 `Are you sure you want to continue connecting (yes/no)?`，输入 **`yes`** 并回车。
- 接着会提示 `ubuntu@111.229.144.202's password:`，此时盲打你的腾讯云 Root/Ubuntu 密码并回车。（注意：屏幕上不会显示密码字符或星号，这是正常的安全屏障）。

✅ **登录成功标志**：当你看到命令行最左边变成了类似 `ubuntu@VM-xx-ubuntu:~$` 的字样，说明你已经成功进入云端了！

---

## 3. 云端常用操作速查手册

进入云端之后，最常做的操作都在项目文件夹里。操作的**第一步永远是进入项目目录**：

```bash
cd ~/market-live-terminal
```

### 🛠 场景 A：强制修复单只股票的历史数据 (v3.0.10 新增)
如果发现生产环境某只股票没有 30 分钟历史图或者缺得厉害，在云端终端执行这行魔法命令：

```bash
# 务必保证在 ~/market-live-terminal/deploy 目录下执行
cd ~/market-live-terminal/deploy
sudo docker compose exec backend python backend/scripts/force_fix_stock.py 股票代码1 股票代码2
```
*示例：`sudo docker compose exec backend python backend/scripts/force_fix_stock.py sz000833 sh603629`*

### 🛠 场景 B：拉取全部 60 天数据兜底全家桶
如果想把自选股池子里的票统一从头彻尾修一遍：

```bash
cd ~/market-live-terminal/deploy
sudo docker compose exec backend python backend/scripts/run_batch_backfill.py
```

### 🛠 场景 C：查看服务器运行有没有报错
如果云端某个数据突然卡住，查看线上 Docker 的日志：

```bash
cd ~/market-live-terminal/deploy
# 查看后端日志 (不停滚动，按 Ctrl+C 退出)
sudo docker compose logs -f backend

# 查看前端日志
sudo docker compose logs -f frontend
```

### 🛠 场景 D：退出云端回到 Mac
工作完成后，如何从云端“退房”回到你的 Mac 本地？
可以直接关闭终端窗口，或者敲键盘：
```bash
exit
```
回车后，左侧的提示符变回 `dong@ZhangdongdeMacBook-Air`，就说明你回来了。
