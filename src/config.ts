// 统一管理后端 API 地址
// 开发环境：使用 Vite 代理 (/api -> http://localhost:8000/api) 或直接连接
// 生产环境：使用相对路径 /api (由 Nginx 代理)

export const API_BASE_URL = import.meta.env.PROD ? '/api' : '/api';
