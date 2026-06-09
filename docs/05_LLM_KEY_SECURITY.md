# 05_LLM_KEY_SECURITY（LLM API Key 安全管理运维指南）

> 本文档说明如何在**线上服务环境（当前 NAS）**和**本地开发环境**安全地配置大模型 API Key，确保 Key 永远不会出现在代码仓库、数据库和 AI 工具的扫描范围中。
> 旧腾讯云只按 legacy/emergency 环境理解，不再当默认生产入口。
>
> **边界提醒**：本文件只定义密钥与安全注入规范；业务规则以 `docs/02_BUSINESS_DOMAIN.md` 为准，接口字段以 `docs/03_DATA_CONTRACTS.md` 为准，发布/远控步骤以 `docs/04_OPS_AND_DEV.md` 为准。

---

## 一、安全架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    安全隔离层                             │
├─────────────┬───────────────────┬───────────────────────┤
│   线上服务(NAS) │   本地开发 (Mac)   │   前端浏览器           │
├─────────────┼───────────────────┼───────────────────────┤
│ 宿主机 .env.nas-full │  .env.local 文件   │  ❌ 完全不接触 Key     │
│ → Docker 透传│  → python 直读     │  只显示模型名称        │
│             │  .gitignore 屏蔽   │  "测试连接"由后端执行   │
│             │  .cursorignore 屏蔽│                       │
└─────────────┴───────────────────┴───────────────────────┘
```

**核心原则**：Key 只在两个地方存在——云端服务器的环境变量 + 本地 `.env.local` 文件。绝不经过网络传输给前端。

---

## 二、线上服务环境配置（当前 NAS）

### 步骤 1：SSH 登录 NAS

```bash
ssh zhangdong@dxp4800pro
```

### 步骤 2：在 NAS 项目目录下创建 `.env.nas-full`

```bash
cd /volume1/docker/market-live-terminal/app
nano .env.nas-full
```

写入以下内容（替换为你的真实 Key）：

```env
# === LLM 大模型配置 ===
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-你的真实API密钥
LLM_MODEL=qwen3-max
LLM_PROXY=

# === v4.2.3+ 生产运行必需 ===
INGEST_TOKEN=replace-with-strong-token
WRITE_API_TOKEN=replace-with-strong-token
TUSHARE_TOKEN=replace-with-licensed-token
ENABLE_CLOUD_COLLECTOR=false
```

> `WRITE_API_TOKEN` 仅允许存在于服务端环境变量（backend / frontend 代理容器 / 本地 Vite dev proxy 所在进程）中。  
> `TUSHARE_TOKEN` 同样只允许存在于服务端环境变量 / 本地 `.env.local`，不得写入前端静态资源或提交到 Git。  
> **禁止**继续使用 `VITE_WRITE_API_TOKEN`、禁止把共享写 token 打包进浏览器静态资源。

保存并退出 (`Ctrl+X` → `Y` → `Enter`)。

### 步骤 3：设置文件权限（防止其他用户读取）

```bash
chmod 600 .env.nas-full
```

### 步骤 4：重启 Docker 服务使环境变量生效

```bash
cd /volume1/docker/market-live-terminal/app
docker compose --env-file .env.nas-full -f deploy/docker-compose.nas-full.yml up -d --build backend frontend
```

### 步骤 5：验证 Key 已正确注入容器

```bash
docker exec market-backend-nas env | grep LLM
```

应输出：
```
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-你的真实API密钥
LLM_MODEL=qwen3-max
```

> ⚠️ **注意**：`.env.nas-full` 只存在于 NAS 宿主机，不进入 Git。

### 旧 Cloud 兼容说明

- 旧腾讯云如仍需保活，只按 `legacy/emergency only` 处理。
- 旧 Cloud 相关脚本：`deploy_to_cloud.sh`、`sync_cloud_db.sh`、`sync_local_to_cloud.sh`
- 不再把 `111.229.144.202` 当当前默认生产环境，也不再把旧 Cloud `data/market_data.db` 当默认正式真相。

---

## 三、本地开发环境配置

### 步骤 1：编辑项目根目录的 `.env.local`

```bash
cd ~/Desktop/AIGC/market-live-terminal
nano .env.local
```

确保包含以下 LLM 配置：

```env
# === LLM 大模型配置 (开发环境) ===
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-你的开发用API密钥
LLM_MODEL=qwen3-max
LLM_PROXY=

# === 官方事件源配置 ===
TUSHARE_TOKEN=replace-with-dev-token

# === 其他开发配置 ===
MOCK_DATA_DATE=2026-03-06
```

### 步骤 2：确认安全屏蔽已生效

运行以下命令确认 `.env.local` 不会被 Git 追踪：

```bash
git status .env.local
# 应显示：没有任何输出（文件被 .gitignore 忽略）

git check-ignore .env.local
# 应输出：.env.local
```

### 步骤 3：启动本地后端

```bash
# 推荐：从项目根目录直接启动（main.py 已自动加载 .env.local）
cd ~/Desktop/AIGC/market-live-terminal
python -m backend.app.main
```

> 如需热重载调试，可在项目根目录使用：`uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`

---

## 四、安全检查清单

每次发版前，执行以下检查：

| # | 检查项 | 命令 | 期望结果 |
|---|--------|------|---------|
| 1 | `.env.local` 未被追踪 | `git check-ignore .env.local` | 输出 `.env.local` |
| 2 | `.env` 未被追踪 | `git check-ignore .env` | 输出 `.env` |
| 3 | 代码中无硬编码 Key | `grep -r "sk-" --include="*.py" --include="*.ts" --include="*.tsx" backend/ src/` | 无输出 |
| 4 | 数据库中无敏感 LLM 配置 | `sqlite3 "${USER_DB_PATH:-/Users/dong/Desktop/AIGC/market-data/live/user_data.db}" "SELECT key,value FROM app_config WHERE key LIKE 'llm_%'"` | 允许存在 `llm_model`；不得出现 `llm_api_key / llm_base_url / llm_proxy` |
| 5 | Config API 不泄露 Key | `curl localhost:8001/api/config \| python -m json.tool` | 输出中无 `llm_api_key` |

---

## 五、更换 Key / 更换模型

### NAS 线上服务
```bash
ssh zhangdong@dxp4800pro
cd /volume1/docker/market-live-terminal/app
nano .env.nas-full
docker compose --env-file .env.nas-full -f deploy/docker-compose.nas-full.yml up -d --build backend frontend
```

### 本地
```bash
nano .env.local        # 修改 Key 或模型名
# 重启后端即可生效
```

> 补充说明（`CHG-20260324-01`）：
> - **Key / Base URL / Proxy** 仍只能通过环境变量修改；
> - **模型名称** 现在允许在前端 AI 设置里保存到 `app_config.llm_model`，并优先覆盖环境变量 `LLM_MODEL`；
> - 该前端可写项属于**非敏感配置**，不改变本文件的 Key 安全边界。

---

## 六、常见问题

**Q: 发版后 LLM 功能不工作？**
A: 先检查 NAS 上的 `.env.nas-full` 是否存在，且 `docker-compose.nas-full.yml` 启动时确实带了 `--env-file .env.nas-full`。

**Q: 从旧版本升级后，数据库中还有 `llm_api_key` 残留怎么办？**
A: 无影响。新代码的 `get_app_config()` 已过滤掉 `llm_` 前缀的配置项，不会返回给前端。如需彻底清理：
```bash
sqlite3 "${USER_DB_PATH:-/Users/dong/Desktop/AIGC/market-data/live/user_data.db}" "DELETE FROM app_config WHERE key LIKE 'llm_%'"
```

**Q: 本地 AI（Cursor/Copilot）是否还能看到 Key？**
A: 不能。`.cursorignore` 已将 `.env.local` 屏蔽。Copilot 遵循 `.gitignore` 规则，同样会忽略。
