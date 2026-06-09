# 端口管理规范

## 1. 当前正式端口

| 场景 | 端口 | 说明 |
|---|---|---|
| Mac 本地前端 | `3001` | 唯一正式本地前端端口 |
| Mac 本地后端 | `8001` | 唯一正式本地后端端口 |
| NAS 项目 Web | `8080` | NAS 对内 / Tailscale 项目访问入口 |
| NAS Gitea Web | `3000` | NAS Git 管理界面 |
| NAS 管理后台 | `9443` | NAS 系统管理后台 |
| Docker 内部 backend | `8000` | 仅容器内部使用，不是 Mac 本地开发端口 |

## 2. 历史端口怎么理解

- `5173`、`5174`：只按历史 Vite 临时调试端口理解，不是正式标准，不写入 runbook。
- `8000`：当前只按容器内部 backend 端口理解；本地 Mac 直连后端时一律使用 `8001`。
- `3000`：当前只按 NAS `Gitea` Web 端口理解，不是本项目本地前端端口。

## 3. 本地开发红线

1. 本地前端默认只允许 `3001`。
2. 本地后端默认只允许 `8001`。
3. 端口被占用时，先清理旧实例，不要把前端默默改成 `5174`、`5175` 之类漂移端口。
4. 所有本地启动命令、截图、交接文档，默认都写 `3001 / 8001`。
5. 若某次排障必须临时改端口，必须显式标注“临时端口”，排障结束后恢复到正式口径。

## 4. 当前正式启动命令

```bash
cd /Users/dong/Desktop/AIGC/market-live-terminal
PORT=8001 bash ops/start_local_research_station.sh
BACKEND_PORT=8001 FRONTEND_PORT=3001 bash ops/start_local_research_frontend.sh
```

补充：

- `ops/start_local_research_station.sh` 已内置同仓库重复实例保护。
- `ops/start_local_research_frontend.sh` 已改成直接拉起本仓库 `vite`，并强制 `--strictPort`，不再因为 `npm run dev` 缺失或端口被占而漂移到别的端口。
