# Mac <-> NAS 协作 Runbook

更新时间：2026-06-06

## 1. 结论

长期应该固定成 `Mac -> NAS` 直连协作，不再把 `Windows` 当管理跳板。

现在已经建立并验证过的核心能力有四类：

- `管理`：Mac 可以通过 Tailscale 节点名直接管理 NAS
- `查数`：Mac 可以通过 SSH 在 NAS 上直接查目录、查 sqlite、看容器
- `交付`：项目可以通过 Gitea 私有仓库提交到 NAS
- `访问`：项目服务已经跑在 NAS 上，并且已经验证过私网和临时公网入口

2026-06-06 这轮复检后，当前准确判断已经变成：

- `Mac -> NAS` 这套工作模式已经不只是“方向正确”，而是当前正式控制面
- `SSH / HTTP / Gitea SSH / docker compose / research/current` 这几条关键链路都已重新验证通过
- 默认交付方式已经固定成 `git push nas main`、发布脚本和 `tar | ssh`；普通 `scp / sftp / rsync` 绝对路径上传仍不作为默认方案

## 2. 长期工作模型

以后这套环境按下面分工使用：

| 角色 | 长期职责 |
|---|---|
| `Mac` | 主开发机、文档、远程查数、Git 提交、发布控制台 |
| `NAS` | 私有 Git、在线服务、在线数据库、持久运行容器、未来正式公网入口 |
| `Windows` | 盘中/盘后重计算、特殊源抓取、暂时保留的运行节点 |

原则：

- `日常开发和运维` 从 Mac 发起
- `在线系统` 固定跑在 NAS
- `Windows` 只保留暂时无法迁走的计算/采集职责

## 3. 当前入口约定

以后先记“入口分层”，不要混用。

### 3.1 私网管理入口

优先入口：

```text
dxp4800pro
```

对应使用：

- SSH: `ssh zhangdong@dxp4800pro`
- 项目服务: `http://dxp4800pro:8080`
- Gitea: `http://dxp4800pro:3000`
- Gitea SSH: `ssh -p 2222 -T git@dxp4800pro`

备用入口：

```text
100.119.0.126
192.168.3.43
```

使用原则：

- `在外网` 优先 `dxp4800pro` / `100.119.0.126`
- `在家里局域网` 可直接用 `192.168.3.43`

### 3.2 当前临时公网入口

```text
https://dxp4800pro.tailfff556.ts.net/
```

这条地址的意义：

- 对外访问时，访问者不需要安装 Tailscale
- 它已经证明 NAS 可以直接承担公网服务
- 它只是 `Tailscale Funnel` 的临时公网入口
- 它不是最终 D1 的正式自定义域名方案

### 3.3 最终公网入口目标

正式方案仍然是：

```text
Cloudflare Tunnel + 自定义域名
```

原因只有一个：它才适合长期稳定给别人访问，并且域名可控。

## 4. 已验证能力矩阵

下表区分“能力是否已建立”和“2026-06-06 当前复检状态”。

| 能力 | 能力已建立 | 2026-06-06 复检 |
|---|---|---|
| Tailscale 节点在线 | 是 | 通过 |
| SSH 登录 NAS | 是 | 通过 |
| 远程 `python3` / `sqlite3` | 是 | 通过 |
| `docker compose ps` | 是 | 通过 |
| Gitea SSH / `nas` remote | 是 | 通过 |
| 项目服务私网访问 | 是 | 通过 |
| `/api/health` | 是 | 通过 |
| `/api/selection/health` | 是 | 通过 |
| `research/current` 当前版本检查 | 是 | 通过 |
| `research/archive` 回滚点检查 | 是 | 通过 |

当前最关键的信息是：

- `Mac -> NAS` 已经是当前正式运维入口
- `research/current` 当前正式版本是 `nas_daily_new_20260605`
- 当前仍保留 `Tailscale Funnel` 作为临时公网入口，但正式品牌域名仍属于后续增强项

## 5. 对未来多项目的能力建设要求

你以后会在这台 Mac 上长期做多个项目，所以从 Mac 到 NAS，至少需要固定建立下面五种能力。

### 5.1 能建目录

每个项目在 NAS 上都应该有独立根目录。

推荐固定结构：

```text
/volume1/docker/<project>/
  app/
  data/
  logs/
  deploy/
```

对当前项目：

```text
/volume1/docker/market-live-terminal/
  app/
  data/
  logs/
  deploy/
```

说明：

- `app/`：部署代码、compose 文件、运行脚本
- `data/`：数据库、缓存、导出物、运行数据
- `logs/`：容器外日志、发布日志、排障输出
- `deploy/`：项目级发布配置和模板

### 5.2 能查数据

默认不要先依赖 SMB 挂载。先把“SSH 远程查数据”作为标准能力。

标准动作包括：

- 查目录
- 查文件大小
- 查 sqlite 表结构
- 抽样查最新记录

典型命令：

```bash
ssh zhangdong@dxp4800pro \
  "sqlite3 /volume1/docker/market-live-terminal/data/live/market_data.db '.tables'"
```

### 5.3 能传文件

对 NAS 传文件，长期保留三条路：

1. `git push` 传代码
2. `scp -O` 传单文件
3. `tar | ssh` 传一批文件

约束：

- `scp` 在 macOS 15+ 上默认走 SFTP 子系统，不要直接假设可用
- 对这台 NAS，正式做法是加 `-O`

例子：

```bash
scp -O local-file zhangdong@192.168.3.43:/volume1/docker/market-live-terminal/data/incoming/
```

### 5.4 能提 Git

长期 Git 模式已经明确：`Gitea` 是 NAS 私有主仓。

当前项目 remote：

| Remote 名 | 地址 | 用途 |
|---|---|---|
| `origin` | `https://github.com/zd0907-arc/market-live-terminal.git` | 外部备份 |
| `nas` | `nas-git:zhangdong/market-live-terminal.git` | NAS 主提交入口 |
| `nas-local` | `ssh://git@192.168.3.43:2222/zhangdong/market-live-terminal.git` | 局域网备用 |

日常提交原则：

```bash
git push nas main
```

需要外部备份时再补：

```bash
git push origin main
```

### 5.5 能重启和验服务

只要项目跑在 NAS 上，就必须从 Mac 直接完成下面动作：

- 看容器状态
- 重启容器
- 看健康检查
- 看日志

当前项目默认服务入口：

- 前后端入口：`http://dxp4800pro:8080`
- 健康检查：`/api/health`
- Gitea：`http://dxp4800pro:3000`

## 6. 当前项目的推荐目录规范

针对 `market-live-terminal`，目录先按下面规则收口。

### 6.1 项目根

```text
/volume1/docker/market-live-terminal/app
```

存放：

- 当前在线部署代码
- compose 文件
- 发布脚本

### 6.2 数据根

```text
/volume1/docker/market-live-terminal/data
```

建议进一步固定为：

```text
data/
  live/
  research/
  cache/
  incoming/
  archive/
```

说明：

- `live/`：线上运行依赖的正式数据库
- `research/`：研究产物、页面数据、策略结果
- `cache/`：可重建缓存
- `incoming/`：从 Windows / Mac 新传上来的待整理数据
- `archive/`：旧版本归档

### 6.3 Git / 仓库

Gitea 已经承担仓库能力，所以不建议再手工造一套裸仓库流程。

如果未来某个项目不想进 Gitea，再单独在：

```text
/volume1/docker/<project>/repos
```

下放裸仓库。

## 7. 标准工作流

## 7.1 从 Mac 查 NAS 数据

1. 先确认入口
2. SSH 到 NAS
3. 直接查 sqlite 或目录

例子：

```bash
ssh zhangdong@dxp4800pro
sqlite3 /volume1/docker/market-live-terminal/data/live/market_data.db '.tables'
```

## 7.2 从 Mac 提交项目到 NAS

标准顺序：

1. 本地开发
2. `git commit`
3. `git push nas main`
4. 到 NAS 上拉取/更新部署
5. 重启容器
6. 验证 `/api/health`

## 7.3 从 Mac 上传数据库或大文件

场景划分：

- 单文件：`scp -O`
- 成批目录：`tar | ssh`
- 可版本化代码：`git push`

## 7.4 给外部人员访问

当前分两阶段：

1. 临时公网验证：`Tailscale Funnel`
2. 正式公网发布：`Cloudflare Tunnel + 自定义域名`

不要把这两阶段混成一个结论。

## 8. 当前剩余缺口

当前还没真正收口的，不是“Mac 能不能管 NAS”，而是下面三件事。

### 8.1 Tailscale 数据面稳定性

今天复检说明：

- 设备在线不等于业务端口可用
- 需要单独排查 `22 / 2222 / 8080 / 443` 的可达性

优先排查点：

1. NAS 上的 `tailscale` 容器是否正常
2. Funnel 当前是否仍在指向正确服务
3. 目标容器是否还在监听
4. 是否存在 Docker 网络或端口映射漂移

### 8.2 正式公网域名

当前只有 `*.ts.net` 临时公网地址。

真正要完成 D1，仍需：

- Cloudflare 账号和域名
- `cloudflared` 容器或二进制
- `hostname -> NAS service` 的 Tunnel 配置

正式切换细节统一看：

- `/Users/dong/Desktop/AIGC/market-live-terminal/docs/ops/nas-public-domain-cloudflare.md`

### 8.3 数据目录治理

未来还要继续收口：

- 哪些是正式数据库
- 哪些只是中间缓存
- 哪些可以归档或删除
- Windows 每日跑数后哪些文件要同步到 NAS 的哪个目录

## 9. 故障排查顺序

以后如果再出现“好像连不上 NAS”，不要乱试，按这个顺序查。

1. `tailscale status`
2. `tailscale ping dxp4800pro`
3. `ssh zhangdong@dxp4800pro`
4. `curl http://dxp4800pro:8080/api/health`
5. `ssh -p 2222 -T git@dxp4800pro`
6. 如果上面不通，再退回局域网地址 `192.168.3.43`

核心判断规则：

- `status/ping 通，ssh 不通`：是 TCP 业务链路问题
- `局域网通，Tailscale 不通`：优先查 Tailscale/Funnel
- `Git 不通但 SSH 通`：优先查 Gitea 2222 映射

## 10. 这份文档的定位

这份文档是以后所有 `Mac -> NAS` 协作的总 SOP。

你以后需要处理的事情，只要属于下面任一类，都先回到这份文档：

- 从 Mac 远程查 NAS 数据
- 从 Mac 提交项目到 NAS
- 从 Mac 验证 Gitea / 服务 / 容器
- 判断当前是私网问题还是公网问题
- 判断当前是 Tailscale 问题还是项目部署问题
