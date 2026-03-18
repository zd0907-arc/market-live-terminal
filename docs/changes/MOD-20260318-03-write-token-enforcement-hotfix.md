# MOD-20260318-03-write-token-enforcement-hotfix

## 1. 基本信息
- 标题：生产写接口鉴权红线热修（移除公网代理自动注入）
- 状态：DONE
- 负责人：Codex / 发布 AI
- 关联 Task ID：`CHG-20260318-03`
- 关联 CAP：`CAP-SECURITY`, `CAP-RELEASE`
- 关联 STG：无

## 2. 背景与目标
- `v4.2.22` 发布后，生产冒烟发现匿名公网 `POST /api/watchlist` 返回 `200`。
- 根因是生产 Nginx 对全部 `/api` 请求无差别注入 `X-Write-Token`，使所有外部用户天然获得写权限。
- 目标：立即消除匿名公网写能力，同时保留单人管理员在受信终端上的最小可用写入口。

## 3. 方案与边界
- 做什么：
  - 移除生产 Nginx 对 `/api` 的全局 `X-Write-Token` 注入；
  - 前端默认只读，新增“当前浏览器会话管理员写令牌”入口；
  - 写请求失败时前端不再静默成功，统一抛出明确错误；
  - 补写鉴权/ingest 鉴权单测。
- 不做什么：
  - 本轮不引入完整登录系统；
  - 不改业务接口语义；
  - 不改数据库 schema。

## 4. 验收标准（Given/When/Then）
- Given 生产公网匿名请求，When `POST /api/watchlist` 或 `POST /api/config`，Then 必须返回 `401/503`，不得再返回 `200`。
- Given 管理员已在受信浏览器当前会话录入正确 `WRITE_API_TOKEN`，When 执行星标或配置保存，Then 请求应正常成功。
- Given 本地 `npm run dev`，When `.env.local` 已配置 `WRITE_API_TOKEN`，Then 仍可通过 Vite proxy 完成写请求，且浏览器构建产物中不包含 token。

## 5. 结果回填
- 实际改动：
  - `deploy/nginx.conf`、`deploy/docker-compose.yml`：移除生产 frontend 代理的全局写 token 注入链路；
  - `src/config.ts`：新增 session 级管理员写令牌读取/保存；
  - `src/components/common/ConfigModal.tsx`：新增生产写令牌录入口；
  - `src/services/stockService.ts`、`src/App.tsx`：写请求失败不再静默；
  - `backend/tests/test_security_guards.py`：补写鉴权与 ingest 鉴权测试。
- 验证结果：
  - `npm run check:baseline` 通过；
  - 本地 build 通过，后端测试通过；
  - 发布后需再次执行生产匿名写入冒烟，确认返回 `401/503`。

## 6. 风险与回滚
- 风险：
  - 管理员若未录入令牌，会误以为“写功能坏了”；需通过 UI 文案提示“生产默认只读”。
  - 浏览器会话内仍会临时持有令牌，因此只允许在受信设备使用。
- 回滚：
  1. 仅在确认有更安全替代方案时，才允许恢复新的受控注入方案；
  2. 严禁回滚到“公网代理对全部 `/api` 自动注入写 token”的状态。
