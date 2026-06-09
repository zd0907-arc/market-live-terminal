# NAS 正式公网域名 Runbook

更新时间：2026-06-04

## 1. 结论

当前 NAS 的临时公网方案可以用，但不应该继续当正式方案。

准确状态是：

- `Tailscale Funnel` 现在能用
- 但 NAS 宿主机自带 `nginx` 占着 `443`
- `tailscale-nas` 又使用 `host network`
- 所以 Funnel 会长期报 `443` 端口冲突

这不是当前服务挂了，而是临时方案和宿主机 HTTPS 天然冲突。

正式公网方案应改成：

```text
Cloudflare Tunnel + 自定义域名
```

原因：

- `cloudflared` 只做出站连接，不需要在 NAS 上抢宿主机 `443`
- 自定义域名、DNS、后续多站点路由都更可控
- Tailscale 继续保留给私网运维，不再承担正式公网入口

## 2. 当前确认的事实

当前 NAS 上实际情况：

- 项目服务：`http://127.0.0.1:8080`
- Gitea：`http://127.0.0.1:3000`
- Gitea SSH：`127.0.0.1:2222`
- 宿主机 `443` 已被 UGOS 自带 `nginx` 占用
- `tailscale-nas` 日志持续出现 `100.119.0.126:443 bind: address already in use`

这说明：

- 现在不要尝试为了 Funnel 去停 NAS 自带 `nginx`
- 也不要让项目容器去抢宿主机 `80/443`
- 应直接切到 `cloudflared`

## 3. 目标结构

公网和私网以后分开：

- 私网运维：
  - `ssh zhangdong@dxp4800pro`
  - `http://dxp4800pro:8080`
  - `http://dxp4800pro:3000`

- 正式公网：
  - `app.<你的域名>` -> `http://127.0.0.1:8080`
  - 可选 `git.<你的域名>` -> `http://127.0.0.1:3000`

## 4. 已准备好的仓库资产

仓库里已经补好了三样东西：

1. `deploy/docker-compose.cloudflare-tunnel.yml`
2. `ops/nas/nas_enable_cloudflare_tunnel.sh`
3. `ops/nas/nas_disable_tailscale_funnel.sh`

设计原则：

- `cloudflared` 用 Docker 跑
- `network_mode: host`
- 不暴露宿主机端口
- 通过 `TUNNEL_TOKEN` 运行远程托管 Tunnel

## 5. 你必须手工完成的前置步骤

这部分必须你自己在 Cloudflare 后台做，我没法代办。

### 5.1 准备域名

前提：

- 你要有一个自己的域名
- 这个域名已经接入 Cloudflare DNS

如果你不想买域名，这条 runbook 就不是当前优先方案。

免费口径可以直接定成：

- 继续使用当前 `*.ts.net` 的 `Tailscale Funnel` 地址作为公网入口

这套方案的优点是零额外成本；缺点是地址不可品牌化，而且当前仍有 `443` 冲突噪音。

### 5.2 在 Cloudflare 创建 Tunnel

在 Cloudflare Dashboard：

1. 进入 `Networking > Tunnels`
2. 创建一个新的 Tunnel
3. 选择 `Docker`
4. 复制安装命令里的 token

你真正需要给我的，不是整条安装命令，而是里面那个：

```text
eyJ...
```

### 5.3 配置公网 hostname

在 Cloudflare Tunnel 里新增 `Published application`：

主站建议先配：

```text
Hostname: app.<你的域名>
Service: http://localhost:8080
```

如果以后要开放 Gitea 网页，再加：

```text
Hostname: git.<你的域名>
Service: http://localhost:3000
```

注意：

- `cloudflared` 跑在 NAS 上，并且使用 host network
- 所以这里填 `localhost:8080` / `localhost:3000` 是对的

## 6. 我可以直接执行的步骤

只要你给我下面两项，我就能直接继续：

1. 你的正式域名
2. `CLOUDFLARE_TUNNEL_TOKEN`

拿到后我会直接执行：

```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
CLOUDFLARE_TUNNEL_TOKEN='你的 token' \
bash ops/nas/nas_enable_cloudflare_tunnel.sh
```

然后我会验证：

- `cloudflared-nas` 容器是否启动
- 域名是否返回项目首页
- `/api/health` 是否正常

## 7. 切换顺序

正确切换顺序是：

1. 先保留当前 Tailscale Funnel
2. 把 Cloudflare Tunnel 配好并验证通过
3. 确认正式域名可用
4. 再关掉 Tailscale Funnel

关闭 Funnel 用：

```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
bash ops/nas/nas_disable_tailscale_funnel.sh
```

这样做的好处是：

- 切换过程不断网
- 就算 Cloudflare 配错了，临时公网入口还在

## 8. 当前阻塞点

现在真正阻塞正式公网域名落地的，不是 NAS，也不是 Docker，而是这两个外部前提：

1. Cloudflare 账号里的域名归属
2. Tunnel token

在这两项到位前，我已经把仓库侧和 NAS 侧的部署骨架准备好了。

## 9. 当前建议

现在最合理的动作顺序是：

1. 你把域名接到 Cloudflare
2. 你在 Cloudflare 后台建 Tunnel，并把 token 给我
3. 我在 NAS 上起 `cloudflared`
4. 我验证正式域名
5. 我再关掉 Tailscale Funnel，彻底消掉当前 `443` 冲突噪音
