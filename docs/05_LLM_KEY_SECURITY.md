# 05_LLM_KEY_SECURITY（LLM API Key 安全管理运维指南）

> 本文档说明如何在**云端生产环境**和**本地开发环境**安全地配置大模型 API Key，确保 Key 永远不会出现在代码仓库、数据库和 AI 工具的扫描范围中。
>
> **边界提醒**：本文件只定义密钥与安全注入规范；业务规则以 `docs/02_BUSINESS_DOMAIN.md` 为准，接口字段以 `docs/03_DATA_CONTRACTS.md` 为准，发布/远控步骤以 `docs/04_OPS_AND_DEV.md` 为准。

---

## 一、安全架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    安全隔离层                             │
├─────────────┬───────────────────┬───────────────────────┤
│   云端生产    │   本地开发 (Mac)   │   前端浏览器           │
├─────────────┼───────────────────┼───────────────────────┤
│ 宿主机 .env  │  .env.local 文件   │  ❌ 完全不接触 Key     │
│ → Docker 透传│  → python 直读     │  只显示模型名称        │
│             │  .gitignore 屏蔽   │  "测试连接"由后端执行   │
│             │  .cursorignore 屏蔽│                       │
└─────────────┴───────────────────┴───────────────────────┘
```

**核心原则**：Key 只在两个地方存在——云端服务器的环境变量 + 本地 `.env.local` 文件。绝不经过网络传输给前端。

---

## 二、云端生产环境配置

### 步骤 1：SSH 登录云服务器

```bash
ssh ubuntu@111.229.144.202
```

### 步骤 2：在项目 deploy 目录下创建 `.env` 文件

```bash
cd ~/market-live-terminal/deploy
nano .env
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
ENABLE_CLOUD_COLLECTOR=false
```

> `WRITE_API_TOKEN` 仅允许存在于服务端环境变量（backend / frontend 代理容器 / 本地 Vite dev proxy 所在进程）中。  
> **禁止**继续使用 `VITE_WRITE_API_TOKEN`、禁止把共享写 token 打包进浏览器静态资源。

保存并退出 (`Ctrl+X` → `Y` → `Enter`)。

### 步骤 3：设置文件权限（防止其他用户读取）

```bash
chmod 600 .env
```

### 步骤 4：重启 Docker 服务使环境变量生效

```bash
cd ~/market-live-terminal/deploy
sudo docker compose down
sudo docker compose up -d
```

### 步骤 5：验证 Key 已正确注入容器

```bash
sudo docker exec market-backend env | grep LLM
```

应输出：
```
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-你的真实API密钥
LLM_MODEL=qwen3-max
```

> ⚠️ **注意**：`deploy/.env` 文件**不会**被 Git 追踪（已在 `.gitignore` 中排除），所以每次首次部署都需要手动创建这个文件。

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
| 4 | 数据库中无 Key | `sqlite3 data/user_data.db "SELECT * FROM app_config WHERE key LIKE 'llm_%'"` | 无结果或仅有历史残留 |
| 5 | Config API 不泄露 Key | `curl localhost:8000/api/config \| python -m json.tool` | 输出中无 `llm_api_key` |

---

## 五、更换 Key / 更换模型

### 云端
```bash
ssh ubuntu@111.229.144.202
cd ~/market-live-terminal/deploy
nano .env              # 修改 Key 或模型名
sudo docker compose down
sudo docker compose up -d
```

### 本地
```bash
nano .env.local        # 修改 Key 或模型名
# 重启后端即可生效
```

---

## 六、常见问题

**Q: 发版后 LLM 功能不工作？**
A: 检查云端 `deploy/.env` 是否存在。`deploy_to_cloud.sh` 使用 `git reset --hard`，这不会删除 `.env`（它不在 Git 中），但如果是首次部署或服务器重建，需要手动创建。

**Q: 从旧版本升级后，数据库中还有 `llm_api_key` 残留怎么办？**
A: 无影响。新代码的 `get_app_config()` 已过滤掉 `llm_` 前缀的配置项，不会返回给前端。如需彻底清理：
```bash
sqlite3 data/user_data.db "DELETE FROM app_config WHERE key LIKE 'llm_%'"
```

**Q: 本地 AI（Cursor/Copilot）是否还能看到 Key？**
A: 不能。`.cursorignore` 已将 `.env.local` 屏蔽。Copilot 遵循 `.gitignore` 规则，同样会忽略。
