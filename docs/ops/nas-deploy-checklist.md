# NAS 部署接手清单

更新时间：2026-05-28

## 目标

第一阶段只做一件事：

- 用家里 NAS 替代腾讯云，承载当前项目的轻量前后端与 Windows realtime crawler 的写入目标。

第一阶段明确不做：

- 不搬 Windows 数据主站。
- 不迁移 `D:\MarketData` 全量日包。
- 不迁移 Mac 本地 `77G` 正式研究库到 NAS。

## 当前已确认现状

- NAS 型号：UGREEN DXP4800 Pro
- NAS 局域网 IP：`192.168.3.43`
- NAS 当前开放端口：
  - `80`：可达
  - `443`：可达
  - `445`：可达
  - `9443`：可达
- NAS 当前未开放 SSH：
  - `22`：拒绝连接
- NAS 系统 Web 已占用 `80/443/9443`，项目容器不要再占用宿主机 `80`。
- 当前 Windows crawler 正式目标地址应理解为：
  - `http://dxp4800pro:8080`

## 需要用户手工完成

以下事情我当前不能直接完成，因为需要 NAS 图形后台登录权限，或当前没有 SSH 入口。

### 1. 开 SSH

在 UGOS Pro 里：

1. 登录 NAS Web 后台。
2. 进入 `Control Panel > Terminal`。
3. 打开 `Enable SSH Service`。
4. 端口先保持 `22`，不要先改。
5. 点击 `Apply`。

完成标准：

- Mac 上执行 `nc -vz 192.168.3.43 22` 能连通。

### 2. 准备一个可 SSH 登录的管理员账号

要求：

- 这个账号必须能登录 SSH。
- 这个账号需要能执行 `sudo -i`。
- 先不要只开普通文件账号。

完成后请把这两个信息告诉我：

- SSH 用户名
- SSH 端口

### 3. 给这台 Mac 的公钥加到 NAS

这台 Mac 当前可用公钥文件：

- [id_ed25519.pub](/Users/dong/.ssh/id_ed25519.pub)

你需要把这个公钥内容加入 NAS 上目标登录用户的 `~/.ssh/authorized_keys`。

如果 UGOS 还没做图形化导入，最简单的办法是：

- 先开启 SSH 密码登录。
- 你自己从终端登录一次 NAS。
- 再把 [id_ed25519.pub](/Users/dong/.ssh/id_ed25519.pub) 内容追加到 `~/.ssh/authorized_keys`。

完成标准：

- 这台 Mac 执行 `ssh <user>@192.168.3.43` 不再要求输入密码。

### 4. 安装并启用 Docker

在 UGOS Pro 的 App Center 里安装 Docker。

完成标准：

- NAS 上能看到 Docker 管理界面。
- 我通过 SSH 执行 `docker --version` 有输出。
- 最好同时支持 `docker compose version`。

### 5. 创建项目持久化目录

这一步现在不需要你手工做。

当前已确认我可以直接创建并写入：

```text
/volume1/docker/market-live-terminal/app
/volume1/docker/market-live-terminal/data
```

### 6. 先不要动 Windows crawler

这一步由我来改。

如现场仍残留旧 `CLOUD_API_URL=http://111.229.144.202`，应在 cutover 后改到 NAS。

## 用户完成后发给我的信息

你只要回我下面 3 项：

1. `SSH 已开`
2. `SSH 用户名`
3. `Docker 已可用`

可选补充：

- 如果你改了 SSH 端口，也把端口号一起发我。
- 如果你已经装了 Tailscale，也把 NAS 的 Tailscale IP 发我。

## 你做完后我会直接接手

我会自己完成这些事：

1. SSH 连上 NAS，做基础探测。
2. 把当前项目代码传到 NAS。
3. 改一份 NAS 专用 `docker-compose` 配置：
   - Web 端口改成 `8080`
   - 保留轻量模式
   - 配好容器数据挂载
4. 在 NAS 上启动前后端容器。
5. 验证：
   - `/api/health`
   - 页面是否可打开
   - 日志是否正常
6. 再回头改 Windows crawler 的目标地址，让它开始写 NAS。
7. 验证 Windows -> NAS 的 ingest 链路。

## 第一阶段目标状态

完成后应当达到：

- 浏览器可访问 `http://192.168.3.43:8080`
- Windows crawler 不再写腾讯云，改写 NAS
- 腾讯云可以退役出这条轻量盯盘链路

## 参考来源

- UGREEN 官方关于 SSH 开启路径：`Control Panel > Terminal > Enable SSH Service`
- UGREEN 官方关于 UGOS Pro / Docker / File Services 能力说明
