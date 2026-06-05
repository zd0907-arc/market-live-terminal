# NAS 迁移总规划

更新时间：2026-06-04

## 1. 这份文档解决什么问题

这次迁移的目标，不是简单把腾讯云换成 NAS，而是把整套链路收口成一套长期稳定结构：

- NAS 负责在线服务、Git、运行时数据承载
- Windows 负责盘后重跑，以及在迁移完成前继续承担盘中 crawler
- Mac 负责开发、部署、排障、日常运维

腾讯云当前先不动。等 NAS 侧链路稳定后，再决定是否退役。

## 2. 当前已经确认的事实

### 2.1 NAS 当前状态

- NAS 前后端已经跑通
- 当前局域网地址可用：`http://192.168.3.43:8080`
- 当前 Tailscale 私网地址可用：`http://dxp4800pro:8080`
- 当前公开验证地址可用：`https://dxp4800pro.tailfff556.ts.net/`
- 这条公开地址不要求访问者安装 Tailscale
- 但它只是临时公网通路，不算 `D1` 完成；`D1` 仍然要求 `Cloudflare Tunnel + 自定义域名`

已验证页面 / API：

- `/api/health`
- `/api/selection/health`
- `/api/selection/daily-candidates`
- `/api/market_heat/latest`
- `/api/trend-research/ideas`
- `/selection-research`

### 2.2 NAS 数据当前状态

- NAS 已经完成 `research/current` 口径切换
- 当前运行态不是继续吃旧 flat 根，而是吃：
  - `live/`
  - `research/current/`
- 但这次切换走的是 bootstrap 路线，不是完整 79GB 正式库整包上传
- 当前 `research/current` 是基于 NAS 已有 flat 数据整理出来的可运行版本

当前 bootstrap `research/current` 主要数据日期：

- atomic / selection / feature / market index / market_heat_v2：`2026-05-27`
- `fine_theme_heat_daily.db`：`2026-04-30`
- `forecast`：`2026-05-13`

这说明：

- 迁移结构已经跑通
- 线上查询主链已经落到 NAS
- 但 NAS 上的数据还不是最新

### 2.3 Windows 当前状态

- Windows 当前仍承担两类职责：
  - 盘中 realtime crawler
  - 盘后正式跑数与大库产出
- 这两类职责不应长期绑在一起

### 2.4 Mac 当前状态

- Mac 当前两个核心目录仍然是：
  - `/Users/dong/Desktop/AIGC/market-live-terminal`
  - `/Users/dong/Desktop/AIGC/market-data`

它们职责必须明确区分：

- `market-live-terminal`：代码仓库、脚本、文档、部署资产、少量兼容数据
- `market-data`：本地正式数据根，供研究、回补、发版准备使用

## 3. 当前迁移已经做完什么

截至 `2026-06-04`，已经完成的事情是：

1. NAS 前后端完整查询链路已跑通
2. Gitea 已经部署并可用
3. Tailscale 私网访问已跑通
4. Tailscale Funnel 临时公网访问已跑通
5. NAS 侧 `research/current` 已建立
6. NAS 线上 compose 已切到新目录口径：
   - `LIVE_DATA_ROOT=/runtime-data/live`
   - `RESEARCH_CURRENT_ROOT=/runtime-data/research/current`
7. 基于 NAS 现有 flat 研究库完成了 bootstrap current
8. NAS smoke 已通过，说明“研究查询主链落到 NAS”这件事已经成立

一句话：

- 现在不是“NAS 还没跑起来”
- 而是“NAS 已经跑起来，但还有三块没收口：盘中 crawler、目录治理、正式公网域名；另外还要补最新数据”

## 4. 长期目标架构

长期目标不是三端并列，而是三端分工明确：

```text
Mac
  -> 代码开发 / 部署 / 排障 / Git 提交 / 远程运维

Windows
  -> 盘后重跑工人机
  -> 原始大包下载与处理
  -> 研究库 / 特征库 / 明细底座产出
  -> 迁移完成前继续承担盘中 crawler

NAS
  -> 唯一在线服务节点
  -> 前端 / 后端 / Gitea
  -> 线上实时数据
  -> 研究查询主入口
  -> 外网访问入口
```

一句话：

- `NAS = 生产主站`
- `Windows = 跑数工厂`
- `Mac = 开发与运维控制台`

## 5. 剩余任务顺序

当前剩余任务不再是“重做一次大迁移”，而是按下面顺序收口：

### A1：把盘中 realtime crawler 从 Windows 挪到 NAS

目标：

- 交易时段不再依赖 Windows 持续开机
- active symbols / watchlist / snapshots / ticks / final sweep 都由 NAS 本机完成

这一步完成后：

- Windows 可以开始向“只保留盘后工人机”收口

### B1-补：把缺失日期的数据定向补到 NAS

这不是重新做一次全量 79GB 上传。

当前更合理的做法是：

- 以 NAS 当前 `research/current` 为基线
- 只补 `2026-05-27` / `2026-05-28` 之后缺失的几天
- 把 NAS 查询主链先追平到本地正式数据

这一步的目标不是目录治理，而是“先把 NAS 上的正式库追到够新”。

### C1：`market-data` 目录治理彻底收口

这一步要解决两件事：

1. Mac 本地 `market-data` 的边界和目录层级
2. NAS 上运行期数据结构的正式落位

当前 NAS 虽然已经在用 `research/current`，但它还是一个 bootstrap current，不是最终治理完成态。

`C1` 的目标是把：

- 正式库
- 缓存
- 研究产物
- 临时导入物

彻底分开，不再混放。

### B2：未来每日跑数后的 Windows -> NAS 同步机制

这一步是新增明确任务。

未来目标不该是：

- Windows 跑完数据 -> 同步回 Mac

而应该改成：

- Windows 跑完数据 -> 直接同步到 NAS `staging` 或约定目录
- NAS 校验后切 `current`
- Mac 只作为开发和运维端，不再承担生产数据中转站

### D1：正式公网域名方案

这一步仍然放最后。

正式目标仍然是：

- `Cloudflare Tunnel + 自定义域名`

当前的 Tailscale Funnel 只证明：

- “公网访问这件事能通”

它不等于：

- “正式公网域名方案已完成”

### E1：腾讯云退役决策

腾讯云现在先不动。

前提：

- `A1`
- 缺失数据补齐
- `C1`
- `B2`
- `D1`

都稳定后，再决定是否退役。

## 6. 目录规划：不是只分“开发文件夹”和“数据库文件夹”

你现在的判断是对的：

- 只分 `market-live-terminal` 和 `market-data` 不够
- `market-data` 里面还必须再分层

### 6.1 Mac 上这两个目录到底是什么意思

```text
/Users/dong/Desktop/AIGC/
  market-live-terminal/   # 程序本体
  market-data/            # 本地正式数据根
```

不要再用 `code`、`optional mirror` 这种抽象词。

直接按真实职责理解：

- `market-live-terminal`
  - 代码
  - 部署脚本
  - 文档
  - 少量兼容数据
  - 不承担正式大库主存储职责

- `market-data`
  - 运行期数据库
  - 缓存
  - 研究产物
  - 导入包
  - 归档

### 6.2 `market-data` 的目标结构

后续目标结构建议固定为：

```text
market-data/
  live/
    market_data.db
    user_data.db

  research/
    current/
      atomic_facts/
      selection/
      market_heat/
    staging/
    archive/

  cache/
    market_heat/
    eastmoney_sector_cache/

  artifacts/
    market_heat/
    selection/

  incoming/
```

含义分别是：

- `live/`
  - 在线轻量运行库
  - 盘中会变化

- `research/current/`
  - 当前正式研究库
  - 供选股研究 / 热点 / 趋势研究 / 复盘主链使用

- `research/staging/`
  - Windows 新产物先落这里
  - 校验通过后再切到 `current`

- `research/archive/`
  - 历史回滚点

- `cache/`
  - 缓存，不是真相源

- `artifacts/`
  - 回测、专题导出、分析结果

- `incoming/`
  - 手工搬运、待分拣对象

### 6.3 这套结构在 NAS 上的当前现实

当前 NAS 上已经有这套目标结构的骨架：

- `live/`
- `research/current`
- `research/staging`
- `research/archive`
- `cache/...`
- `artifacts/...`
- `incoming`

但要注意：

- 当前 `research/current` 仍然是 bootstrap current
- 还没完成“最新正式库追平”
- 也还没完成“目录治理彻底收口”

## 7. 为什么现在看起来乱

因为当前至少有 4 类东西还混在一起：

1. 正式库
2. 缓存
3. 实验 / 回测 / 研究导出
4. 历史兼容对象

所以你会看到很多 `.db / .json / .csv / .md` 混在同一层级。

这不是某个文件单独有问题，而是结构还没收口。

## 8. 当前治理原则

现阶段先遵守这 5 条：

1. 不直接删正式大库
2. 先分类，再迁目录
3. 先保证代码路径兼容，再做物理重排
4. 任何新产物都不要再往根目录乱堆
5. 先让 NAS 成为稳定生产主站，再做彻底美化

## 9. 当前最重要的结论

当前最重要的不是下掉腾讯云，也不是再开一次全量大迁移。

当前真正的状态是：

- NAS 生产主站已经跑起来了
- 公开访问临时方案已经通了
- 查询主链已经落到 NAS
- 但 NAS 还没接管盘中 crawler
- NAS 上的数据还没追到最新
- Windows 跑数后的同步机制还没改成以 NAS 为中心
- 正式公网域名方案还没做

接下来只按这个顺序推进：

1. `A1`：盘中 crawler 挪到 NAS
2. 定向补齐缺失日期数据
3. `C1`：目录治理收口
4. `B2`：Windows -> NAS 每日同步机制
5. `D1`：Cloudflare Tunnel + 自定义域名
6. `E1`：腾讯云退役决策
