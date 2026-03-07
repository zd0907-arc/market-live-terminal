// 统一管理后端 API 地址
// 开发环境：使用 Vite 代理 (/api -> http://localhost:8000/api) 或直接连接
// 生产环境：使用相对路径 /api (由 Nginx 代理)

export const API_BASE_URL = import.meta.env.PROD ? '/api' : '/api';
export const WRITE_API_TOKEN = (import.meta.env.VITE_WRITE_API_TOKEN || '').trim();

export const getWriteHeaders = (withJson: boolean = false): Record<string, string> => {
  const headers: Record<string, string> = {};
  if (withJson) {
    headers['Content-Type'] = 'application/json';
  }
  if (WRITE_API_TOKEN) {
    headers['X-Write-Token'] = WRITE_API_TOKEN;
  }
  return headers;
};
