// 统一管理后端 API 地址
// 开发环境：使用 Vite 代理 (/api -> http://127.0.0.1:8001/api) 或直接连接
// 生产环境：使用相对路径 /api (由 Nginx 代理)

export const API_BASE_URL = import.meta.env.PROD ? '/api' : '/api';
export const DEV_BACKEND_DIRECT_URL = import.meta.env.PROD ? '' : 'http://127.0.0.1:8001';

export const getWriteHeaders = (withJson: boolean = false): Record<string, string> => {
  const headers: Record<string, string> = {};
  if (withJson) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
};


const isTruthyEnv = (value: unknown): boolean => {
  return String(value ?? '').trim().toLowerCase() === 'true' || String(value ?? '').trim() === '1';
};

// 云端轻量模式：生产只开放盯盘 + 复盘，隐藏并阻断选股/研究类页面入口。
export const CLOUD_LITE_MODE = isTruthyEnv(import.meta.env.VITE_CLOUD_LITE_MODE || import.meta.env.VITE_CLOUD_LITE);
