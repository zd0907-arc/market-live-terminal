# 代码仓与数据仓排布收口方案

日期：2026-06-19

## 1. 结论

当前 Mac 本地已经按“代码仓 / 数据仓”完成结构收口。代码仓只保留代码、文档、测试、部署脚本和小型配置；研究产物、模型产物、页面 payload、跑数现场已经迁入数据仓。

当前目标形态：

- 代码仓只放源代码、文档、测试、部署脚本、小型配置。
- 数据仓放正式数据、模型产物、研究产物、运行中间包。
- Mac 和 NAS 的数据仓结构尽量一致。
- NAS 只允许额外多出备份和 Docker/Gitea 自身服务数据。

## 2. 为什么历史上会放进代码仓

这不是一个理想的长期决策，更像历史演进结果：

1. 早期选股研究脚本在代码仓里开发，产物就近写到代码仓。
2. 后来部分产物被页面和线上服务复用，变成运行依赖。
3. 再后来正式数据库已经迁到 `market-data`，但非数据库产物没有同步迁完。
4. 所以现在形成了“功能能跑，但肉眼目录不统一”的状态。

## 3. 当前盘点

### 3.1 代码仓

位置：`/Users/dong/ZhangData/market-live-terminal`

应保留：

- 源代码、前端页面、后端服务。
- 文档、测试、部署脚本。
- 小型规则配置。
- 必须随代码版本演进的示例数据。

不应长期放在代码仓：

- 选股模型产物。
- 策略回测产物。
- 运行中间包。
- 构建产物。
- 大型页面研究 payload。

已迁出代码仓的历史混杂：

- `data/selection`：已迁到 `market-data/artifacts/selection`，代码仓副本已移除。
- `.run`：已迁到 `market-data/runs`，代码仓现场目录已移除。
- `public/research`：已迁到 `market-data/artifacts/research_payloads`，代码仓副本已移除；页面 `/research` 由后端从数据仓提供。
- `dist`：构建产物，可重建。
- `node_modules`：本机依赖，可重装，不属于同步对象。

### 3.2 数据仓

位置：`/Users/dong/ZhangData/market-data`

当前主结构已经承接正式本地数据：

- `live`：本地轻量消费数据。
- `research/current`：正式研究数据。
- `cache`：缓存。
- `artifacts`：模型、研究产物、页面 payload。
- `incoming`：增量输入。
- `runs`：跑数现场和中间包。

当前 Mac 本地不再把这些产物放回代码仓。

### 3.3 NAS

位置：`/volume1/docker/market-live-terminal`

当前合理部分：

- `app`：线上运行代码。
- `data`：线上运行数据。
- `backups`：备份区。

NAS 需要按本轮 Mac 结构同步后的目标状态：

- 线上模型产物迁到 `data/artifacts/selection`。
- 页面研究 payload 迁到 `data/artifacts/research_payloads`。
- 跑数现场和中间包迁到 `data/runs`。
- `logs`：当前为空，不是运行必需。
- `repos`：当前为空，不是 Gitea 真实仓库。
- `_pending_delete_20260619`：待用户确认删除的历史清理区。

## 4. 最终推荐结构

### 4.1 Mac

```text
/Users/dong/ZhangData/
  market-live-terminal/        # 代码仓
  market-data/                 # 数据仓
    live/                      # 本地页面消费数据
    research/current/          # 正式研究数据
    artifacts/
      selection/               # 选股模型、策略、研究产物
      market_heat/             # 市场热度产物
      research_payloads/       # 页面研究 payload
    cache/                     # 可重建缓存
    incoming/                  # 增量输入
    runs/                      # 跑数现场和中间包
```

### 4.2 NAS

```text
/volume1/docker/market-live-terminal/
  app/                         # 线上运行代码
  data/                        # 线上运行数据，结构尽量对齐 Mac market-data
    live/
    research/current/
    artifacts/
      selection/
      market_heat/
      research_payloads/
    cache/
    incoming/
    runs/
  backups/                     # NAS 专属备份
```

### 4.3 Windows

Windows 仍以跑数为主，不要求和 Mac 完全肉眼一致，但业务语义要一致：

- 保留全量原始数据和完整跑数数据。
- 输出结果最终同步到 Mac/NAS 的对应业务目录。
- 不承担日常代码开发职责。

## 5. 本地收口结果

### 5.1 模型和研究产物

目标：解决 `selection` 目录不一致。当前 Mac 本地已完成：

- 选股模型、策略、长期趋势等产物已进入 `market-data/artifacts/selection`。
- 代码仓 `data/selection` 副本已删除。
- 后端 `/data/selection` 从数据仓只读提供。
- NAS full compose 已改为读取 `data/artifacts/selection`。

### 5.2 运行现场

目标：让代码仓不再长期堆 `.run`。当前 Mac 本地已完成：

- 旧 `.run` 内容已进入 `market-data/runs`。
- 代码仓 `.run` 已删除。
- 本地日跑、盘后 L2、状态查询、crawler 运行痕迹默认写入 `market-data/runs`。

### 5.3 页面研究 payload

目标：让页面研究 payload 不再散在 `public/research`。当前 Mac 本地已完成：

- 源产物位于 `market-data/artifacts/research_payloads`。
- 代码仓 `public/research` 副本已删除。
- 本地 Vite 与 NAS Nginx 都把 `/research` 转发到后端，由后端从数据仓提供。

### 5.4 NAS 清理

目标：让 NAS 肉眼结构干净。

可清理对象：

- 空的 `logs`。
- 空的 `repos`。
- `.DS_Store`。

保留对象：

- `backups`。
- `app`。
- `data`。
- `_pending_delete_20260619` 等用户确认后再删。

## 6. 风险

1. 部分历史研究脚本正文里仍有旧路径字样，后续只要再次启用，就必须按当前数据仓规则改输出。
2. NAS 同步时不能用 Mac 的轻量 atomic 覆盖 NAS 的全量 atomic。
3. NAS 旧 `data/selection` 如果仍被旧容器或旧 compose 使用，需先切到本轮 full compose 后再清理。

## 7. 本轮暴露问题与处理状态

### 7.1 已修

1. 复盘页历史只到 6 月 9 日：原因是长周期复盘误走分钟级口径；已改成长周期默认日级口径。
2. 选股页市场水位没数据：原因是水位历史只读到最新短窗口；已合并旧历史与当前产物，并让读取逻辑能跨目录补齐。
3. 选股策略缺底层数据时报错：原因是本地缺 6 月 11 日至 6 月 12 日明细底座时，部分策略没有正常返回空状态；已改为显式空结果。
4. PPO 回测复盘没数据：原因是模型回测产物迁到数据仓后旧产物没有跟随；已补到 `market-data/artifacts/selection/evolution_lab`。
5. 本地后端启动报错：原因是路由日志把静态挂载也当普通接口读；已修。
6. 选股页顶部股票卡压缩意图丢失：原因是页面传了 `compact`，但公共卡片组件没有承接该参数；已补成显式紧凑模式。

### 7.2 暂不修或需要后续同步

1. Mac 本地缺少部分 6 月 11 日至 6 月 12 日盘后明细底座；用户已确认 67G 大库不在本地可以接受，后续可从 NAS/Windows 补齐。
2. `docs/selection` 与 `docs/strategy-rework` 里仍有旧实验 CSV/JSON；本轮签收为历史实验包，不再扩大。
3. 部分旧脚本仍写旧目录；本轮已改活跃链路，后续重新启用旧脚本时按当前规则迁。

## 8. 建议验收标准

1. Mac 和 NAS 数据仓都能看到同样的业务层级：`live / research/current / artifacts / cache / incoming / runs`。
2. 代码仓根目录不再有长期运行数据。
3. NAS 除 `backups` 和 Docker/Gitea 服务数据外，不再多出无解释目录。
4. 选股页、复盘页、首页、市场热度、机会发现模型相关功能全部通过冒烟。
5. 文档里只用业务语义解释目录，不再用一串底层库名解释。
