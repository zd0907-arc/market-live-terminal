# NAS Tailscale 通路排障复盘

更新时间：2026-06-03

## 1. 现状描述

这次排障的目标，是把当前这台 **不在家里局域网里的 Mac**，通过 **Tailscale** 直接连到家里的 NAS，后续再基于这条通路做远程运维和部署。

当前卡点不在 Mac，也不在 Tailscale 控制台网页本身，而在 **NAS 上的 Tailscale 容器没有稳定上线**。

### 1.1 当前已经确认的事实

- Mac 端 Tailscale 已安装并登录成功。
- Tailscale 管理台里能看到 NAS 设备：
  - 设备名：`dxp4800pro-1167`
  - Tailscale IP：`100.98.2.43`
- 但这个“看得到设备”不等于“设备已经能通信”。

我实际查到的状态是：

- `Active: false`
- `InEngine: false`
- `InMagicSock: false`
- `RxBytes: 0`
- `TxBytes: 0`
- `LastHandshake: 0001-01-01T00:00:00Z`

这说明：

- 设备已经注册到 Tailscale 控制面
- 但 **数据面没有真正建立连接**
- 所以 Mac 侧无法通过 Tailscale IP 连通 NAS

### 1.2 直接表现

对 NAS 的 Tailscale IP `100.98.2.43` 做过多次连通性测试，结果都是失败：

- `curl http://100.98.2.43/` 超时
- `curl https://100.98.2.43/` 超时
- `nc -vz 100.98.2.43 22 80 443 8080 8443` 超时

也就是说：

- 不是“SSH 没开”这么简单
- 而是 **这台 NAS 作为 Tailscale 节点本身就没有稳定接入 tailnet**

### 1.3 根本卡点

NAS 上当前采用的是 Docker 方案，容器名是：

- `tailscale-nas`

我从日志里确认到，它一直在循环下面这件事：

1. 启动 `tailscaled`
2. 生成新的 Tailscale 登录链接
3. 等待认证
4. 约 60 秒后失败退出
5. 重新生成新的 node key 和新的登录链接

关键报错特征：

- `profile data directory: profile not found`
- `machineAuthorized=false`
- `AuthURL is https://login.tailscale.com/a/...`
- `tailscale up failed: signal: killed`

所以当前真正的问题是：

- **认证状态没有稳定保存**
- 或者说 **容器每分钟就被打断重来，导致授权来不及落到当前实例**

### 1.4 为什么 Tailscale SSH quickstart 不是当前解法

你在控制台里看到的：

- `tailscale set --ssh`
- `ssh dxp4800pro-1167`

这套引导的前提是：

- 设备已经稳定连上 tailnet
- `tailscaled` 已经正常在线

而我当前卡在更前面：

- **NAS 节点还没有稳定在线**

所以这套 quickstart 不是当前主问题的解法，只是后续功能配置。

## 2. 尝试过程

## 2.1 做过的基础确认

我先确认了这条链路上每一段是不是都通：

### Mac 侧

- 确认 `tailscale` 已安装
- 确认已登录
- 确认能看到 Windows、Mac、NAS 三台设备

### NAS 侧

- 确认你已经在绿联云里创建了 `tailscale-nas` 容器
- 确认容器在 Docker 管理界面显示“运行中”
- 确认 Docker 权限已经补齐

### Tailscale 管理台

- 确认管理台里确实出现了 `dxp4800pro-1167`
- 确认它拿到了 `100.98.2.43`

这一轮确认的结论是：

- **表面上已经接近成功**
- 但实际通信层仍然没起来

## 2.2 做过的连通性验证

为了避免误判，我没有只看网页状态，而是直接做了通信测试：

- `tailscale status --json`
- `tailscale ping`
- `curl`
- `nc`

结果一致：

- NAS 设备存在
- 但没有真实握手
- 所有访问都超时

这一步把问题范围从“网页登录/权限/局域网路由”收窄到了：

- **NAS 端的 Tailscale 运行状态本身异常**

## 2.3 做过的容器级排查

我进一步从绿联云本机接口抓到了容器配置和日志。

已确认的容器配置包括：

- 镜像：`ghcr.io/tailscale/tailscale:stable`
- 网络：`host`
- 权限：`privileged`
- 关键环境变量：
  - `TS_USERSPACE=false`
  - `TS_DEST_IP=192.168.3.43`
  - `TS_STATE_DIR=/volume1/docker/tailscale`
  - `TS_AUTH_ONCE=true`

然后我重点看了日志，发现了两个核心现象：

### 现象 A：认证链接不断变化

日志会不断生成新的：

- `https://login.tailscale.com/a/...`

这意味着：

- 每次容器重启，都会对应新的认证上下文
- 用户如果点的是旧链接，授权可能落不到当前容器实例上

### 现象 B：认证等待只有约 60 秒

日志里反复出现：

- `tailscale up failed: signal: killed`

这说明：

- 容器不是“挂着等你慢慢授权”
- 而是很快就超时结束，再重来一轮

## 2.4 做过的网页登录尝试

我还尝试过利用你当前 Mac 上已经登录的 Chrome 会话，直接去消费最新认证链接，减少人工来回切换。

做过的动作包括：

- 抓取容器日志里的最新 `AuthURL`
- 在你当前已登录的 Tailscale 控制台里打开该链接
- 检查是否进入真正的授权完成页

这个过程里碰到的困难是：

1. 链接是时效性的  
   容器每次重启，链接都会换。

2. 有时打开的是登录页，不是最终授权确认页  
   这意味着当前浏览器上下文并没有稳定地完成这次设备授权。

3. 即便设备页里已经能看到 NAS，也不代表这次认证真的落到了运行中的容器实例  
   日志里始终没有出现稳定成功的信号。

## 2.5 这次排障里失败的尝试

下面这些路径都没有把问题真正解决：

### 失败尝试 1：只看管理台里出现了 NAS 设备

失败原因：

- 这只能证明控制面注册成功过一次
- 不能证明当前实例正在正常通信

### 失败尝试 2：直接用 Tailscale IP 连 NAS

失败原因：

- 节点并没有真实握手
- 所以 `100.98.2.43` 无法连通

### 失败尝试 3：按 Tailscale SSH quickstart 往后推

失败原因：

- 这一步依赖节点先稳定在线
- 当前基础条件不成立

### 失败尝试 4：用当前网页会话直接消费认证链接

失败原因：

- 链接频繁变化
- 容器每分钟重启
- 授权结果没有稳定落盘

## 2.6 本次排障的边界判断

到目前为止，可以明确排除的方向有：

- 不是 Mac 没装好 Tailscale
- 不是 Tailscale 管理台完全没登录
- 不是纯粹的“SSH 没开”
- 不是 Windows 中转这条路必须存在

当前最值得聚焦的方向只有一个：

- **NAS 上 `tailscale-nas` 容器的认证和状态持久化有问题**

## 3. 后续计划

接下来不应该再围着 `tailscale set --ssh` 或 `ssh dxp4800pro-1167` 转，而应该先把 **容器稳定上线** 这件事解决。

## 3.1 下一步的主方向

我准备按下面顺序推进：

### 方案 A：先确认状态目录到底有没有持久化

重点确认：

- `TS_STATE_DIR=/volume1/docker/tailscale`
- 对应挂载目录是否真的可写
- 里面是否真的生成并保留了 Tailscale state

如果这个目录不可写、没挂对、或重启后状态丢失，就会直接解释当前循环。

### 方案 B：避免交互式登录，改成稳定认证方式

当前方案的问题在于：

- `TS_AUTH_ONCE=true`
- 交互授权窗口太短

更稳的做法是：

- 改成 **非交互认证**
- 让容器启动时直接拿稳定凭证完成接入

这样可以绕过“每分钟换链接”的问题。

### 方案 C：必要时重建 Tailscale 容器

如果现有容器配置本身就不对，最省时间的路径不是继续补丁式试错，而是：

- 保留目标目录
- 用明确的参数重建一个干净容器
- 再验证上线状态

## 3.2 后续验证标准

后面不再以“页面里看到了设备”为成功标准，而要同时满足下面这些条件：

### Tailscale 状态标准

- `Active: true`
- `InEngine: true`
- `LastHandshake` 不为零
- `RxBytes/TxBytes` 有增长

### 网络访问标准

- Mac 上能访问 NAS 的 Tailscale IP
- 能访问 NAS Web 服务
- 能稳定跑通至少一个实际操作链路

### 运维标准

- 不依赖 Windows 中转
- 不要求局域网环境
- 可以从外部网络下的 Mac 直接管理 NAS

## 3.3 当前建议

现阶段不要再把精力放在：

- `tailscale set --ssh`
- `ssh dxp4800pro-1167`
- Tailscale SSH quickstart

因为这些都建立在“节点已经稳定在线”的前提下。

当前正确的顺序应该是：

1. 先修 `tailscale-nas` 容器稳定接入
2. 再验证 Mac -> NAS 直连
3. 最后才配置 SSH / 浏览器终端 / 后续部署链路
